# desktop/

Internals for the Deeper Notebook desktop wrapper. The linked legacy design and
implementation plan retain their shipped names for historical accuracy. See
[../docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md] for design and
[../docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md] for the implementation plan.

## Local build (developer)

```
pip install -r desktop/requirements.txt
cd frontend && npm ci && npm run build && cd ..
python desktop/build/fetch_runtimes.py
pyinstaller desktop/build/pyinstaller.spec
```

Output lands in `dist/Deeper Notebook.app` (macOS) or
`dist/Deeper Notebook/` (Windows).

## Release artifacts

The desktop version in `desktop/__init__.py` is intentionally separate from the
upstream server/package version in `pyproject.toml`.

- macOS builds produce `Deeper-Notebook-mac-<arch>.dmg`.
- Windows builds produce both `Deeper-Notebook-windows-x64.zip` and
  `Deeper-Notebook-Setup-x64.exe`. Both contain the full PyInstaller onedir
  bundle; the launcher executable is never distributed by itself.
- The Windows installer is compiled with Inno Setup 6.7.1. It installs per user,
  creates a Start Menu shortcut, upgrades the stable application ID in place,
  and supplies an uninstaller.

For every distributable artifact, generate an adjacent `release-manifest.json`
and `SHA256SUMS` after packaging:

```bash
python desktop/build/release_manifest.py \
  --artifact dist/Deeper-Notebook-mac-arm64.dmg \
  --platform macos --arch arm64 \
  --output dist/release-manifest.json
shasum -a 256 dist/Deeper-Notebook-mac-arm64.dmg > dist/SHA256SUMS
```

CI runs the backend and frontend quality gates before packaging. The Windows
job additionally installs the setup package silently into a temporary folder,
checks that the installed launcher remains running briefly, repeats the install
to exercise the upgrade path, then uninstalls it.
