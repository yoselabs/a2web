# Affordances spike v5 — two-axis rubric (weak)

Primer ask: `Give a 2-3 sentence summary of what this page is.` · Model: claude-haiku-4-5

Axes: page_kind + page_kind_confidence + content_value (omitted on obstacle)

Corpus: 14 URLs



---

## 1. tiny-arxiv (declared: `article-short`)

`https://arxiv.org/abs/2402.17753`


**Fetch**: tier=`site_handler:arxiv` · status=`ok` · chars=1853


**V5** · 18517 ms · $0.01377 · kind=`reference` conf=`medium` value=`high`

```json
{
  "page_kind": "reference",
  "page_kind_confidence": "medium",
  "content_value": "high",
  "reasoning": "Academic paper abstract with structured metadata (authors, categories, dataset/benchmark description); clearly a reference work, but arxiv abstracts sit at the boundary between reference and article-short, making confidence medium rather than high.",
  "answer": "This paper introduces LoCoMo, a dataset and evaluation benchmark for measuring long-term conversational memory in LLM agents across very long dialogues (300 turns, 35+ sessions). The authors developed a machine-human pipeline to generate high-quality multi-modal conversations grounded in personas and temporal event graphs, then evaluated existing LLMs and RAG approaches on tasks like question answering and event summarization. Results show current models substantially underperform humans on long-range temporal and causal reasoning in extended conversations.",
  "shapes": [
    {
      "label": "citations",
      "where": "author line + category tags",
      "size": "small"
    },
    {
      "label": "key-value",
      "where": "dataset specs (turns, tokens, sessions)",
      "size": "small"
    },
    {
      "label": "list",
      "where": "evaluation tasks (QA, summarization, dialogue generation)",
      "size": "small"
    }
  ],
  "follow_up_questions": [
    "What specific long-context LLM architectures did the authors test (e.g., Claude, GPT-4, Llama variants)?",
    "How large is the LoCoMo dataset in total conversations, and is it publicly available?",
    "What is the performance gap between best-performing models and human baselines on each task?",
    "Does the paper distinguish between retrieval-based RAG failures vs. in-context reasoning failures?",
    "What persona and temporal event graph structures did they use to ground the dialogues?"
  ]
}
```


---

## 2. tiny-gh-gist (declared: `code-snippet`)

`https://gist.github.com/jboner/2841832`


**Fetch**: tier=`raw` · status=`ok` · chars=22132


**V5** · 13634 ms · $0.02180 · kind=`listing` conf=`high` value=`medium`

```json
{
  "page_kind": "listing",
  "page_kind_confidence": "high",
  "content_value": "medium",
  "reasoning": "This is a GitHub Gist comments section showing a chronological thread of 30 discussion items about computer latency benchmarks; the core reference material is referenced but not fully present, making the extracted content partial.",
  "answer": "This page is a listing of comments (30 records) from a GitHub Gist discussion thread about computer latency and performance benchmarks. The gist itself—'Latency Numbers Every Programmer Should Know' (originally from 2010)—is referenced throughout the comments, which span 2021–2023 and include technical corrections, follow-up questions, and resource recommendations from developers discussing the numbers' accuracy and applicability.",
  "shapes": [
    {
      "label": "comments",
      "where": "full page body",
      "size": "large (30+ individual comment threads with replies, timestamps, and usernames)"
    },
    {
      "label": "timeline",
      "where": "comment ordering",
      "size": "medium (chronological thread from Apr 2021 to Dec 2023)"
    },
    {
      "label": "citations",
      "where": "inline references",
      "size": "small (scattered external links to research papers, YouTube talks, Wikipedia articles, and related projects)"
    }
  ],
  "follow_up_questions": [
    "What is the original latency benchmark table that this gist references, and what are the specific numbers being discussed?",
    "What are the main technical corrections or disagreements raised in the comments about the latency figures?",
    "Which external resources (napkin-math project, research papers, context-switch studies) are most frequently cited and what do they add?",
    "Are there consensus updates or corrected figures proposed in the 2023 comments that supersede the 2010 baseline?",
    "What cryptography and disk-write latency data was proposed as additions to the original benchmark list?"
  ]
}
```


---

## 3. tiny-status-page (declared: `status`)

`https://status.openai.com/`


