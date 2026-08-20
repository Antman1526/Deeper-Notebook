"""Brand metadata in generated Office packages without changing their content."""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path

from deeper_notebook.identity import PRODUCT_NAME

_APPLICATION = re.compile(
    rb"(<Application>).*?(</Application>)",
    flags=re.DOTALL,
)


def brand_office_application(path: Path) -> None:
    """Set the OOXML extended-properties application to Deeper Notebook."""
    with zipfile.ZipFile(path, "r") as package:
        entries = [(info, package.read(info.filename)) for info in package.infolist()]

    branded_entries: list[tuple[zipfile.ZipInfo, bytes]] = []
    changed = False
    for info, data in entries:
        if info.filename == "docProps/app.xml":
            data, replacements = _APPLICATION.subn(
                rb"\1" + PRODUCT_NAME.encode("utf-8") + rb"\2",
                data,
                count=1,
            )
            if replacements != 1:
                raise ValueError("Office package application metadata is missing")
            changed = True
        branded_entries.append((info, data))
    if not changed:
        raise ValueError("Office package has no extended application metadata")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(temporary_path, "w") as package:
            for info, data in branded_entries:
                package.writestr(info, data)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = ["brand_office_application"]
