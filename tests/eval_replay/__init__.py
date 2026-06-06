"""Deterministic replay harness — drives the real pipeline over frozen
cassettes. Lives in the test layer so `make check` collects it; makes no
live network, browser, or LLM call.
"""