**Fetch**: tier=`raw` · status=`ok` · chars=758


**V5** · 11417 ms · $0.01272 · kind=`product-page` conf=`medium` value=`low`

```json
{
  "page_kind": "product-page",
  "page_kind_confidence": "medium",
  "content_value": "low",
  "reasoning": "OpenAI's status dashboard shows system health metrics and uptime statistics, but the extracted content is mostly chrome/summary data with minimal substantive body; sits in cluster C (status/product-page) where distinction is defensible.",
  "answer": "This is OpenAI's system status page, displaying uptime and component health across APIs, ChatGPT, Codex, and FedRAMP services. Currently reporting no known issues, with aggregate uptime metrics ranging from 99.84% to 99.98% for the Feb–May 2026 period.",
  "shapes": [
    {
      "label": "key-value",
      "where": "service components with uptime percentages",
      "size": "4 services × 1–12 components each"
    },
    {
      "label": "timeline",
      "where": "Feb 2026–May 2026aggregate reporting window",
      "size": "short (3-month span)"
    }
  ],
  "follow_up_questions": [
    "Are there any degraded services not listed as 'no issues'?",
    "What was uptime for individual components (not aggregate) during this period?",
    "How do subscription tiers affect reported availability for this account?",
    "What constitutes an 'issue' threshold that would trigger a status page alert?"
  ]
}
```


---

## 4. huge-changelog (declared: `changelog`)

`https://github.com/pydantic/pydantic/releases`


**Fetch**: tier=`raw` · status=`ok` · chars=10503


**V5** · 14226 ms · $0.02165 · kind=`changelog` conf=`high` value=`medium`

```json
{
  "page_kind": "changelog",
  "page_kind_confidence": "high",
  "content_value": "medium",
  "reasoning": "GitHub releases page for Pydantic library showing version history with dates, changes, and contributors; clear changelog structure but content is heavily truncated with incomplete entries and truncated text.",
  "answer": "This is the GitHub releases page for the Pydantic Python library, listing version history from v2.14.0a1 (most recent, 2026-05-22) back through v1.10.26. Each release entry includes date, change notes, contributors, and pull request links, though the extracted content shows significant truncation and incomplete entries.",
  "shapes": [
    {
      "label": "timeline",
      "where": "vertical listing of releases ordered by date (newest first)",
      "size": "10 release entries shown"
    },
    {
      "label": "key-value",
      "where": "each release: version number, date, release type (pre-release/latest), contributors (@mentions), PR links",
      "size": "~6 fields per entry"
    },
    {
      "label": "citations",
      "where": "pull request #numbers and GitHub user @handles throughout",
      "size": "multiple per entry"
    }
  ],
  "follow_up_questions": [
    "What are the breaking changes between v2.13.4 and v2.14.0a1?",
    "Which Pydantic version is recommended for production use (latest stable)?",
    "What major features were added in v2.13.0 compared to v2.12?",
    "Are there any known issues or regressions reported in the recent releases?",
    "What Python versions does the latest stable release support?"
  ]
}
```


---

## 5. comments-lobste (declared: `threaded`)

`https://lobste.rs/s/2hu3pq/`


**Fetch**: tier=`jina` · status=`ok` · chars=880


**V5** · 45536 ms · $0.01157 · kind=`error` conf=`high` value=`—`

```json
{
  "page_kind": "error",
  "page_kind_confidence": "high",
  "reasoning": "HTTP 404 status code with explicit 'Resource Not Found' heading and message stating the story has been deleted or does not exist.",
  "answer": "This is a 404 error page from Lobsters (a community news aggregator). The requested story or resource no longer exists or was deleted."
}
```


---

## 6. docs-anthropic (declared: `api-reference`)

`https://docs.claude.com/en/api/messages`


**Fetch**: tier=`raw` · status=`ok` · chars=726


**V5** · 10458 ms · $0.01247 · kind=`api-reference` conf=`high` value=`low`

