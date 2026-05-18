"""ONP v0.7.120 — Cross-cutting HTTP middlewares.

Split out of api/main.py so each middleware (request-id, security
headers, gzip wiring) can be unit-tested in isolation and so main.py
doesn't grow past the "fits in one head" threshold.
"""
