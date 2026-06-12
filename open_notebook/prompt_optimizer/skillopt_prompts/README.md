Prompt templates vendored verbatim from microsoft/SkillOpt
(https://github.com/microsoft/SkillOpt, MIT License), commit state of
2026-06-11. The skillopt 0.1.0 wheel omits these package-data files, so
`load_prompt()` raises FileNotFoundError at the reflection/aggregate
stages. `ensure_skillopt_prompts()` in ../runner.py backfills any file
missing from the installed package at run start — existing files are
never overwritten, so a fixed upstream wheel automatically wins.
