# Surface eval v2 — FINAL router-shape design pre-impl check

Model: `claude-haiku-4-5` · max_tokens=1024 · thinking disabled

Single prompt (EXTRACT_ROUTER_V1 from refactor-ask-to-router-shape openspec).
13 URLs including 4 discussion-shape pages (hn-thread, so-yield, lobste, reddit, blog-julia).


---

## 1. paper-abs

`https://arxiv.org/abs/2402.17753`

Q: **what does the paper claim in 2 sentences?**  ·  expected_shape=`prose`, expected_genre=`paper`

Fetch: tier=`raw` · status=`ok` · chars=3170

### · 10204 ms · $0.01411

shape miss: got `key-value`, expected `prose`

```json
{
  "answer": "The paper introduces LoCoMo, a dataset of very long-term conversations (300 turns, 9K tokens avg., up to 35 sessions) with human-verified consistency, and presents a comprehensive benchmark to evaluate LLM memory on QA, event summarization, and multi-modal dialogue tasks. Results show LLMs struggle with lengthy conversations and long-range temporal/causal dynamics, with improvements from long-context LLMs or RAG still substantially below human performance.",
  "structural_form": "reference",
  "shape": "key-value",
  "genre": "paper",
  "ask_here": [
    "What specific memory capabilities (e.g., recall of early sessions, temporal ordering, entity tracking) does LoCoMo isolate as failure modes?",
    "How does RAG performance compare to long-context LLMs on the same tasks?",
    "What is the inter-annotator agreement on the human-verified long-range consistency edits?"
  ]
}
```

---

## 2. hn-front

`https://news.ycombinator.com/`

Q: **what are the top 3 most-discussed posts right now?**  ·  expected_shape=`records`, expected_genre=`community`

Fetch: tier=`site_handler:hn` · status=`ok` · chars=6942

### · 10145 ms · $0.01773

```json
{
  "answer": "The top 3 most-discussed posts by comment count are: (1) **Memory has grown to nearly two-thirds of AI chip component costs** (311 comments), (2) **Time to talk about my writerdeck** (277 comments), and (3) **I spent 50 hours drawing a line graph** (74 comments, tied with DeepSeek reasonix at 197 comments — actually **DeepSeek reasonix** is #3 with 197 comments).",
  "structural_form": "listing",
  "shape": "records",
  "genre": "news",
  "ask_here": [
    "Which of these discussions surfaced the most substantive technical critique or pushback?",
    "Do the writerdeck and line-graph posts represent a particular community sentiment about tooling or documentation?",
    "What specific aspects of AI chip memory costs drove the high engagement in that thread?"
  ]
}
```

---

## 3. hn-thread

`https://news.ycombinator.com/item?id=39745700`

Q: **what is the most-upvoted criticism in this thread?**  ·  expected_shape=`discussion`, expected_genre=`community`

Fetch: tier=`site_handler:hn` · status=`ok` · chars=15211

### · 10396 ms · $0.01988

```json
{
  "answer": "The most-upvoted criticism is implicit in the question about total tokens trained. The commenter 'adt' estimates ~3B tokens (at 8:1 ratio), highlighting that the author lacks scientific rigor and exact metrics for a research project—a significant gap for reproducibility and benchmarking claims.",
  "structural_form": "thread",
  "shape": "discussion",
  "genre": "community",
  "ask_here": [
    "Do commenters challenge the model's actual capabilities or benchmarks against comparable tiny models?",
    "Are there objections to the dataset choices, synthetic-only training, or lack of RLHF/DPO?",
    "Does anyone critique the architectural decisions (GQA depth, ALiBi max token limit, etc.)?",
    "What's the consensus on whether sub-400M params can meaningfully advance research vs. toy status?",
    "Do commenters question reproducibility given the author's admission of non-scientific methods and deleted models?"
  ]
}
```

---

## 4. mdn-array

`https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array`

Q: **how do you remove the last element of an array in javascript?**  ·  expected_shape=`mixed`, expected_genre=`official`

Fetch: tier=`raw` · status=`ok` · chars=40505

### · 9275 ms · $0.01950

```json
{
  "answer": "Use the `pop()` method to remove the last element: `arr.pop()`. Alternatively, use non-mutating methods like `arr.slice(0, -1)` to create a new array without the last element, or set `arr.length = arr.length - 1` to remove it in-place.",
  "structural_form": "reference",
  "shape": "mixed",
  "genre": "official",
  "ask_here": [
    "What's the difference in behavior between `pop()` and `slice(0, -1)` when the array is empty?",
    "Do mutating vs non-mutating removal methods have performance implications for large arrays?",
    "How do empty slots affect `pop()` and other removal methods?"
  ]
}
```

---

## 5. rfc-9110-idempotent

`https://datatracker.ietf.org/doc/html/rfc9110`

Q: **what does the spec say about idempotent methods?**  ·  expected_shape=`prose`, expected_genre=`spec`

Fetch: tier=`raw` · status=`ok` · chars=403182

### · 9978 ms · $0.01864

shape miss: got `mixed`, expected `prose`

