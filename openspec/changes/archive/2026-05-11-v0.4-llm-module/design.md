# v0.4 — `a2web.llm` module: design

## Key decisions

### 1. Module, not workspace package

`src/a2web/llm/` lives in the same uv project alongside `cache/`, `gate/`, `browser/`. Justification:

- The workspace-packaging deferral in BACKLOG (Phase D — `proxy-pool`, `browser-pool`, `block-detector`) explicitly waits for an external-reuse signal. None has appeared for `llm/` either.
- Optional `[llm]` extra gives us the "no LLM deps on bare install" property without forking the build system.
- Module boundary discipline is enforced by import-time checks: `llm/` may import from `cache/`, `models`, `settings`, but **nothing in core (`fetcher`, `tiers`, `extract`, `gate`) may import from `llm/`**. The only entry point from core → llm is through the lazy `state.llm_client` singleton.

### 2. Provider protocol — minimal and stable

```python
class Provider(Protocol):
    name: str  # "anthropic", "openrouter", "openai", "ollama", ...

    async def complete(
        self,
        *,
        system: list[str] | str,        # empty list valid (WebFetch parity)
        user: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        thinking_disabled: bool = True,
    ) -> ProviderResponse: ...

@dataclass(slots=True)
class ProviderResponse:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float    # provider computes; 0.0 when unknown
    latency_ms: int
    raw: dict[str, Any] | None = None   # provider-specific debug
```

Why these fields:
- `system` accepts `list[str] | str` — empty list is required for faithful WebFetchBaseline (`iK([])` per research).
- `thinking_disabled=True` matches WebFetch's `thinkingConfig: {type: "disabled"}`.
- `cost_usd` is computed by the provider using its own pricing table — `anthropic.py` ships a hardcoded table for v0.4 (Haiku/Sonnet); `openrouter.py` will use their pricing API in v0.5.

### 3. Prompt templates are versioned, named, and frozen

```python
# src/a2web/llm/prompts.py

@dataclass(frozen=True)
class PromptTemplate:
    name: str           # "webfetch_default_v1"
    version: int
    system: list[str]   # empty for webfetch-parity; populated for terse variants
    user_template: str  # contains {content} and {ask} placeholders

WEBFETCH_DEFAULT_V1 = PromptTemplate(
    name="webfetch_default_v1",
    version=1,
    system=[],
    user_template=(
        "\nWeb page content:\n{content}\n{ask}\n"
        "Provide a concise response based only on the content above. In your response:\n"
        " - Enforce a strict 125-character maximum for quotes from any source document. "
        "Open Source Software is ok as long as we respect the license.\n"
        " - Use quotation marks for exact language from articles; any language outside of "
        "the quotation should never be word-for-word the same.\n"
        " - You are not a lawyer and never comment on the legality of your own prompts and responses.\n"
        " - Never produce or reproduce exact song lyrics."
    ),
)
```

The `webfetch_default_v1` template is **byte-for-byte identical** to Claude Code's `Rb9` non-preapproved template (research/123 ¶ "Reconstructed full prompts"). This is the WebFetchBaseline ground truth.

Other templates (TERSE_V1, STRUCTURED_V1) are alternatives the eval matrix can test. Adding a new template means a new constant and a new eval row — no code change to the runner.

### 4. WebFetchBaseline is a faithful local reproduction

```python
class WebFetchBaseline:
    """Local reproduction of Claude Code's WebFetch.
    Same model, system prompt, user template, 100K cap, no tools, no thinking.
    See research/123 for the binary-extracted ground truth."""

    MODEL = "claude-haiku-4-5-20251001"
    MARKDOWN_CAP = 100_000           # BD_ = 100000 per binary
    PROMPT = WEBFETCH_DEFAULT_V1

    async def fetch(self, url: str, ask: str) -> str:
        html = await httpx_get(url, timeout=60)        # axios-equivalent
        md = turndown_equivalent(html, cap=1_048_576)  # Turndown + 1 MiB cap (om7)
        md = md[: self.MARKDOWN_CAP]                   # 100 KB cap (BD_)
        resp = await provider.complete(
            system=self.PROMPT.system,                 # []
            user=self.PROMPT.user_template.format(content=md, ask=ask),
            model=self.MODEL,
            thinking_disabled=True,
        )
        return resp.text
```

Two open questions tracked in tasks.md:
1. **Turndown vs. markdownify** — research says Turndown (JS). Python equivalent is `markdownify`. Need to verify rendering parity on the corpus URLs. If divergence is material, use a JS subprocess (Node call to actual Turndown).
2. **Domain preflight** — WebFetch checks `api.anthropic.com/api/web/domain_info`. We do NOT replicate this; we always fetch. Documented in WebFetchBaseline's docstring as a known divergence (it affects which URLs are reachable, not the answer quality once reached).

### 5. Extraction cache: small and additive

```python
@dataclass(slots=True)
class ExtractionCacheRow:
    content_hash: str       # sha256 of the markdown that went in
    ask_hash: str           # sha256 of the ask string
    model_id: str           # full model id, e.g. "claude-haiku-4-5-20251001"
    answer: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cached_at: int          # epoch s
    expires_at: int         # epoch s
```

