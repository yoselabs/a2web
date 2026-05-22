"""Firefox cookie reader test — hand-built `cookies.sqlite` under a fake profile.

Never touches the user's real Firefox. We construct a profile directory with
a synthetic `moz_cookies` table and patch the reader's profile root to point
at it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from a2web.packages.cookie_store import firefox
from a2web.packages.cookie_store.models import ChromeCookieAccessError


def _make_profile(tmp_path: Path, name: str = "abc123.default-release") -> Path:
    root = tmp_path / "Profiles"
    pdir = root / name
    pdir.mkdir(parents=True)
    db = pdir / "cookies.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE moz_cookies (
            id INTEGER PRIMARY KEY,
            host TEXT,
            name TEXT,
            value TEXT,
            path TEXT,
            expiry INTEGER,
            isSecure INTEGER,
            isHttpOnly INTEGER,
            sameSite INTEGER
        )
        """,
    )
    conn.executemany(
        "INSERT INTO moz_cookies (host, name, value, path, expiry, isSecure, isHttpOnly, sameSite) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (".example.com", "sid", "abc", "/", 9999999999, 1, 1, 1),
            ("other.com", "tracker", "xyz", "/", 0, 0, 0, 0),
        ],
    )
    conn.commit()
    conn.close()
    return root


def test_read_cookies_normalizes_rows(tmp_path, monkeypatch) -> None:
    root = _make_profile(tmp_path)
    monkeypatch.setattr(firefox, "_profiles_root", lambda: root)
    rows = firefox.read_cookies("default-release")
    by_name = {r.name: r for r in rows}
    assert set(by_name) == {"sid", "tracker"}
    assert by_name["sid"].host_key == ".example.com"
    assert by_name["sid"].value == "abc"
    assert by_name["sid"].is_secure == 1
    assert by_name["sid"].is_httponly == 1
    assert by_name["sid"].samesite == "lax"
    assert by_name["sid"].expires_utc == 9999999999
    # Session cookies (expiry==0) map to None
    assert by_name["tracker"].expires_utc is None
    assert by_name["tracker"].is_secure == 0
    assert by_name["tracker"].samesite == "none"


def test_resolve_alias_picks_lex_first(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Profiles"
    (root / "zzz.default-release").mkdir(parents=True)
    (root / "aaa.default-release").mkdir(parents=True)
    # Put a sqlite under the aaa profile so the lex-first match is the one read.
    db = root / "aaa.default-release" / "cookies.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, host TEXT, name TEXT, value TEXT, "
        "path TEXT, expiry INTEGER, isSecure INTEGER, isHttpOnly INTEGER, sameSite INTEGER)",
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(firefox, "_profiles_root", lambda: root)
    # Should resolve to aaa.* and not fail (zzz has no sqlite).
    rows = firefox.read_cookies("default-release")
    assert rows == []


def test_missing_profile_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(firefox, "_profiles_root", lambda: tmp_path / "nope")
    with pytest.raises(ChromeCookieAccessError):
        firefox.read_cookies("default")


def test_direct_dir_name(tmp_path, monkeypatch) -> None:
    root = _make_profile(tmp_path, name="abc123.default-release")
    monkeypatch.setattr(firefox, "_profiles_root", lambda: root)
    rows = firefox.read_cookies("abc123.default-release")
    assert len(rows) == 2