```json
{
  "answer": "RFC 9110 does not contain a section explicitly discussing idempotent methods. The document covers HTTP semantics, architecture, and core protocol elements, but the fetched content ends abruptly mid-sentence in Section 2.2 and does not reach the section on request methods (Section 9) where such semantics would be defined.",
  "structural_form": "reference",
  "shape": "mixed",
  "genre": "spec",
  "try_url": [
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc9110#section-9",
      "reason": "Section 9 defines request methods and their semantics, including idempotency guarantees"
    },
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc9110#section-9.2",
      "reason": "Common method definitions (GET, PUT, DELETE, etc.) explicitly note idempotency properties"
    }
  ]
}
```

---

## 6. so-yield

`https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python`

Q: **what is the accepted answer?**  ·  expected_shape=`discussion`, expected_genre=`community`

Fetch: tier=`raw` · status=`ok` · chars=38038

### · 10476 ms · $0.02029

```json
{
  "answer": "The accepted answer explains that `yield` is used to create generators—functions that return a \"lazy pending list\" object. When Python detects `yield` in a function, that function returns a generator (an iterable) rather than a single value. Each time `yield` is encountered, the function returns a value but preserves its state; the next call resumes execution from where it left off, making generators memory-efficient for producing sequences.",
  "structural_form": "thread",
  "shape": "discussion",
  "genre": "community",
  "ask_here": [
    "What are the memory/performance advantages of generators over building complete lists?",
    "How do generators handle `send()` and `throw()` for bidirectional communication (coroutine behavior)?",
    "What's the practical difference between `yield` and `return` in a generator function?",
    "How does `yield from` in Python 3 differ from chaining multiple generators?",
    "Can a generator function be used multiple times, or does it exhaust after one iteration?"
  ]
}
```

---

## 7. gh-httpx-readme

`https://github.com/encode/httpx`

Q: **how do I install httpx and make a basic GET request?**  ·  expected_shape=`mixed`, expected_genre=`official`

Fetch: tier=`site_handler:github` · status=`ok` · chars=5317

### · 9960 ms · $0.01660

```json
{
  "answer": "Install httpx with `pip install httpx`, then import and use it: `import httpx; r = httpx.get('https://www.example.org/'); r.status_code`. For HTTP/2 support, use `pip install httpx[http2]`. HTTPX requires Python 3.9+.",
  "structural_form": "product",
  "shape": "mixed",
  "genre": "official",
  "ask_here": [
    "What async APIs does HTTPX provide and how do I use them?",
    "How do I configure timeouts, authentication, and proxy settings?",
    "Can HTTPX make requests directly to WSGI/ASGI applications, and how?",
    "What are the differences between HTTPX and the requests library?",
    "How do I use sessions with cookie persistence in HTTPX?"
  ],
  "try_url": [
    {
      "url": "https://www.python-httpx.org/quickstart/",
      "reason": "official quickstart guide with runnable examples for common patterns"
    },
    {
      "url": "https://www.python-httpx.org/async/",
      "reason": "async API documentation if user needs concurrent requests"
    },
    {
      "url": "https://www.python-httpx.org/advanced/",
      "reason": "advanced usage covering sessions, transports, timeouts, auth"
    }
  ]
}
```

---

## 8. pydantic-releases

`https://github.com/pydantic/pydantic/releases`

Q: **what changed in the latest pydantic release?**  ·  expected_shape=`records`, expected_genre=`official`

Fetch: tier=`raw` · status=`ok` · chars=10503

### · 11758 ms · $0.02212

```json
{
  "answer": "The latest Pydantic release is v2.14.0a1 (2026-05-22), a pre-release alpha. Key changes: PyEmscripten platform tag support for Pyodide 314.0+, and acceptance of None in MultiHostUrl. The stable latest is v2.13.4 (2026-05-06), which includes packaging updates (libc 0.2.155→0.2.185, macOS linker flag fixes) and fixes for RootModel core metadata preservation.",
  "structural_form": "changelog",
  "shape": "records",
  "genre": "official",
  "ask_here": [
    "What are the breaking changes between v2.13.x and v2.14.0 (when final released)?",
    "What performance improvements or validation/serialization fixes are included in v2.13.4?",
    "Does the PyEmscripten wheel in v2.14.0a1 have any known compatibility issues beyond Pyodide 314.0?"
  ],
  "try_url": [
    {
      "url": "https://pydantic.dev/articles/pydantic-v2-13-release",
      "reason": "Official v2.13 release blog post referenced in the v2.13.0 notes — explains highlights and minor non-breaking changes"
    },
    {
      "url": "https://github.com/pydantic/pydantic/releases/tag/v2.14.0a1",
      "reason": "Full v2.14.0a1 release page — complete changelog for PyEmscripten and MultiHostUrl changes"
    }
  ]
}
```

---

## 9. wiki-rust

`https://en.wikipedia.org/wiki/Rust_(programming_language)`

Q: **when was rust 1.0 released and who created it?**  ·  expected_shape=`prose`, expected_genre=`encyclopedia`

Fetch: tier=`site_handler:wikipedia` · status=`ok` · chars=42295

### · 9211 ms · $0.01913

