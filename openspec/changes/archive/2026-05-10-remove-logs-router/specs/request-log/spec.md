## REMOVED Requirements

### Requirement: Log reader iterates records from active and rolled files

**Reason**: PR10 shipped read-only convenience tools without the actual replay-from-stored-body feature, which was deferred. The reader added API surface area without delivering the high-value half of the dogfood loop. Removing it before v0.1 keeps the public contract small until a proper replay-from-cache implementation can land.

**Migration**: Read the NDJSON log directly with standard tools. The on-disk format and writer are unchanged.

```sh
# last record for a URL
jq 'select(.url=="https://example.com/x")' ~/.a2web/logs/fetches-*.ndjson | tail -n 1

# substring search (case-insensitive)
grep -i "paywall" ~/.a2web/logs/fetches-*.ndjson | tail -n 50

# rolled .gz files
zcat ~/.a2web/logs/fetches-*.ndjson.gz | jq 'select(.verdict=="block_page_detected")'
```

### Requirement: LogsRouter exposes replay / tail / grep

**Reason**: Removed alongside the reader. The `replay` / `tail` / `grep` MCP/CLI tools depended on `log/reader.py`, and shipping them without the body-replay payload made the v0.1 surface bigger than the value justified.

**Migration**: There are no shipped consumers. Use the shell-based recipes documented for the reader's removal above. A future change will reintroduce a router for replay only after body storage lands (tracked in `BACKLOG.md` as `PR10b — replay-from-cache`).
