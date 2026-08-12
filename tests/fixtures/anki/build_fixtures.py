"""Build small deterministic `.apkg` fixtures without using Anki itself."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from itertools import permutations
from pathlib import Path
from typing import Any


def _model(*, kind: str, hostile_template: str | None = None) -> dict[str, Any]:
    if kind == "cloze":
        return {
            "1": {
                "id": 1,
                "name": "Cloze",
                "type": 1,
                "flds": [{"name": "Text", "ord": 0}, {"name": "Extra", "ord": 1}],
                "tmpls": [{"name": "Cloze", "ord": 0, "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"}],
                "css": ".card { font-family: sans-serif; }",
            }
        }
    templates = [
        {"name": "Card 1", "ord": 0, "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}
    ]
    if kind == "reverse":
        templates.append(
            {"name": "Card 2", "ord": 1, "qfmt": "{{Back}}", "afmt": "{{FrontSide}}<hr>{{Front}}"}
        )
    if hostile_template is not None:
        templates[0]["qfmt"] = hostile_template
    return {
        "1": {
            "id": 1,
            "name": "Basic",
            "type": 0,
            "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}],
            "tmpls": templates,
            "css": ".card { font-family: sans-serif; }",
        }
    }


def build_apkg(
    path: Path,
    *,
    kind: str = "basic",
    collection_member: str = "collection.anki2",
    front: str = "What is inertia?",
    back: str = "Resistance to a change in motion.",
    tags: str = " physics mechanics ",
    deck_name: str = "Mechanics",
    media: dict[str, bytes] | None = None,
    media_manifest: object | None = None,
    hostile_template: str | None = None,
    models_override: object | None = None,
    decks_override: object | None = None,
    extra_members: list[tuple[str | zipfile.ZipInfo, bytes]] | None = None,
    raw_collection: bytes | None = None,
    extra_sql: str | None = None,
    note_unique_constraints: int = 0,
) -> Path:
    """Create one current-schema package with Basic/reverse/Cloze cards."""

    path.parent.mkdir(parents=True, exist_ok=True)
    db_path = path.with_suffix(".sqlite")
    if raw_collection is None:
        connection = sqlite3.connect(db_path)
        unique_columns = (
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
        )
        unique_shapes = [
            *(tuple([column]) for column in unique_columns),
            *permutations(unique_columns, 2),
            *permutations(unique_columns, 3),
        ]
        note_constraints = "".join(
            f", UNIQUE({', '.join(columns)})"
            for columns in unique_shapes[:note_unique_constraints]
        )
        connection.executescript(
            f"""
            CREATE TABLE col (
                id integer primary key, crt integer, mod integer, scm integer,
                ver integer, dty integer, usn integer, ls integer,
                conf text, models text, decks text, dconf text, tags text
            );
            CREATE TABLE notes (
                id integer primary key, guid text, mid integer, mod integer,
                usn integer, tags text, flds text, sfld integer, csum integer,
                flags integer, data text{note_constraints}
            );
            CREATE TABLE cards (
                id integer primary key, nid integer, did integer, ord integer,
                mod integer, usn integer, type integer, queue integer, due integer,
                ivl integer, factor integer, reps integer, lapses integer,
                left integer, odue integer, odid integer, flags integer, data text
            );
            CREATE TABLE revlog (
                id integer primary key, cid integer, usn integer, ease integer,
                ivl integer, lastIvl integer, factor integer, time integer, type integer
            );
            CREATE TABLE graves (usn integer, oid integer, type integer);
            """
        )
        models = (
            _model(kind=kind, hostile_template=hostile_template)
            if models_override is None
            else models_override
        )
        decks = (
            {"1": {"id": 1, "name": deck_name, "desc": "", "dyn": 0}}
            if decks_override is None
            else decks_override
        )
        connection.execute(
            "INSERT INTO col VALUES (1,0,0,0,11,0,0,0,?,?,?,?,?)",
            ("{}", json.dumps(models), json.dumps(decks), "{}", "{}"),
        )
        fields = (
            f"{{{{c1::{front}}}}}\x1f{back}" if kind == "cloze" else f"{front}\x1f{back}"
        )
        connection.execute(
            "INSERT INTO notes VALUES (1001,'guid-one',1,0,0,?,?,0,0,0,'')",
            (tags, fields),
        )
        card_ords = (0, 1) if kind == "reverse" else (0,)
        for index, ord_value in enumerate(card_ords):
            connection.execute(
                "INSERT INTO cards VALUES (?,?,?,?,0,0,0,0,0,0,2500,0,0,0,0,0,0,'')",
                (2001 + index, 1001, 1, ord_value),
            )
        if extra_sql:
            connection.executescript(extra_sql)
        connection.commit()
        connection.close()
        collection_bytes = db_path.read_bytes()
        db_path.unlink()
    else:
        collection_bytes = raw_collection

    media = media or {}
    manifest = media_manifest
    if manifest is None:
        manifest = {str(index): name for index, name in enumerate(media)}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(collection_member, collection_bytes)
        archive.writestr("media", json.dumps(manifest, sort_keys=True).encode())
        for index, content in enumerate(media.values()):
            archive.writestr(str(index), content)
        for name, content in extra_members or []:
            archive.writestr(name, content)
    return path