```json
{
  "answer": "Rust 1.0, the first stable release, was published on May 15, 2015. Rust was created by Graydon Hoare, who started the project in 2006 while working at Mozilla.",
  "structural_form": "article",
  "shape": "prose",
  "genre": "encyclopedia",
  "ask_here": [
    "What were the major language design influences on Rust during its development?",
    "How did the ownership system evolve between 2010 and 2015?",
    "What significant features were removed or changed between early Rust and 1.0?",
    "How did Mozilla's sponsorship in 2009 change the trajectory of the project?"
  ]
}
```

---

## 10. pypi-httpx

`https://pypi.org/project/httpx/`

Q: **what is the latest version of httpx and its main dependencies?**  ·  expected_shape=`key-value`, expected_genre=`official`

Fetch: tier=`raw` · status=`ok` · chars=6711

### · 10234 ms · $0.01832

```json
{
  "answer": "The latest stable version of httpx is 0.28.1 (released Dec 6, 2024). The page shows 1.0.dev3 pre-release available (Sep 15, 2025). Dependencies are not explicitly listed on this PyPI page—the Requires field only specifies Python >=3.8; optional extras (brotli, cli, http2, socks, zstd) are available but their backing packages aren't itemized here.",
  "structural_form": "product",
  "shape": "key-value",
  "genre": "official",
  "try_url": [
    {
      "url": "https://www.python-httpx.org/",
      "reason": "Official documentation—likely lists full dependency tree and installation guidance"
    },
    {
      "url": "https://github.com/encode/httpx",
      "reason": "Source repo—pyproject.toml or setup.py shows exact pinned dependencies for each extra"
    }
  ]
}
```

---

## 11. lobste-thread

`https://lobste.rs/s/n1gytv`

Q: **what is the dominant critique in this discussion?**  ·  expected_shape=`discussion`, expected_genre=`community`

Fetch: tier=`raw` · status=`ok` · chars=27823

### · 10603 ms · $0.01548

```json
{
  "answer": "The dominant critique is that Ruby/RuboCop lacks built-in ceremony-free defaults. Critics argue RuboCop involves excessive configuration overhead (picking and tuning cops, debating rule changes) compared to languages with opinionated built-in tooling (Go's `gofmt`, StandardRB). The core tension: Ruby's philosophy of optionality creates fragmentation, and no authority exists to enforce community-wide standards like Go's language team.",
  "structural_form": "thread",
  "shape": "discussion",
  "genre": "community",
  "ask_here": [
    "Do commenters propose concrete solutions to RuboCop's configuration burden, or is the consensus 'use StandardRB instead'?",
    "Which commenters advocate keeping RuboCop defaults as-is, and what's their reasoning?",
    "Is there consensus on whether Ruby's philosophy of optionality is a feature or a bug?",
    "Do any responses address trade-offs between Go's rigid tooling and Ruby's flexibility?",
    "What's the tone toward newcomers returning to Ruby—welcoming, or skeptical of nostalgia bias?"
  ]
}
```

---

## 12. blog-julia-comments

`https://jvns.ca/blog/2026/05/15/moving-away-from-tailwind--and-learning-to-structure-my-css-/`

Q: **what does the author conclude about tailwind?**  ·  expected_shape=`prose`, expected_genre=`personal`

Fetch: tier=`raw` · status=`ok` · chars=12223

### · 10962 ms · $0.01947

```json
{
  "answer": "The author concludes that Tailwind was useful for learning CSS structure, but she has deliberately migrated away from it. While acknowledging Tailwind's educational value (reset styles, color palettes, font scales), she prefers vanilla CSS + semantic HTML because: (1) modern CSS features like grid, @layer, and @scope enable flexible layouts impossible in Tailwind; (2) Tailwind now requires build systems and bloats projects (2.8MB files); and (3) she believes promoting Tailwind devalues CSS expertise, which she now deeply respects as a serious technology.",
  "structural_form": "article",
  "shape": "prose",
  "genre": "personal",
  "ask_here": [
    "What specific CSS grid patterns does she use to replace Tailwind's responsive breakpoint syntax (md:, lg:)?",
    "Does she provide concrete recommendations for developers still deciding between Tailwind and vanilla CSS based on skill level?",
    "How does she handle component-scoping in vanilla CSS to prevent style conflicts, given she mentioned no programmatic enforcement?"
  ]
}
```

---

## 13. reddit-rust-thread

`https://www.reddit.com/r/rust/comments/1cu4wuc/announcing_rust_1781/`

Q: **what is the most discussed objection in this thread?**  ·  expected_shape=`discussion`, expected_genre=`community`

Fetch: tier=`raw` · status=`failed` · chars=0

(no content_md — skipping)

---

## Aggregate

- total cost: **$0.2213** over 13 URLs (12 succeeded)
- vs v1 catalog baseline ($0.1855 over 10 URLs): +19.3%
- parse failures: 0
- envelope violations: 0
- **memory leaks: 0**
- shape: 10/12 matched expected
- genre: emitted 12 / omitted 0
- obstacle: emitted on 0 URLs
- ask_here: emitted on 10, avg count 3.9
- try_url: emitted on 4, avg count 2.2