```json
{
  "page_kind": "api-reference",
  "page_kind_confidence": "high",
  "content_value": "low",
  "reasoning": "OpenGraph metadata clearly identifies this as Claude API documentation for the Messages endpoint. The fetched content contains only metadata table (8 rows), no actual API reference body—page body was not captured or is behind dynamic rendering.",
  "answer": "This is the Claude API reference page for the Messages endpoints, part of Anthropic's official API documentation. The fetched content shows only OpenGraph metadata (title, description, og:image details) with no actual API reference documentation body included in the extraction.",
  "shapes": [
    {
      "label": "key-value",
      "where": "OpenGraph metadata table",
      "size": "8 rows (title, description, url, site_name, locale, image properties, type)"
    }
  ],
  "follow_up_questions": [
    "What are the request/response schemas for the Messages API?",
    "What HTTP methods and endpoints are available under Messages?",
    "Are there code examples (curl, Python, JavaScript) for common Message API patterns?",
    "What authentication and rate-limiting rules apply to Messages endpoints?",
    "Does this page document streaming vs. non-streaming message creation?"
  ]
}
```


---

## 7. news-bbc (declared: `news-article`)

`https://www.bbc.com/news/articles/c1k7nzjpz7eo`


**Fetch**: tier=`jina` · status=`ok` · chars=10652


**V5** · 10689 ms · $0.02048 · kind=`error` conf=`high` value=`—`

```json
{
  "page_kind": "error",
  "page_kind_confidence": "high",
  "reasoning": "HTTP 404 error explicitly stated in page heading and metadata; page structure is BBC's standard 404 template with navigation and related-links fallback, not article content.",
  "answer": "This is a BBC News 404 error page indicating the requested article (at URL c1k7nzjpz7eo) no longer exists or has been removed. The page displays the standard 404 template with site navigation and a list of recent BBC News stories as fallback content."
}
```


---

## 8. blog-julia-evans (declared: `blog-post`)

`https://jvns.ca/blog/2024/01/05/2023-in-review/`


**Fetch**: tier=`jina` · status=`ok` · chars=1442


**V5** · 9252 ms · $0.01241 · kind=`error` conf=`high` value=`—`

```json
{
  "page_kind": "error",
  "page_kind_confidence": "high",
  "reasoning": "HTTP 404 status code combined with explicit 'Page not found' heading and navigation-only body clearly identifies this as a broken link / 404 error page.",
  "answer": "This is a 404 error page from Julia Evans' blog (jvns.ca) indicating that the requested article at /blog/2024/01/05/2023-in-review/ no longer exists or has been moved. The page displays a standard 404 heading with site navigation and footer links, but no article content."
}
```


---

## 9. code-gh-readme (declared: `readme`)

`https://github.com/encode/httpx`


**Fetch**: tier=`site_handler:github` · status=`ok` · chars=5317


**V5** · 11226 ms · $0.01605 · kind=`readme` conf=`high` value=`high`

```json
{
  "page_kind": "readme",
  "page_kind_confidence": "high",
  "content_value": "high",
  "reasoning": "This is the GitHub README for encode/httpx, a mature Python HTTP client library. Clear project landing structure (heading + badges + features + installation + documentation + contribution info) with substantial body content (>2000 chars) directly relevant to understanding the project.",
  "answer": "This is the GitHub README for HTTPX, a next-generation HTTP client library for Python that provides both sync and async APIs with support for HTTP/1.1, HTTP/2, and an integrated command-line client. The page documents HTTPX's features (requests-compatible API, type annotations, 100% test coverage), installation instructions, and links to comprehensive documentation.",
  "shapes": [
    {
      "label": "key-value",
      "where": "Project metadata (stars, forks, language, license) at top",
      "size": "small"
    },
    {
      "label": "code",
      "where": "Installation example, Python REPL session, CLI usage",
      "size": "medium"
    },
    {
      "label": "list",
      "where": "Features section (bulleted main features + standard requests features)",
      "size": "large"
    },
    {
      "label": "list",
      "where": "Dependencies section (core + optional installs grouped)",
      "size": "medium"
    }
  ],
  "follow_up_questions": [
    "What are the key differences between HTTPX and the standard requests library in terms of API design?",
    "What versions of Python does HTTPX support, and what is its stability/release cadence?",
    "How does HTTPX's async support compare to alternatives like aiohttp or httptools?",
    "What is the performance profile of HTTPX vs requests for typical sync use cases?",
    "Are there breaking changes or migration guides between major versions?"
  ]
}
```


---

## 10. media-yt-video (declared: `video-page`)

`https://www.youtube.com/watch?v=dQw4w9WgXcQ`


