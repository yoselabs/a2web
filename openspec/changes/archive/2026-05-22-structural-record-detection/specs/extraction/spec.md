## MODIFIED Requirements

### Requirement: Multi-source extraction escalation ladder

After `extract_markdown` returns, `_phase_extract` SHALL run an ordered ladder of structured-extraction sources **unconditionally** — there is no recall trigger gating entry to the ladder. Each rung self-gates: it produces output only when its own preconditions hold — `json_in_script` only when embedded JSON is present; structural record extraction only when a record region clears the `record-extraction` detection guards. The ladder runs in order: (1) `json_in_script` payloads (embedded JSON, including JSON-LD); (2) structural record extraction via the `record-extraction` capability. The ladder stops at the first rung whose output passes the quality-aware replace check. When no rung produces a passing result, the cascade SHALL leave `content_md` unchanged and fall through, so the orchestrator's existing browser-tier escalation still applies. Each rung SHALL emit `StageStarted` / `StageEnded` LDD events naming the source.

#### Scenario: Ladder runs without a trigger

- **WHEN** `extract_markdown` returns for any page
- **THEN** the escalation ladder runs, and each rung self-gates on its own preconditions

#### Scenario: Embedded JSON is tried first

- **WHEN** the raw HTML carries embedded JSON
- **THEN** the `json_in_script` source is attempted first and, if its output passes the replace check, the ladder stops

#### Scenario: Server-rendered listing reaches record extraction

- **WHEN** the raw HTML is a server-rendered listing with no embedded JSON
- **THEN** the `json_in_script` source yields nothing and the structural record-extraction source runs

#### Scenario: Article reaches the record rung and it self-gates

- **WHEN** the page is a genuine article
- **THEN** the structural record-extraction rung runs, returns no record set, and `content_md` is left unchanged

#### Scenario: No source passes — clean fall-through

- **WHEN** no ladder rung produces a passing result
- **THEN** `content_md` is left unchanged and the cascade falls through to the orchestrator's browser-tier escalation

### Requirement: Quality-aware content replacement

A ladder source's output SHALL replace `content_md` only when it is a higher-quality result than trafilatura's output. For structural record extraction the replace decision SHALL be **depth-aware**: a **threaded** record set (maximum nesting depth > 0) SHALL replace `content_md` whenever the detector produced one — trafilatura cannot represent threading, so rendered length is not a quality proxy for it; a **flat** record set (depth 0) SHALL replace `content_md` only when its rendered length exceeds trafilatura's output. A good article SHALL NOT be clobbered: an article yields no record set because the `record-extraction` detection guards reject it, so the replace check is never reached. A `json_in_script` source SHALL replace `content_md` when its synthetic output exceeds trafilatura's output in length.

#### Scenario: Threaded record set replaces a flattened wall

- **WHEN** structural record extraction produces a threaded (depth > 0) record set on a page trafilatura flattened into an undifferentiated wall of text
- **THEN** the threaded render replaces `content_md` even if it is shorter than trafilatura's output

#### Scenario: Flat catalog replaces on length

- **WHEN** structural record extraction produces a flat (depth 0) record set whose rendered length exceeds trafilatura's output
- **THEN** it replaces `content_md`

#### Scenario: A good article is never clobbered

- **WHEN** the page is an article
- **THEN** the record-extraction guards reject it, no record set is produced, and `content_md` keeps trafilatura's output

## REMOVED Requirements

### Requirement: Recall-based escalation trigger

**Reason**: The recall trigger was a text-*volume* ratio (`content_md` length vs. visible-text length), structurally blind to *structure* loss. trafilatura can keep ~all of a page's text while flattening a listing into an undifferentiated wall — volume recall ≈ 1.0 — so the trigger stayed silent on exactly the text-heavy listing markup it most needed to catch (the lobste.rs homepage measured a recall ratio of 0.99).

**Migration**: The trigger is removed entirely. The escalation ladder now runs **unconditionally** and each rung self-gates — `extract_records` returning a `RecordSet` is itself the "this page is a listing" classification (see the modified `Multi-source extraction escalation ladder` and the `record-extraction` detection guards). The near-empty → browser-tier path is unaffected: the gate's existing length floor drives `suggested_tier`. `trafilatura_under_extracted`, `_visible_text_length`, and the ratio constants are deleted from `domain.py`.
