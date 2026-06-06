"""Capture + refresh dev tooling and the shared cassette format.

Non-packaged: lives under `eval/`, never imported by `a2web.*`. The
read side (cassette + corpus loaders) is consumed by the replay harness
under `tests/eval_replay/`; the write side (capture/refresh) is driven by
the `make eval-capture` / `make eval-refresh` targets.
"""