**Fetch**: tier=`raw` · status=`ok` · chars=1013


**V5** · 10694 ms · $0.01280 · kind=`video-page` conf=`high` value=`low`

```json
{
  "page_kind": "video-page",
  "page_kind_confidence": "high",
  "content_value": "low",
  "reasoning": "OpenGraph metadata clearly identifies this as a YouTube video page (og:type=video.other, video embed URLs present), but only metadata is extracted—no transcript, description body, or comments visible in the fetched content.",
  "answer": "This is Rick Astley's official YouTube video for 'Never Gonna Give You Up' (4K Remaster), a music video page on YouTube. The fetched content contains only OpenGraph metadata (title, thumbnail, embed URL) without the actual video description, transcript, or engagement data. The page itself is a standard YouTube video hosting page, but the extraction is incomplete.",
  "shapes": [
    {
      "label": "key-value",
      "where": "OpenGraph metadata table",
      "size": "small"
    }
  ],
  "follow_up_questions": [
    "What does the full video description say (beyond the truncated og:description)?",
    "Are there visible comments or engagement metrics (views, likes, upload date)?",
    "Does the page include a transcript or captions?",
    "What is the actual video duration and channel subscriber count?"
  ]
}
```


---

## 11. spa-react-dev (declared: `spa`)

`https://react.dev/learn`


**Fetch**: tier=`raw` · status=`ok` · chars=12130


**V5** · 17613 ms · $0.01957 · kind=`tutorial` conf=`high` value=`high`

```json
{
  "page_kind": "tutorial",
  "page_kind_confidence": "high",
  "content_value": "high",
  "reasoning": "Unambiguous tutorial structure: step-by-step learning progression from component basics through state management, with interactive code examples and clear learning objectives stated upfront; substantial body (>2000 chars) with on-topic foundational React concepts.",
  "answer": "This is the React documentation's Quick Start tutorial, introducing 80% of core React concepts for daily use. It covers creating and nesting components, JSX syntax, styling, data display, conditional rendering, lists, event handling, state management with hooks, and prop-based data sharing between components.",
  "shapes": [
    {
      "label": "learning objectives list",
      "where": "top section under 'You will learn'",
      "size": "6 items"
    },
    {
      "label": "code examples with inline demos",
      "where": "throughout each concept section",
      "size": "10+ executable snippets"
    },
    {
      "label": "concept progression",
      "where": "section headings flow from components → markup → styling → data → conditionals → lists → events → state → hooks → props",
      "size": "10 major concept blocks"
    }
  ],
  "follow_up_questions": [
    "Are there prerequisites or prior JavaScript knowledge assumed before starting this tutorial?",
    "What resources does React recommend for learning the JavaScript syntax used in JSX (like destructuring, arrow functions, ternary operators)?",
    "How does React's official learning path progress after completing this Quick Start—what intermediate or advanced topics come next?",
    "Are there interactive sandbox environments (like CodePen or StackBlitz) embedded to let users experiment with the code examples live?",
    "Does this page cover performance considerations like re-renders, memoization, or when lifting state becomes problematic?"
  ]
}
```


---

## 12. gated-nyt (declared: `paywalled`)

`https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html`


**Fetch**: tier=`jina` · status=`failed` · chars=536


**V5** · 12077 ms · $0.01074 · kind=`blocked` conf=`high` value=`—`

```json
{
  "page_kind": "blocked",
  "page_kind_confidence": "high",
  "reasoning": "HTTP 403 Forbidden + explicit CAPTCHA warning indicate bot protection blocking automated access; no content body present.",
  "answer": "This New York Times article about the 2024 Biden-Trump election is inaccessible due to a 403 Forbidden error and CAPTCHA protection, which blocks automated content fetching. The page exists but cannot be read without human browser interaction and proper authentication credentials."
}
```


---

## 13. paper-arxiv-pdf-stub (declared: `pdf-stub`)

`https://arxiv.org/pdf/2402.17753`


**Fetch**: tier=`site_handler:arxiv` · status=`ok` · chars=1853


**V5** · 14121 ms · $0.01419 · kind=`reference` conf=`medium` value=`high`

