"""Bounded, non-executing inspection of untrusted Anki package archives."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import stat
import tempfile
import time
import unicodedata
import zipfile
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 512
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_MEDIA_MEMBERS = 500
MAX_CARDS = 10_000
MAX_NOTES = 10_000
MAX_MODELS = 1_000
MAX_DECKS = 1_000
MAX_FIELD_BYTES = 64 * 1024
MAX_SQLITE_SECONDS = 5.0
MAX_SQLITE_PROGRESS_CALLS = 25_000

_COLLECTION_MEMBERS = frozenset({"collection.anki2", "collection.anki21"})
# genanki 0.13.1 emits these fixed native indexes.  They are part of the
# canonical Anki schema; arbitrary package/add-on indexes remain rejected.
_ALLOWED_NATIVE_INDEXES = frozenset(
    {
        "ix_cards_nid",
        "ix_cards_sched",
        "ix_cards_usn",
        "ix_notes_csum",
        "ix_notes_usn",
        "ix_revlog_cid",
        "ix_revlog_usn",
    }
)
_NATIVE_INDEX_SQL = {
    "ix_cards_nid": "create index ix_cards_nid on cards (nid)",
    "ix_cards_sched": "create index ix_cards_sched on cards (did, queue, due)",
    "ix_cards_usn": "create index ix_cards_usn on cards (usn)",
    "ix_notes_csum": "create index ix_notes_csum on notes (csum)",
    "ix_notes_usn": "create index ix_notes_usn on notes (usn)",
    "ix_revlog_cid": "create index ix_revlog_cid on revlog (cid)",
    "ix_revlog_usn": "create index ix_revlog_usn on revlog (usn)",
}
_ALLOWED_ZIP_METHODS = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_VISIBLE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MEDIA_NAME = re.compile(r"^[^/\\\x00-\x1f\x7f]{1,512}$")
_SOUND = re.compile(r"\[sound:([^\]]{1,512})\]", re.IGNORECASE)
_CLOZE = re.compile(r"\{\{c([1-9][0-9]{0,2})::(.*?)(?:::(.*?))?\}\}", re.DOTALL)
_MUSTACHE = re.compile(r"\{\{([^{}]{1,128})\}\}")
_FORBIDDEN_MARKUP = re.compile(
    r"<(?:script|style|iframe|object|embed|svg|math|link|meta|base)\b|"
    r"\bon[a-z0-9_-]+\s*=|(?:javascript|file|data|https?|ftp):|"
    r"(?:\.\./|\.\.\\)|url\s*\(|@import|expression\s*\(",
    re.IGNORECASE,
)
_ALLOWED_TAGS = frozenset(
    {
        "b",
        "strong",
        "i",
        "em",
        "u",
        "s",
        "br",
        "div",
        "p",
        "span",
        "ul",
        "ol",
        "li",
        "a",
        "img",
    }
)
_ALLOWED_TEMPLATE_TAGS = frozenset(
    {
        "b",
        "strong",
        "i",
        "em",
        "u",
        "s",
        "br",
        "div",
        "p",
        "span",
        "ul",
        "ol",
        "li",
        "hr",
    }
)
_BLOCK_TAGS = frozenset({"br", "div", "p", "ul", "ol", "li"})


class AnkiPackageRejected(ValueError):
    """A safe, stable rejection for an untrusted package."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AnkiImportOptions(_Frozen):
    schema_version: Literal[1] = 1
    syllabus_unit_id: str | None = Field(default=None, max_length=64)
    deck_names: tuple[str, ...] = Field(default_factory=tuple, max_length=100)

    @field_validator("syllabus_unit_id")
    @classmethod
    def unit_id_is_valid(cls, value: str | None) -> str | None:
        if value is not None and _VISIBLE_ID.fullmatch(value) is None:
            raise ValueError("invalid syllabus unit ID")
        return value

    @field_validator("deck_names", mode="before")
    @classmethod
    def deck_names_are_immutable(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("deck_names")
    @classmethod
    def deck_names_are_bounded(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("duplicate deck names")
        if any(
            not value.strip() or value != value.strip() or len(value) > 200
            for value in values
        ):
            raise ValueError("invalid deck name")
        return values


class AnkiCardPreview(_Frozen):
    schema_version: Literal[1] = 1
    card_id: str = Field(min_length=1, max_length=64)
    note_id: str = Field(min_length=1, max_length=64)
    kind: Literal["basic", "reverse", "cloze"]
    front: str = Field(min_length=1, max_length=8_000)
    back: str = Field(min_length=1, max_length=16_000)
    deck_name: str = Field(min_length=1, max_length=200)
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    media_names: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    # Bounded compatibility projection retained from the inspected note.
    # ``front``/``back`` are rendered-card projections; export needs the
    # original note fields to rebuild reverse and Cloze notes losslessly.
    source_note_id: str | None = Field(default=None, max_length=128)
    source_model_kind: Literal["basic", "cloze"] | None = None
    template_ord: int | None = Field(default=None, ge=0, le=999)
    source_fields: tuple[str, ...] = Field(default_factory=tuple, max_length=4)

    @field_validator("source_fields", mode="before")
    @classmethod
    def source_fields_are_immutable(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("source_fields")
    @classmethod
    def source_fields_are_bounded(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values and not 2 <= len(values) <= 4:
            raise ValueError("invalid source fields")
        if any(
            not isinstance(value, str) or len(value.encode("utf-8")) > 16_384
            for value in values
        ):
            raise ValueError("invalid source fields")
        return values

    @field_validator("source_note_id")
    @classmethod
    def source_note_id_is_bounded(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("invalid source note ID")
        return value

    @model_validator(mode="after")
    def template_ordinal_matches_model(self) -> "AnkiCardPreview":
        if (
            self.template_ord is not None
            and self.kind != "cloze"
            and self.template_ord > 1
        ):
            raise ValueError("invalid Basic/reverse template ordinal")
        if (
            self.template_ord is not None
            and self.source_model_kind == "basic"
            and self.template_ord > 1
        ):
            raise ValueError("invalid Basic/reverse template ordinal")
        return self


class AnkiPackageInspection(_Frozen):
    schema_version: Literal[1] = 1
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_member: Literal["collection.anki2", "collection.anki21"]
    cards: tuple[AnkiCardPreview, ...] = Field(max_length=MAX_CARDS)
    note_count: int = Field(ge=0, le=MAX_NOTES)
    transformed_count: int = Field(ge=0, le=MAX_CARDS)
    skipped_count: int = Field(default=0, ge=0, le=MAX_CARDS)
    deck_names: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_DECKS)
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000)
    media_names: tuple[str, ...] = Field(
        default_factory=tuple, max_length=MAX_MEDIA_MEMBERS
    )


def _reject(code: str) -> None:
    raise AnkiPackageRejected(code)


def _snapshot_archive(path: Path, destination: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as source, destination.open("xb") as target:
            os.chmod(destination, 0o600)
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    _reject("archive_size_exceeded")
                digest.update(chunk)
                target.write(chunk)
    except AnkiPackageRejected:
        raise
    except OSError:
        _reject("archive_unavailable")
    return digest.hexdigest()


def _safe_member_name(name: object) -> str:
    if not isinstance(name, str):
        _reject("unsafe_member_path")
    try:
        encoded = name.encode("utf-8", "strict")
    except UnicodeError:
        _reject("unsafe_member_path")
    if not encoded or len(encoded) > 4096 or unicodedata.normalize("NFC", name) != name:
        _reject("unsafe_member_path")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        _reject("unsafe_member_path")
    if "\\" in name or "/" in name or name.startswith(("/", "~")):
        _reject("unsafe_member_path")
    if re.match(r"^[A-Za-z]:", name) or name in {".", ".."} or ".." in name.split("/"):
        _reject("unsafe_member_path")
    return name


def _validate_archive(
    archive: zipfile.ZipFile,
) -> tuple[zipfile.ZipInfo, zipfile.ZipInfo, dict[str, str]]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        _reject("member_count_exceeded")
    seen: set[str] = set()
    supported_collections: list[zipfile.ZipInfo] = []
    media_info: zipfile.ZipInfo | None = None
    numeric_infos: dict[str, zipfile.ZipInfo] = {}
    expanded_total = 0
    for info in infos:
        name = _safe_member_name(info.filename)
        key = unicodedata.normalize("NFC", name).casefold()
        if key in seen:
            _reject("duplicate_member")
        seen.add(key)
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode) if mode else stat.S_IFREG
        if info.is_dir() or kind not in {0, stat.S_IFREG}:
            _reject("unsafe_member_type")
        if info.flag_bits & 0x1:
            _reject("encrypted_member")
        if info.compress_type not in _ALLOWED_ZIP_METHODS:
            _reject("unsupported_compression")
        if (
            info.file_size < 0
            or info.compress_size < 0
            or info.file_size > MAX_MEMBER_BYTES
        ):
            _reject("member_size_exceeded")
        expanded_total += info.file_size
        if expanded_total > MAX_EXPANDED_BYTES:
            _reject("expanded_size_exceeded")
        if (
            info.file_size > 1024
            and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO
        ):
            _reject("compression_ratio_exceeded")
        if name in _COLLECTION_MEMBERS:
            supported_collections.append(info)
        elif name.startswith("collection."):
            _reject("unsupported_collection")
        elif name == "media":
            media_info = info
        elif name.isascii() and name.isdecimal() and str(int(name)) == name:
            numeric_infos[name] = info
        else:
            _reject("unexpected_member")
    if len(supported_collections) > 1:
        _reject("ambiguous_collection")
    if not supported_collections:
        _reject("unsupported_collection")
    if media_info is None or media_info.file_size > 2 * 1024 * 1024:
        _reject("invalid_media")
    if len(numeric_infos) > MAX_MEDIA_MEMBERS:
        _reject("media_count_exceeded")
    try:
        raw_manifest = archive.read(media_info)
        manifest_value = json.loads(raw_manifest.decode("utf-8", "strict"))
    except Exception:
        _reject("invalid_media")
    if not isinstance(manifest_value, dict):
        _reject("invalid_media")
    manifest: dict[str, str] = {}
    seen_names: set[str] = set()
    for key, value in manifest_value.items():
        if (
            not isinstance(key, str)
            or not key.isascii()
            or not key.isdecimal()
            or str(int(key)) != key
        ):
            _reject("invalid_media")
        if not isinstance(value, str) or _MEDIA_NAME.fullmatch(value) is None:
            _reject("invalid_media_filename")
        if (
            value in {".", ".."}
            or re.match(r"^[A-Za-z]:", value)
            or ".." in value
            or ":" in value
        ):
            _reject("invalid_media_filename")
        normalized = unicodedata.normalize("NFC", value)
        if normalized != value or normalized.casefold() in seen_names:
            _reject("invalid_media_filename")
        seen_names.add(normalized.casefold())
        manifest[key] = value
    if set(manifest) != set(numeric_infos):
        _reject("invalid_media")
    return supported_collections[0], media_info, manifest


def _unsafe_markup(value: str) -> bool:
    return bool(_FORBIDDEN_MARKUP.search(html.unescape(value)))


class _FieldParser(HTMLParser):
    def __init__(self, media_names: frozenset[str]):
        super().__init__(convert_charrefs=True)
        self.media_names = media_names
        self.parts: list[str] = []
        self.media: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag not in _ALLOWED_TAGS:
            _reject("unsafe_field")
        for name, value in attrs:
            lowered = name.casefold()
            if lowered.startswith("on"):
                _reject("unsafe_field")
            if tag == "img" and lowered == "src":
                if value is None or value not in self.media_names:
                    _reject("unsafe_media_reference")
                self.media.add(value)
                self.parts.append(f" [media:{value}] ")
            elif lowered in {"class", "style", "title", "alt"}:
                if value and _unsafe_markup(value):
                    _reject("unsafe_field")
            elif tag == "a" and lowered == "href":
                if value:
                    _reject("unsafe_field")
            else:
                _reject("unsafe_field")
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() not in _ALLOWED_TAGS:
            _reject("unsafe_field")
        if tag.casefold() in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _clean_text(
    value: object,
    *,
    media_names: frozenset[str],
    limit: int,
    allow_empty: bool = False,
) -> tuple[str, tuple[str, ...]]:
    if (
        not isinstance(value, str)
        or len(value.encode("utf-8", "strict")) > MAX_FIELD_BYTES
    ):
        _reject("field_size_exceeded")
    if _unsafe_markup(value):
        _reject("unsafe_field")
    parser = _FieldParser(media_names)
    try:
        parser.feed(value)
        parser.close()
    except AnkiPackageRejected:
        raise
    except Exception:
        _reject("unsafe_field")
    text = "".join(parser.parts)

    def sound_replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in media_names:
            _reject("unsafe_media_reference")
        parser.media.add(name)
        return f" [media:{name}] "

    text = _SOUND.sub(sound_replace, text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if (
        (not text and not allow_empty)
        or len(text) > limit
        or any(ord(char) == 0 or ord(char) == 127 for char in text)
    ):
        _reject("unsafe_field")
    return text, tuple(sorted(parser.media))


class _TemplateParser(HTMLParser):
    """Validate template markup without rendering or retaining it."""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() not in _ALLOWED_TEMPLATE_TAGS:
            _reject("unsafe_template")
        for name, value in attrs:
            if name.casefold() not in {"id", "class", "style"}:
                _reject("unsafe_template")
            if value and _unsafe_markup(value):
                _reject("unsafe_template")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() not in _ALLOWED_TEMPLATE_TAGS:
            _reject("unsafe_template")


def _validate_template_markup(source: str) -> None:
    parser = _TemplateParser(convert_charrefs=True)
    try:
        parser.feed(source)
        parser.close()
    except AnkiPackageRejected:
        raise
    except Exception:
        _reject("unsafe_template")


def _json_object(value: object, *, code: str) -> dict[str, Any]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 8 * 1024 * 1024:
        _reject(code)
    try:
        decoded = json.loads(value)
    except Exception:
        _reject(code)
    if not isinstance(decoded, dict):
        _reject(code)
    return decoded


def _numeric_json_id(key: object, value: object, *, code: str) -> int:
    """Decode one canonical positive SQLite identifier without coercion surprises."""

    if (
        not isinstance(key, str)
        or not key.isascii()
        or not key.isdecimal()
        or key.startswith("0")
        or len(key) > 19
    ):
        _reject(code)
    numeric = int(key)
    if not 1 <= numeric <= 9_223_372_036_854_775_807:
        _reject(code)
    if isinstance(value, bool):
        _reject(code)
    if isinstance(value, int):
        valid_value = value == numeric
    elif isinstance(value, str):
        valid_value = (
            value.isascii()
            and value.isdecimal()
            and not value.startswith("0")
            and int(value) == numeric
        )
    else:
        valid_value = False
    if not valid_value:
        _reject(code)
    return numeric


def _bounded_integer(value: object, *, minimum: int, maximum: int) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and minimum <= value <= maximum
    )


def _validate_imported_schedule(values: tuple[object, ...]) -> None:
    """Validate imported scheduling metadata without adopting it as authority."""

    (
        card_type,
        queue,
        due,
        interval,
        factor,
        repetitions,
        lapses,
        remaining,
        original_due,
        original_deck_id,
        flags,
    ) = values
    if not (
        _bounded_integer(card_type, minimum=0, maximum=3)
        and _bounded_integer(queue, minimum=-3, maximum=4)
        and _bounded_integer(due, minimum=0, maximum=9_223_372_036_854_775_807)
        # Legacy Anki learning intervals may be negative seconds.  Preserve
        # compatibility without accepting effectively unbounded integers.
        and _bounded_integer(interval, minimum=-31_536_000, maximum=2_147_483_647)
        and _bounded_integer(factor, minimum=0, maximum=2_147_483_647)
        and _bounded_integer(repetitions, minimum=0, maximum=2_147_483_647)
        and _bounded_integer(lapses, minimum=0, maximum=2_147_483_647)
        and _bounded_integer(remaining, minimum=0, maximum=2_147_483_647)
        and _bounded_integer(original_due, minimum=0, maximum=9_223_372_036_854_775_807)
        and _bounded_integer(
            original_deck_id, minimum=0, maximum=9_223_372_036_854_775_807
        )
        and _bounded_integer(flags, minimum=0, maximum=2_147_483_647)
    ):
        _reject("invalid_scheduling")


def _validate_templates(
    model: Mapping[str, Any], field_names: tuple[str, ...]
) -> tuple[int, tuple[int, ...]]:
    model_type = model.get("type")
    templates = model.get("tmpls")
    css = model.get("css", "")
    if (
        isinstance(model_type, bool)
        or model_type not in {0, 1}
        or not isinstance(templates, list)
    ):
        _reject("unsupported_model")
    if not isinstance(css, str) or len(css) > 128_000 or _unsafe_markup(css):
        _reject("unsafe_template")
    if not 1 <= len(templates) <= 2:
        _reject("unsupported_model")
    ords: list[int] = []
    allowed_tokens = (
        set(field_names) | {"FrontSide"} | {f"cloze:{name}" for name in field_names}
    )
    for template in templates:
        if not isinstance(template, dict):
            _reject("unsupported_model")
        ord_value = template.get("ord")
        if (
            isinstance(ord_value, bool)
            or not isinstance(ord_value, int)
            or ord_value not in {0, 1}
        ):
            _reject("unsupported_model")
        ords.append(ord_value)
        for key in ("qfmt", "afmt"):
            source = template.get(key)
            if (
                not isinstance(source, str)
                or len(source) > 128_000
                or _unsafe_markup(source)
            ):
                _reject("unsafe_template")
            _validate_template_markup(source)
            tokens = _MUSTACHE.findall(source)
            if any(token.strip() not in allowed_tokens for token in tokens):
                _reject("unsafe_template")
    if len(set(ords)) != len(ords):
        _reject("unsupported_model")
    if model_type == 1 and (
        field_names[:2] != ("Text", "Extra") or tuple(ords) != (0,)
    ):
        _reject("unsupported_model")
    if model_type == 0 and (
        field_names[:2] != ("Front", "Back") or sorted(ords) != list(range(len(ords)))
    ):
        _reject("unsupported_model")
    return model_type, tuple(ords)


def _inspect_sqlite(
    path: Path,
    *,
    package_sha256: str,
    collection_member: str,
    collection_sha256: str,
    media_names: tuple[str, ...],
) -> AnkiPackageInspection:
    try:
        with path.open("rb") as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                _reject("invalid_sqlite_header")
    except AnkiPackageRejected:
        raise
    except OSError:
        _reject("invalid_sqlite_header")
    uri = f"file:{quote(path.resolve().as_posix(), safe='/')}?mode=ro&immutable=1"
    started = time.monotonic()
    calls = 0

    def progress() -> int:
        nonlocal calls
        calls += 1
        return int(
            calls > MAX_SQLITE_PROGRESS_CALLS
            or time.monotonic() - started > MAX_SQLITE_SECONDS
        )

    try:
        with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
            connection.enable_load_extension(False)
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.set_progress_handler(progress, 1_000)
            databases = list(connection.execute("PRAGMA database_list"))
            if len(databases) != 1 or databases[0][1] != "main":
                _reject("unsafe_sqlite_schema")
            schema_rows = list(
                connection.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master "
                    "ORDER BY name LIMIT 101"
                )
            )
            if len(schema_rows) > 100:
                _reject("unsafe_sqlite_schema")
            allowed_tables = {"col", "notes", "cards", "revlog", "graves"}
            tables = {row[1] for row in schema_rows if row[0] == "table"}
            if tables != allowed_tables or any(
                row[0] not in {"table", "index"} for row in schema_rows
            ):
                _reject("unsafe_sqlite_schema")
            for row in schema_rows:
                if row[0] != "index" or str(row[1]).startswith("sqlite_autoindex_"):
                    continue
                index_name = str(row[1])
                if index_name not in _ALLOWED_NATIVE_INDEXES:
                    _reject("unsafe_sqlite_schema")
                normalized_sql = re.sub(r"\s+", " ", str(row[3] or "").strip().lower())
                if normalized_sql != _NATIVE_INDEX_SQL[index_name]:
                    _reject("unsafe_sqlite_schema")
            expected_columns = {
                "col": {
                    "id",
                    "crt",
                    "mod",
                    "scm",
                    "ver",
                    "dty",
                    "usn",
                    "ls",
                    "conf",
                    "models",
                    "decks",
                    "dconf",
                    "tags",
                },
                "notes": {
                    "id",
                    "guid",
                    "mid",
                    "mod",
                    "usn",
                    "tags",
                    "flds",
                    "sfld",
                    "csum",
                    "flags",
                    "data",
                },
                "cards": {
                    "id",
                    "nid",
                    "did",
                    "ord",
                    "mod",
                    "usn",
                    "type",
                    "queue",
                    "due",
                    "ivl",
                    "factor",
                    "reps",
                    "lapses",
                    "left",
                    "odue",
                    "odid",
                    "flags",
                    "data",
                },
                "revlog": {
                    "id",
                    "cid",
                    "usn",
                    "ease",
                    "ivl",
                    "lastIvl",
                    "factor",
                    "time",
                    "type",
                },
                "graves": {"usn", "oid", "type"},
            }
            for table, expected in expected_columns.items():
                columns = {
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }  # table is fixed above
                if columns != expected:
                    _reject("unsupported_sqlite_schema")
            col_rows = list(
                connection.execute("SELECT ver, models, decks FROM col LIMIT 2")
            )
            if len(col_rows) != 1 or col_rows[0][0] not in {11, 12}:
                _reject("unsupported_sqlite_schema")
            models = _json_object(col_rows[0][1], code="invalid_models")
            decks = _json_object(col_rows[0][2], code="invalid_decks")
            if not 1 <= len(models) <= MAX_MODELS or not 1 <= len(decks) <= MAX_DECKS:
                _reject("collection_limit_exceeded")
            note_rows = list(
                connection.execute(
                    "SELECT id, guid, mid, tags, flds FROM notes ORDER BY id LIMIT ?",
                    (MAX_NOTES + 1,),
                )
            )
            card_rows = list(
                connection.execute(
                    "SELECT id, nid, did, ord, type, queue, due, ivl, factor, "
                    "reps, lapses, left, odue, odid, flags FROM cards "
                    "ORDER BY id LIMIT ?",
                    (MAX_CARDS + 1,),
                )
            )
            if len(note_rows) > MAX_NOTES or len(card_rows) > MAX_CARDS:
                _reject("collection_limit_exceeded")
    except AnkiPackageRejected:
        raise
    except sqlite3.Error:
        _reject("invalid_sqlite")

    model_specs: dict[int, tuple[int, tuple[str, ...], tuple[int, ...]]] = {}
    for key, value in models.items():
        if not isinstance(value, dict):
            _reject("invalid_models")
        model_id = _numeric_json_id(key, value.get("id"), code="invalid_models")
        fields = value.get("flds")
        if not isinstance(fields, list) or not 2 <= len(fields) <= 64:
            _reject("unsupported_model")
        if any(not isinstance(item, dict) for item in fields):
            _reject("unsupported_model")
        field_ords = tuple(item.get("ord") for item in fields)
        if any(
            isinstance(item, bool) or not isinstance(item, int) for item in field_ords
        ) or sorted(field_ords) != list(range(len(fields))):
            _reject("unsupported_model")
        ordered = sorted(fields, key=lambda item: item["ord"])
        field_names = tuple(
            item.get("name") for item in ordered if isinstance(item, dict)
        )
        if (
            len(field_names) != len(fields)
            or len(set(field_names)) != len(field_names)
            or any(
                not isinstance(name, str)
                or not name.strip()
                or name != name.strip()
                or len(name) > 128
                for name in field_names
            )
        ):
            _reject("unsupported_model")
        model_type, ords = _validate_templates(value, field_names)
        model_specs[model_id] = (model_type, field_names, ords)

    deck_names_by_id: dict[int, str] = {}
    for key, value in decks.items():
        if not isinstance(value, dict):
            _reject("invalid_decks")
        deck_id = _numeric_json_id(key, value.get("id"), code="invalid_decks")
        name = value.get("name")
        if (
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            or len(name) > 200
            or _unsafe_markup(name)
        ):
            _reject("invalid_decks")
        deck_names_by_id[deck_id] = name

    media_set = frozenset(media_names)
    notes: dict[int, tuple[int, tuple[str, ...], tuple[str, ...]]] = {}
    all_tags: set[str] = set()
    for note_id, guid, model_id, raw_tags, raw_fields in note_rows:
        if (
            isinstance(note_id, bool)
            or not isinstance(note_id, int)
            or not isinstance(guid, str)
            or not 1 <= len(guid) <= 128
        ):
            _reject("invalid_note")
        if model_id not in model_specs or not isinstance(raw_fields, str):
            _reject("invalid_note")
        field_values = tuple(raw_fields.split("\x1f"))
        if len(field_values) != len(model_specs[model_id][1]):
            _reject("invalid_note")
        if not isinstance(raw_tags, str) or len(raw_tags) > 16_000:
            _reject("invalid_note")
        tags = tuple(sorted(set(raw_tags.split())))
        if len(tags) > 100 or any(
            not tag
            or len(tag) > 128
            or any(ord(char) < 33 or ord(char) == 127 for char in tag)
            for tag in tags
        ):
            _reject("invalid_note")
        all_tags.update(tags)
        notes[note_id] = (model_id, field_values, tags)

    cards: list[AnkiCardPreview] = []
    seen_card_ids: set[int] = set()
    for card_row in card_rows:
        card_id, note_id, deck_id, ord_value = card_row[:4]
        _validate_imported_schedule(tuple(card_row[4:]))
        if (
            isinstance(card_id, bool)
            or not isinstance(card_id, int)
            or card_id in seen_card_ids
        ):
            _reject("invalid_card")
        seen_card_ids.add(card_id)
        if (
            note_id not in notes
            or deck_id not in deck_names_by_id
            or isinstance(ord_value, bool)
            or not isinstance(ord_value, int)
        ):
            _reject("invalid_card")
        model_id, fields, tags = notes[note_id]
        model_type, _field_names, template_ords = model_specs[model_id]
        if model_type == 0 and ord_value not in template_ords:
            _reject("invalid_card")
        if model_type == 1 and not 0 <= ord_value < 1_000:
            _reject("invalid_card")
        if model_type == 0:
            source_front, source_front_media = _clean_text(
                fields[0], media_names=media_set, limit=8_000
            )
            source_back, source_back_media = _clean_text(
                fields[1], media_names=media_set, limit=16_000
            )
            front_index, back_index = (0, 1) if ord_value == 0 else (1, 0)
            front, front_media = (
                (source_front, source_front_media)
                if front_index == 0
                else (source_back, source_back_media)
            )
            back, back_media = (
                (source_back, source_back_media)
                if back_index == 1
                else (source_front, source_front_media)
            )
            kind: Literal["basic", "reverse", "cloze"] = (
                "basic" if ord_value == 0 else "reverse"
            )
            source_fields = (source_front, source_back)
            source_model_kind: Literal["basic", "cloze"] = "basic"
        else:
            text, text_media = _clean_text(
                fields[0], media_names=media_set, limit=16_000
            )
            extra, extra_media = _clean_text(
                fields[1], media_names=media_set, limit=16_000, allow_empty=True
            )
            clozes = list(_CLOZE.finditer(text))
            target = ord_value + 1
            if not clozes or target not in {int(match.group(1)) for match in clozes}:
                _reject("invalid_cloze")
            front = _CLOZE.sub(
                lambda match: (
                    (f"[{match.group(3)}]" if match.group(3) else "[…]")
                    if int(match.group(1)) == target
                    else match.group(2)
                ),
                text,
            )
            back_text = _CLOZE.sub(lambda match: match.group(2), text)
            back = f"{back_text}\n{extra}".strip()
            if not front or len(front) > 8_000 or not back or len(back) > 16_000:
                _reject("invalid_cloze")
            front_media = text_media
            back_media = tuple(sorted(set(text_media) | set(extra_media)))
            kind = "cloze"
            source_fields = (text, extra)
            source_model_kind = "cloze"
        cards.append(
            AnkiCardPreview(
                card_id=str(card_id),
                note_id=str(note_id),
                kind=kind,
                front=front,
                back=back,
                deck_name=deck_names_by_id[deck_id],
                tags=tags,
                media_names=tuple(sorted(set(front_media) | set(back_media))),
                source_note_id=str(note_id),
                source_model_kind=source_model_kind,
                template_ord=ord_value,
                source_fields=source_fields,
            )
        )
    return AnkiPackageInspection(
        package_sha256=package_sha256,
        collection_sha256=collection_sha256,
        collection_member=collection_member,
        cards=tuple(cards),
        note_count=len(notes),
        transformed_count=sum(card.kind != "basic" for card in cards),
        deck_names=tuple(sorted(set(deck_names_by_id.values()))),
        tags=tuple(sorted(all_tags))[:1_000],
        media_names=tuple(sorted(media_names)),
    )


def inspect_anki_package(path: str | os.PathLike[str]) -> AnkiPackageInspection:
    """Inspect one `.apkg` without extracting, executing, or publishing it."""

    package_path = Path(path)
    try:
        with tempfile.TemporaryDirectory(prefix="dn-anki-inspect-") as temp_root:
            root = Path(temp_root)
            os.chmod(root, 0o700)
            snapshot_path = root / "package.apkg"
            package_sha256 = _snapshot_archive(package_path, snapshot_path)
            with zipfile.ZipFile(snapshot_path, "r") as archive:
                collection_info, _media_info, manifest = _validate_archive(archive)
                collection_digest = hashlib.sha256()
                collection_path = root / "collection.sqlite"
                copied = 0
                try:
                    with (
                        archive.open(collection_info, "r") as source,
                        collection_path.open("xb") as target,
                    ):
                        os.chmod(collection_path, 0o600)
                        while chunk := source.read(1024 * 1024):
                            copied += len(chunk)
                            if (
                                copied > collection_info.file_size
                                or copied > MAX_MEMBER_BYTES
                            ):
                                _reject("member_size_mismatch")
                            collection_digest.update(chunk)
                            target.write(chunk)
                except AnkiPackageRejected:
                    raise
                except Exception:
                    _reject("collection_read_failed")
                if copied != collection_info.file_size:
                    _reject("member_size_mismatch")
                return _inspect_sqlite(
                    collection_path,
                    package_sha256=package_sha256,
                    collection_member=collection_info.filename,
                    collection_sha256=collection_digest.hexdigest(),
                    media_names=tuple(sorted(manifest.values())),
                )
    except AnkiPackageRejected:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError):
        _reject("invalid_archive")


__all__ = [
    "AnkiCardPreview",
    "AnkiImportOptions",
    "AnkiPackageInspection",
    "AnkiPackageRejected",
    "inspect_anki_package",
]
