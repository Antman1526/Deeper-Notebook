# desktop/

Internals for the open-notebook-Plus desktop wrapper. See
[../docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md] for design and
[../docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md] for the implementation plan.

## Local build (developer)

```
pip install -r desktop/requirements.txt
cd frontend && npm ci && npm run build && cd ..
python desktop/build/fetch_runtimes.py
pyinstaller desktop/build/pyinstaller.spec
```

Output lands in `dist/open-notebook-Plus.app` (Mac) or `dist/open-notebook-Plus/` (Windows).
