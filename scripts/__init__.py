# v0.8.68 — make scripts/ a regular package. The skillopt 0.1.0 wheel
# ships a top-level `scripts` package into site-packages (for its
# skillopt-train/skillopt-eval console entry points); under PEP 420 a
# regular package anywhere on sys.path shadows a namespace package, which
# broke `from scripts.benchmark_models import ...` in tests. With this
# __init__.py the repo's scripts/ is a regular package found first.
