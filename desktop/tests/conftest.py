"""v0.7.183 — desktop/tests conftest.

Four shim tests (test_memory_shim, test_piper_shim,
test_openchronicle_shim, test_whisper_shim) need `desktop/` on
sys.path so they can import `desktop_shims.X`. They do their own
`sys.path.insert(...)` at module load; this conftest is the central
place that documents the requirement.

Cross-suite pollution background — RESOLVED in v0.7.183:

  Previously, `desktop/` insertion would shadow the root `scripts/`
  package whenever pytest ran the combined `tests/ desktop/tests/`
  suite. `<repo>/desktop/scripts/` got resolved as the `scripts`
  package, so `from scripts.benchmark_models import ...` in
  `tests/test_v0_7_139.py` failed with ModuleNotFoundError. 17
  tests blew up.

  v0.7.183 fixed it by renaming `desktop/scripts/` →
  `desktop/dl_scripts/`. There's no namespace collision to fix
  with sys.path tricks — the fix is at the source.
"""
