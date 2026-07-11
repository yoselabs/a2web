"""Suggestion-uptake telemetry (openspec `surface-page-links-to-extractor` 8.2).

Offline unit tests over the free functions in `a2web.uptake`, driven against a
throwaway in-memory sqlite connection — no App, no fetch, no network.
"""

from __future__ import annotations

import aiosqlite
import pytest

from a2web.uptake import note_visit, record_suggestions


@pytest.fixture
async def conn():
    async with aiosqlite.connect(":memory:") as c:
        yield c


async def test_record_then_visit_counts_follow_through(conn: aiosqlite.Connection) -> None:
    # An ask on a product page suggests its reviews page.
    stored = await record_suggestions(
        conn,
        source_url="https://shop.example/p/widget",
        question="summarize the reviews",
        targets=[("https://shop.example/p/widget-yorumlari", False)],
    )
    assert stored == 1

    # A LATER ask fetches exactly that suggested URL → one suggestion fulfilled.
    assert await note_visit(conn, "https://shop.example/p/widget-yorumlari") == 1
    # Idempotent: the same visit does not re-count a closed suggestion.
    assert await note_visit(conn, "https://shop.example/p/widget-yorumlari") == 0


async def test_visit_of_unsuggested_url_is_zero(conn: aiosqlite.Connection) -> None:
    await record_suggestions(
        conn,
        source_url="https://a.example",
        question="q",
        targets=[("https://a.example/reviews", False)],
    )
    assert await note_visit(conn, "https://elsewhere.example/never-suggested") == 0


async def test_correlation_is_slash_and_fragment_insensitive(conn: aiosqlite.Connection) -> None:
    await record_suggestions(
        conn,
        source_url="https://a.example",
        question="q",
        targets=[("https://a.example/reviews/", False)],  # stored with trailing slash
    )
    # Caller fetches the same page without the slash and with a fragment.
    assert await note_visit(conn, "https://a.example/reviews#top") == 1


async def test_empty_targets_store_nothing(conn: aiosqlite.Connection) -> None:
    assert await record_suggestions(conn, source_url="u", question=None, targets=[]) == 0
    # Blank urls are dropped, not stored.
    assert await record_suggestions(conn, source_url="u", question=None, targets=[("", True)]) == 0


async def test_off_domain_flag_persists(conn: aiosqlite.Connection) -> None:
    await record_suggestions(
        conn,
        source_url="https://a.example",
        question="q",
        targets=[("https://cdn.other.example/spec.pdf", True)],
    )
    async with conn.execute("SELECT off_domain FROM a2web_url_suggestions") as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == 1


async def test_multiple_open_suggestions_of_same_target_all_close(conn: aiosqlite.Connection) -> None:
    # Two separate asks both suggested the same continuation URL.
    for src in ("https://a.example/1", "https://a.example/2"):
        await record_suggestions(conn, source_url=src, question="q", targets=[("https://a.example/next", False)])
    # One visit fulfils both prior suggestions.
    assert await note_visit(conn, "https://a.example/next") == 2
