# Design — terse query grammar

## D1. The query is defined by deletion, not by syntax

The cheapest grammar to describe is one whose operators the model *already knows for free* from training: natural language + Google-search conventions. So the grammar is **subtractive** — a deletion rule, not a DSL:

```
query  =  the question with the scaffolding deleted

  DROP   the verb frame        "does it" / "are there any" / "do any reviews mention"
  DROP   the entity you are     (refine items re-ask on the SAME url — never re-name it)
         already looking at
  KEEP   the target noun(s)     reviews · firmware version · connection issues
  KEEP   the discriminator      a contrast (vs) · a qualifier (OFFICIAL) · a list (,)
```

Nothing is a syntax the caller must learn. `,` `vs` `/` `"exact"` `-exclude` all read correctly with zero explanation because Google trained everyone. That is what keeps the tool description tiny.

## D2. Operators (only free-prior ones) + one emphasis rule

```
  ,      a set / list         battery, latency, false-triggers
  vs     a fork / contrast    Apple Home only vs all platforms
  /      alternatives         troubleshooting / known issues
  CAPS   the load-bearing     OFFICIAL pairing steps  ·  setup steps ONLY in working reviews
         word (skim-proof)    (one token, rarely two — if all-caps, nothing is emphasized)
```

CAPS over `**bold**`: ~free on tokens, reads as salience to an LLM. Whether CAPS *measurably* helps is **Spike B** — prescribe it narrowly or not at all based on the result.

## D3. FIND vs DECIDE — the one place a question survives

```
  FIND    → phrase, no question     battery, latency, false-trigger rates
  DECIDE  → keep a "?"              Apple Home only vs all platforms?
```

`refine` items are almost always FIND (retrieve from the same page). Keep `?` only when asking `query` to *judge/determine which*, so the extractor picks rather than dumps both sides.

## D4. Worked corpus (the four structural shapes)

```
shape       original (question)                                   query grammar
FORK        Does it work with Apple Home specifically, or do      connection issues:
            connection issues affect all platforms equally?       Apple Home only vs all platforms
COMPOUND    What firmware are failing units running, AND do       firmware version of failing units
            successful reviews mention setup steps failing        setup steps ONLY in working reviews
            ones don't?                                           (split: `and` == two queries)
QUALIFIER   Are there any official troubleshooting steps or       OFFICIAL troubleshooting / known
            known issues documented for pairing?                  issues for pairing
LIST        Do any reviews mention battery life, response         battery, latency, false-trigger rates
            latency, or false-positive trigger rates?
```

~55 words → ~22, forks/qualifiers/lists intact; the naive-keyword column destroys FORK and QUALIFIER.

## D5. Tool description strawmen (Spike C decides length)

```
LEAN (~15 words)
  query — a concrete, terse search query for what you want from the page, not a full sentence.

FAT (~50 words)
  query — what you want from the page, as a search query, not a polite question. Drop
  "does/are there/do any" and the page's own subject; keep the target and any word that
  narrows it. Commas list; `vs` contrasts; CAPS the one word that decides. Keep a "?" only
  when asking to judge, not find.
```

## D6. Naming cascade — decision: full cascade

Decided this session (accepting the breakage cost):

```
  tool    ask         → query
  param   question    → query
  field   ask_here    → refine     (refine keeps "narrow further, here"; `queries` loses locality)
```

`fetch_raw` / `refresh` unchanged. Cost: breaks MCP contract, `canonical_name_override` pins, `~/.claude.json`, all installed callers — hence gated behind the parallel feature and applied as a deliberate version bump.

## D7. Validation — spikes, not a full bench (and never on metered API)

The thing shipped is the *description + field semantics*, so the spikes test those. They reuse the existing harness (corpus, Judge, four axes) but MUST run on the subscription/cheap provider from the sibling `bench-cost-isolation` change, and MUST use its per-item / per-axis isolation so each spike is a handful of calls, not the full ~80-Sonnet-call matrix.

```
SPIKE A — does terseness cost extraction fidelity?
  hold URL + info-need fixed; vary phrasing over {full-sentence, query-grammar, bare-keyword}
  ~8–10 items spanning the four shapes (fork · compound · qualifier · list)
  measure: Judge answer-quality + token cost
  H: query-grammar ≥ sentence on quality, < on cost; bare-keyword DROPS quality on fork + qualifier

SPIKE B — does CAPS emphasis actually help?
  fork + qualifier subset only; A/B pivot word CAPS'd vs not
  measure: does the answer RESPECT the constraint (one rubric bit)
  H: helps on qualifier, neutral on list → prescribe narrowly or not at all

SPIKE C — lean vs fat description (the real ship test)
  model GENERATES queries from each description for a set of info-needs; run those through Spike A
  measure: which description yields higher-fidelity queries
  H: lean within noise of fat → ship lean, save the description tokens
```

**Deferred (needs multi-turn eval):** whether terse queries make the calling agent fetch *fewer times* — the real token economy — the single-shot harness cannot see this. Note it; do not fake it.
