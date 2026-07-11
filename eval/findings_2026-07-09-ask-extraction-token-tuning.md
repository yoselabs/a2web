# Findings — ask-extraction-token-tuning — 2026-07-09

**Scope:** `openspec/changes/ask-extraction-token-tuning` — `AskResponse.meta` allowlist, `genre` field removal, `EXTRACT_ROUTER_V1` token-efficiency + partial-signal-honesty prompt instructions.
**`make bench` status:** **deliberately skipped** — live-network, spends real LLM quota, and quota is tight this session. This doc covers what was verified without spending any, and what remains open until a bench run (or a live `ask` call) is affordable.

## What's verified — zero LLM cost

**`make check` (full gate):** lint clean, `ty` clean, `make arch` clean, 992 tests passed, 89.81% coverage (≥85% floor). Golden contracts re-blessed; diff reviewed and matches intent exactly — `ask_success_rich.json` drops `meta` (the blog.html fixture carries no allowlisted key), `tool_schemas.json` drops `genre` from both `AskResponse` and `RouterPayload` schemas.

**Live probe on the two original repro URLs, via `fetch_raw` (no LLM call) + the real `_curate_ask_meta` function in-process:**

- `androidheadlines.com` (the camera-redesign article): live raw `meta` is 18 keys. Run through `_curate_ask_meta` unchanged from the pipeline: drops to 2 (`og.description`, `og.site_name`). `og.title` — the duplicate of the promoted `title` field — is correctly excluded, as are all `og.image*`, `twitter.*`, `og.locale/type/url`, and `jsonld[0].@context`.
- `androidexperto.com` (the thin Lens-replacement article): raw `meta` is already `{}` (jina-tier fetch never parses HTML `<meta>` tags), so nothing to curate — consistent, no regression.
- `genre` absence is a pure schema/wire-shape fact (confirmed by `make check`'s contract snapshot), not something that needs a live re-probe — there is no code path left that can emit it.

## What's NOT verified — needs LLM quota

- **The partial-signal honesty fix itself.** The original bug was `ask`'s answer denying a topic ("the article does not address camera redesign") when the content had partial signal ("Camera" listed as a nav tab). That's model behavior, gated behind a live extraction call. Confirming the new `system` instruction actually changes the model's answer on this exact page requires a real `ask` call — not run here.
- **Token-cost / answer-quality axes** from `make bench`'s four-axis harness — not run.

## Recommendation

Treat this change as **code-complete and structurally verified**, but the actual prompt-tuning payoff (the reason this change exists) is unconfirmed until one of:
1. `make bench` is run when quota allows (ideally the crucial-subset form used in `eval/findings_2026-07-08.md`, not the full matrix, to keep cost down), or
2. A single live `ask` call against the androidheadlines URL, compared against the original transcript in this conversation.

Until then, this is a low-risk merge (wire-shape trims are provably correct; the prompt change is additive instruction text, not a schema change) but the headline claim — "the model now reports partial signal instead of denying the topic" — is asserted, not measured.