```json
{
  "page_kind": "reference",
  "page_kind_confidence": "medium",
  "content_value": "high",
  "reasoning": "ArXiv abstract page with full research metadata (authors, categories, abstract text); classified as reference rather than article-short due to academic paper citation format and abstract-only presentation, but medium confidence due to Cluster A (academic/short articles) ambiguity between reference/article-short/pdf-stub.",
  "answer": "This is an arXiv research paper abstract presenting LoCoMo, a benchmark dataset for evaluating long-term conversational memory in LLM agents across 300-turn, 9K-token dialogues spanning up to 35 sessions. The work introduces a machine-human pipeline to generate very long-term dialogues grounded in personas and temporal event graphs, then benchmarks LLMs on question answering, event summarization, and multi-modal dialogue tasks. Findings show current LLMs struggle with lengthy conversations and long-range temporal/causal reasoning, with only incremental gains from long-context and RAG approaches compared to human performance.",
  "shapes": [
    {
      "label": "citations",
      "where": "header section (author names, institutions implicit)",
      "size": "6 authors listed"
    },
    {
      "label": "key-value",
      "where": "metadata footer",
      "size": "3 categories (cs.CL, cs.AI, cs.LG)"
    },
    {
      "label": "list",
      "where": "abstract body",
      "size": "enumerated research contributions and task types"
    }
  ],
  "follow_up_questions": [
    "What are the specific task types in the LoCoMo benchmark (question answering, event summarization, multi-modal dialogue)?",
    "How does the dataset scale compare to prior long-context dialogue work (e.g., what was the previous max context length)?",
    "What retrieval-augmented generation approach did the authors test, and what was the performance gap vs. baseline LLMs?",
    "What persona and temporal event graph generation method ensures conversation grounding quality?",
    "Which LLMs were benchmarked, and did larger models (e.g., GPT-4-class) meaningfully close the human performance gap?"
  ]
}
```


---

## 14. docs-cf-page (declared: `marketing`)

`https://www.cloudflare.com/products/registrar/`


**Fetch**: tier=`raw` · status=`ok` · chars=6042


**V5** · 14772 ms · $0.01668 · kind=`product-page` conf=`medium` value=`medium`

```json
{
  "page_kind": "product-page",
  "page_kind_confidence": "medium",
  "content_value": "medium",
  "reasoning": "Product landing page for Cloudflare Registrar with clear value prop and feature overview, but navigation structure and marketing copy dominate; extracted content is partial/truncated (footer nav cuts off mid-sentence).",
  "answer": "Cloudflare Registrar is a domain registration and management service that charges transparent, registry-cost-only prices with no markups or hidden fees. It supports 390+ TLDs and includes built-in security features (free DNS, CDN, SSL) plus anti-hijacking protections and DNSSEC. The page pitches core use cases: buying new domains, transferring existing ones, and defending high-profile domains with advanced security.",
  "shapes": [
    {
      "label": "list",
      "where": "Benefits section (11 records heading; transparent fees, TLD support, security)",
      "size": "medium"
    },
    {
      "label": "key-value",
      "where": "FAQ pairs (What is Cloudflare Registrar? / How does it offer domains at cost?)",
      "size": "small"
    },
    {
      "label": "list",
      "where": "Use cases / resources (register new, transfer existing, defend hijacking; ebook, blog, docs links)",
      "size": "medium"
    }
  ],
  "follow_up_questions": [
    "What is the actual pricing for common TLDs (.com, .io, .ai) on Cloudflare Registrar vs. competitors?",
    "Does Cloudflare Registrar support WHOIS privacy or domain masking?",
    "What are the specific security features in 'custom domain protection' (registry lock, out-of-band auth)?",
    "Can existing domains from other registrars be bulk-transferred, and what is the transfer process timeline?",
    "Does Cloudflare offer automated renewal or auto-pay options to prevent accidental expiration?"
  ]
}
```


---

## Totals

- Cost: $0.2169 · time: 214.2s
- Fetch failures: 0 / 14
- Parse failures: 0
- Envelope violations: 0
- Confidence dist: {'medium': 4, 'high': 10}
- Content_value dist: {'high': 4, 'medium': 3, 'low': 3, None: 4}
- Page kinds: {'reference': 2, 'listing': 1, 'product-page': 2, 'changelog': 1, 'error': 3, 'api-reference': 1, 'readme': 1, 'video-page': 1, 'tutorial': 1, 'blocked': 1}
