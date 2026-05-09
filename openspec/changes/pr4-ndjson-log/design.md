## Context

PR1–3 shipped App composition, AppState, and the real fetch pipeline. PR4 makes operations observable: every fetch writes one structured record on disk, and standard Unix tools handle inspection. The dogfood gate from the project prompt lives here — within a week of PR4 merging, a2web should be the default fetch path in the Claude Code subagent flow.

The earlier proposal included an `a2web logs tail/grep/stats` CLI. Dropped: tail/grep/stats are convenience wrappers over `tail`, `grep`, `jq` — every Unix dev already knows them, and shipping our own surface means testing and documenting it forever for negligible value. The genuinely a2web-specific subcommand is `replay` (orchestrator-aware), and that lands in PR10.

The lifespan/TaskGroup work earlier design docs promised in PR4 is genuinely needed only for PR7 (browser pool, proxy health-check loop). PR3's per-fetch sqlite open/close works in both CLI and MCP modes; running it for one more PR costs ~5 ms per fetch and zero engineering hours. Building the lifespan hook with no consumer would mean shipping framework code we can't validate.

## Goals / Non-Goals

**Goals:**
- One NDJSON record per fetch on disk under `~/.a2web/logs/` (or `$A2WEB_LOG_DIR`).
- Rotation is size-based (default 16 MiB) with gzip; daily filename pattern (`fetches-YYYY-MM-DD.ndjson`).
- The fetch itself NEVER fails because the log write failed — best-effort write, with `operator_hint` on failure and a WARNING via `structlog`.
- Opt-out via `A2WEB_LOG_ENABLED=false` or YAML.
- All log paths route through `paths.py`; never hardcoded.
- README ships three jq one-liners covering the most-asked queries.
- `make check` green; coverage ≥85%.