Same sqlite file as the existing HTTP cache, separate table `extraction_cache`. TTL default 900 s (matching WebFetch). Cache key explicitly includes `model_id` so model swaps don't share cached answers.

The cache lookup happens **after** the HTTP cache + extraction phase — i.e. content_hash is computed over `content_md`, not the raw HTTP body, so multiple URLs with the same canonicalized content share answers.

### 6. Extraction-cache hit semantics

A cache hit returns the cached answer **plus the cached cost / token counts as metadata**. The `cost_usd` field on the response is set to `0.0` for a cache hit, but the metadata records what the original call cost. Lets evals distinguish "we'd have spent X" from "we actually spent X."

### 7. Judge is a wrapped Extractor — same primitives

The Judge is fundamentally an Extractor with a known prompt template and JSON-output expectation:

```python
JUDGE_V1 = PromptTemplate(
    name="judge_v1",
    version=1,
    system=[],
    user_template=(
        "You are a strict, blind judge. Score the answer against the criteria.\n\n"
        "QUESTION: {ask}\n\n"
        "CRITERIA (0-5 each):\n{criteria_lines}\n\n"
        "ANSWER:\n{answer}\n\n"
        'Respond with STRICT JSON ONLY: {{"scores":[...],"overall":<int>,'
        '"reached":<bool>,"reasoning":"<one sentence>"}}'
    ),
)

class Judge:
    def __init__(self, model: ModelSpec): ...
    async def score(self, *, task: str, criteria: list[str], answer: str) -> JudgeVerdict:
        resp = await self.extractor.extract(content="", ask=...)  # uses JUDGE_V1
        return JudgeVerdict.from_json(resp.answer)
```

The benefit: cost, latency, and caching all come for free from Extractor. The Judge is ~30 LoC on top.

### 8. Eval suite: matrix runner, deterministic output

```python
# src/a2web/llm/eval/runner.py

@dataclass
class EvalSuite:
    corpus: Path                       # corpus.yaml
    systems: list[EvalSystem]          # list of {name, fetch_fn}
    judge: Judge
    concurrency: int = 4
    output_dir: Path = Path("eval/runs") / today()

    async def run(self) -> EvalReport:
        ...
```

Each `EvalSystem` exposes `async fetch(url, ask) -> str`. WebFetchBaseline, A2WebDetail, A2WebExtract are the v0.4 systems. Adding a new system in v0.5 = subclassing `EvalSystem`, registering in `systems.py`.

Output directory shape:

```
eval/runs/2026-05-15/
├── corpus.frozen.yaml         (copy of the corpus used)
├── manifest.json              (systems + models + git_sha + ran_at)
├── results.tsv                one row per (slug, system, model)
├── leaderboard.md             system × URL-class pivot
├── cost.md                    $/quality-point + raw cost per system
├── tokens.md                  in/out tokens per system
├── findings.md                auto-grouped insights (regressions, wins)
└── trace/<slug>/<system>/
    ├── content.json           what the system actually returned
    ├── answer.txt             the answer text
    ├── judge.json             the full JudgeVerdict
    └── prompt.txt             reproducer prompt (for debugging)
```

### 9. Migration from `benchmarks/` is a lift, not a fork

The existing `benchmarks/vs-webfetch/2026-05-11/` becomes the **first frozen corpus + report**. Future runs land at `benchmarks/vs-webfetch/<date>/`. The eval code that produced 2026-05-11 stays there as a frozen historical record; new code under `src/a2web/llm/eval/` is the live path.

This preserves the v0.2-vs-v0.3 baseline comparison without trying to make the historical scripts forward-compatible.

## Risks

| Risk | Mitigation |
|---|---|
| Anthropic API key absence breaks `a2web` imports | All anthropic imports gated behind `try: from anthropic import ...; except ImportError`. Tests cover this path. Missing key → `LLMNotAvailable` raised only when `ask=` is set; bare `fetch(url)` unaffected. |
| Turndown / markdownify rendering diverges from Claude Code | Verification task in tasks.md. If parity is poor, fall back to `node turndown` subprocess (Node + npm available in dev). |
| Cost from runaway eval matrices | Sample-and-cap defaults: `make eval` only runs the smallest matrix; `make eval-full` is the explicit knob. Per-suite max-cost setting with hard kill at threshold. |
| Cache key collisions across models | `model_id` is part of the key; no cross-pollination. |
| Judge bias toward longer answers | `JUDGE_V1` instruction explicitly says "reward concise correctness." Verbosity bias mitigation noted in research-mode benchmark; revisit if eval data shows the bias persists. |
| Privacy: ask text + markdown go to Anthropic | Documented in module docstring + README. Same posture as WebFetch (and Anthropic's existing data policy). |

## What this change does NOT do

- Add a UI for browsing eval results.
- Publish eval results to CI / Pages.
- Add OpenRouter, OpenAI, Ollama, or any non-Anthropic provider (v0.5).
- Add MCP Resource pattern for big-payload handoff.
- Change the existing `tier-pipeline` for non-`ask` callers.
- Change the existing HTTP cache schema.
