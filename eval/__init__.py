"""a2web eval — dev/test layer, NOT part of the shipped `a2web` package.

Holds the replay-cassette format, capture/refresh dev tooling, and the
on-disk corpus loader. `a2web.*` MUST NOT import from this package
(enforced by `tests/architecture/test_eval_not_imported_by_a2web.py`):
evals are tests, and the product never depends on its own test harness.
"""