**Non-Goals:**
- No `a2web logs` CLI (tail/grep/stats handled by stdlib Unix tools).
- No `a2web logs replay` (PR10).
- No `a2web logs prune` (operator's job; PR9 may revisit).
- No FastMCP lifespan / anyio TaskGroup — deferred to PR7 alongside browser/proxy pools.
- No log shipping (no syslog, no fluentd, no journald).
- No OTel traces in PR4 (PR6 wires OTel alongside the diagnostic event bus).
- No log encryption at rest.
- No PII redaction on URLs (documented; opt-out via `log_enabled=false`).

## Decisions

### Decision 1: NDJSON, not parquet / sqlite

NDJSON is human-grep-able, append-only, easy to rotate, easy to ship later. parquet would force a buffer-and-batch pattern we don't need; sqlite would conflict with the cache database. The cost of NDJSON's extra bytes (vs binary formats) is rounding error at v0.1 fetch volumes.

### Decision 2: Size-based rotation, daily filename, gzip on rollover

```
~/.a2web/logs/
  fetches-2026-05-09.ndjson           # active
  fetches-2026-05-09-01.ndjson.gz     # rolled (16 MiB, then gzipped)
  fetches-2026-05-09-02.ndjson.gz
  fetches-2026-05-08.ndjson.gz        # previous day, fully gzipped at midnight rollover
```

Daily prefix lets operators reason about retention by date; size cap prevents one busy day from creating a 1 GB file. Gzip on rollover means active file stays cheap to append (no compression overhead per write).

**Alternatives considered:**
- Daily-only rotation (one file per day) → busy days explode the file size. Rejected.
- Size-only rotation (no date suffix) → harder to reason about retention. Rejected.
- Per-fetch gzip (one gzipped record per line) → loses gzip's compression ratio. Rejected.

### Decision 3: `LogRecord` is module-scope dataclass; one canonical schema

```python
@dataclass(slots=True)
class LogRecord:
    ts: str                    # ISO 8601 UTC, millisecond precision
    url: str                   # input URL
    final_url: str             # post-redirect
    host: str
    tier: str
    status: str                # closed enum: ok | failed | partial
    verdict: str               # closed enum: dominant Verdict
    cache: str                 # hit | miss | bypass
    total_ms: int
    content_chars: int
    diagnostics: list[dict]    # compact per-step rows
    title: str | None
    error: str | None          # populated only when write/extract pathological
```

Anything richer (full body, full extracted markdown) belongs in a separate "trace" log we're not building yet. PR6 may add an `event_id` correlator when the diagnostic event bus lands.

### Decision 4: Best-effort writes; failures don't propagate

If `write_record` fails (disk full, permissions, fd limit), the fetch SHALL still return its `FetchResponse`. The orchestrator catches the writer's exception, appends an `operator_hint` (`code="log_write_failed"`, `message=...`), and moves on. We do NOT log the log failure to the log (obvious infinite loop); we route it to stderr at WARNING via `structlog`.

### Decision 5: Single in-process writer with an asyncio lock

The MCP server can have many concurrent fetches; CLI is single-shot. One `LogWriter` per `AppState`, an `asyncio.Lock` around the write+rotate critical section. Writes are serialized per-process; cross-process contention isn't relevant in v0.1 (one a2web instance per host).

### Decision 6: Lazy-open the file handle

`register_state` constructs the `LogWriter` but does NOT open the file. The first `write_record` call opens (creating the directory if needed). This avoids zombie zero-byte files on `a2web --help` and keeps `register_state` synchronous (file open is async via aiofiles).

### Decision 7: Rotation check inside `write_record`, not a background task

After each successful append, the writer checks `os.path.getsize(path)`. If it crosses the threshold, the writer closes the handle, renames the active file to `fetches-YYYY-MM-DD-NN.ndjson`, gzips it on a thread (`asyncio.to_thread(gzip.compress_file, ...)`), and reopens a fresh active file. This keeps the writer self-contained — no daemon task, no shutdown hook, no race condition on process exit.

### Decision 8: Reader is operator's stdlib of choice

No bundled CLI. README ships three jq one-liners for the common cases:

```bash
# Last 20 fetches
tail -n 20 ~/.a2web/logs/fetches-*.ndjson | jq

# All non-ok statuses by host
grep -h '"status":"failed"' ~/.a2web/logs/*.ndjson | jq -r '"\(.host)\t\(.verdict)"' | sort | uniq -c | sort -rn

# p50/p95 total_ms across the active log
jq -s 'sort_by(.total_ms) | {p50:.[(length*0.5|floor)].total_ms, p95:.[(length*0.95|floor)].total_ms}' ~/.a2web/logs/fetches-*.ndjson
```

If a query gets repetitive, operators wrap their own shell function or alias. If a pattern emerges across operators, PR9+ revisits.

## Risks / Trade-offs

- **[Risk] Log write contention slows fetches under high concurrency** → Mitigation: writes serialize on the asyncio lock; each write is an OS append (fast). v0.1 fetch volumes are low. Profile and revisit if PR8/9 reveals a hotspot.
- **[Risk] Disk fills up with logs** → Mitigation: documented as operator concern. Defaults: 16 MiB/file × ~365 days/year ≈ 6 GiB worst case. PR9 may add `prune`. For now, operators rotate manually.
- **[Risk] PII in URLs makes logs sensitive** → Mitigation: documented. Operators set `A2WEB_LOG_ENABLED=false` for sensitive flows. We do NOT auto-redact in v0.1 — heuristics here create more confusion than they solve.
- **[Risk] Lifespan deferral means PR7 has more lifecycle work** → Acknowledged. PR7 already needs the lifespan hook for browser pool teardown; bundling with the consumer is cleaner than shipping an unused hook in PR4.
- **[Risk] Rotation race on concurrent writes** → Mitigation: the writer's `asyncio.Lock` covers append + rotation atomically. Single-process serialization is fine for v0.1.
- **[Risk] aiofiles adds a dep on a relatively niche library** → Mitigation: aiofiles is widely used (8M+ downloads/month), maintained, and we use only its file API. The alternative — running every write in `asyncio.to_thread` — works too, but aiofiles is cleaner at the call site.

## Migration Plan

- New filesystem path under `~/.a2web/logs/`. Created on first write.
- No data migration. Existing installs continue to work; the log starts empty.
- Rollback: revert PR4 commits — the log directory becomes orphaned but harmless.
