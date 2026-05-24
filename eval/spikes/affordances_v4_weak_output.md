# Affordances spike v4 — V_CTX_V2 calibration (weak)

Primer ask: `Give a 2-3 sentence summary of what this page is.` · Model: claude-haiku-4-5

Corpus: 14 URLs



---

## 1. tiny-arxiv (declared: `article-short`)

`https://arxiv.org/abs/2402.17753`


**Fetch**: tier=`site_handler:arxiv` · status=`ok` · chars=1853


**V_CTX_V2** · 16070 ms · $0.01329 · kind=`reference` (high)

```json
{
  "page_kind": "reference",
  "page_kind_confidence": "high",
  "reasoning": "This is an arXiv abstract page presenting a peer-reviewed research paper with standard academic structure (title, authors, abstract, categories); the content is substantial (~1850 chars) and unambiguously a research reference.",
  "answer": "This page presents an arXiv research paper titled 'Evaluating Very Long-Term Conversational Memory of LLM Agents' by Maharana et al. The paper introduces LoCoMo, a dataset of very long-term conversations (300 turns, 9K tokens average over 35 sessions) and benchmark to evaluate how well LLMs maintain memory and consistency across extended dialogues. Experimental results show that current LLMs struggle with long-range temporal and causal understanding, and while long-context models and RAG offer improvements, they still underperform compared to human-level consistency.",
  "follow_up_questions": [
    "What is the LoCoMo dataset and what are its key statistics (conversation length, number of turns, sessions)?",
    "What evaluation tasks are included in the benchmark (QA, summarization, dialogue generation)?",
    "How do long-context LLMs and RAG approaches compare to baseline models in the evaluation?",
    "What specific challenges do LLMs exhibit in understanding lengthy conversations and temporal dynamics?",
    "How were the very long-term dialogues generated and verified for consistency?"
  ],
  "shapes": [
    {
      "label": "citations",
      "where": "author names and affiliations",
      "size": "small"
    },
    {
      "label": "key-value",
      "where": "paper metadata (categories: cs.CL, cs.AI, cs.LG)",
      "size": "small"
    },
    {
      "label": "comparison",
      "where": "implicit in results section comparing human vs model performance across approaches",
      "size": "medium"
    }
  ]
}
```


---

## 2. tiny-gh-gist (declared: `code-snippet`)

`https://gist.github.com/jboner/2841832`


**Fetch**: tier=`raw` · status=`ok` · chars=22132


**V_CTX_V2** · 13257 ms · $0.02098 · kind=`thread` (high)

```json
{
  "page_kind": "thread",
  "page_kind_confidence": "high",
  "reasoning": "This is a GitHub Gist comment thread with 30+ nested comments discussing computer operation latencies; the page structure is chronological discussion with replies, citations, and technical debate—classic thread affordance.",
  "answer": "A GitHub Gist comment thread (2021–2023) discussing Jeff Dean's famous latency numbers for computer operations (L1 cache, disk seeks, network roundtrips, etc.). Commenters debate measurement accuracy, propose additions (cryptography, context switches), and reference related projects like napkin-math for teaching latency intuition.",
  "follow_up_questions": [
    "What are the most recent latency measurements cited, and how do they differ from the original 2010 numbers?",
    "Which commenters proposed new metrics to add to the original list, and what were their suggestions?",
    "What external resources (newsletters, talks, projects) were referenced for learning 'napkin math' estimation?",
    "Are there unresolved technical disputes in the thread (e.g., about the 3µs vs 100µs memory read discrepancy)?",
    "Which measurements did commenters question as inaccurate or misleading?"
  ],
  "shapes": [
    {
      "label": "comments",
      "where": "entire page body",
      "size": "30 records, chronologically ordered 2021–2023"
    },
    {
      "label": "citations",
      "where": "scattered throughout replies",
      "size": "5+ external links (napkin-math repo, YouTube talk, research papers, Wikipedia)"
    },
    {
      "label": "timeline",
      "where": "comment timestamps from Apr 2021 to Dec 2023",
      "size": "multi-year discussion arc"
    }
  ]
}
```


---

## 3. tiny-status-page (declared: `status`)

`https://status.openai.com/`


**Fetch**: tier=`raw` · status=`ok` · chars=758


**V_CTX_V2** · 11860 ms · $0.01094 · kind=`product-page` (high)

```json
{
  "page_kind": "product-page",
  "page_kind_confidence": "high",
  "reasoning": "OpenAI status page with system uptime metrics, component dashboards, and service health declarations—classic SaaS status/availability product page.",
  "answer": "This is OpenAI's public system status page reporting overall system health and uptime metrics for APIs, ChatGPT, Codex, and FedRAMP services across Feb–May 2026. The page indicates no current issues and displays aggregate uptime percentages (ranging 99.84–99.98%) across 12–30 components per service.",
  "follow_up_questions": [
    "What is the current uptime percentage for each OpenAI service (APIs, ChatGPT, Codex, FedRAMP)?",
    "Are there any active incidents or degraded services affecting OpenAI systems right now?",
    "How does uptime vary by subscription tier or model, and where can I find tier-specific SLAs?",
    "What is the historical uptime trend for OpenAI APIs over the past 90 days?"
  ],
  "shapes": [
    {
      "label": "key-value",
      "where": "Service health declarations (no issues, uptime %) for 4 service groups",
      "size": "small"
    },
    {
      "label": "timeline",
      "where": "Uptime chart spanning Feb–May 2026",
      "size": "medium"
    },
    {
      "label": "table",
      "where": "Component inventory by service (component count, uptime %)",
      "size": "small"
    }
  ]
}
```


---

## 4. huge-changelog (declared: `changelog`)

`https://github.com/pydantic/pydantic/releases`


**Fetch**: tier=`raw` · status=`ok` · chars=10503


**V_CTX_V2** · 14441 ms · $0.02174 · kind=`changelog` (high)

```json
{
  "page_kind": "changelog",
  "page_kind_confidence": "high",
  "reasoning": "GitHub releases page with versioned entries (v2.14.0a1, v2.13.4, v2.13.3, etc.) dating back to 2025-12, showing What's Changed sections, contributors, and assets per version — textbook changelog structure.",
  "answer": "This is the Pydantic GitHub releases page listing 10 recent versions from v2.14.0a1 (2026-05-22, pre-release) back to v1.10.26 (2025-12-18). Each entry contains release date, change categories (Packaging, Fixes, New Features), pull request links, and contributor names. The most recent stable release is v2.13.4 (2026-05-06), while v2.13.0 (2026-04-13) includes a major feature update with links to the release blog post.",
  "follow_up_questions": [
    "What breaking or non-breaking changes were introduced in v2.13.0?",
    "Which version added PyEmscripten platform tag support and what does it enable?",
    "What bug fixes were made in the recent patch releases (v2.13.2, v2.13.3, v2.13.4)?",
    "What is the current recommendation for users wanting to use the Pyodide wheel?",
    "Which versions are considered pre-releases vs. stable releases?"
  ],
  "shapes": [
    {
      "label": "timeline",
      "where": "main content body",
      "size": "10 versioned entries chronologically ordered"
    },
    {
      "label": "key-value",
      "where": "per-version section",
      "size": "release date, version tag, status (Latest/Pre-release), What's Changed categories"
    },
    {
      "label": "citations",
      "where": "embedded throughout",
      "size": "PR links (#XXXXX), GitHub usernames (@Viicos, etc.), external refs (Pyodide, pydantic-core)"
    },
    {
      "label": "comments",
      "where": "reaction section per entry",
      "size": "emoji reactions (👍 thumbs up, 🎉 hooray, 🚀 rocket) with counts"
    }
  ]
}
```


---

## 5. comments-lobste (declared: `threaded`)

`https://lobste.rs/s/2hu3pq/`


**Fetch**: tier=`jina` · status=`ok` · chars=880


**V_CTX_V2** · 8958 ms · $0.00988 · kind=`error` (high)

```json
{
  "page_kind": "error",
  "page_kind_confidence": "high",
  "reasoning": "HTTP 404 error page with explicit 'Resource Not Found' heading and statement that 'the story has been deleted'; no content body beyond navigation and error messaging.",
  "answer": "This is a 404 error page from Lobsters (a tech news aggregator). The requested resource (likely a story or discussion at /s/2hu3pq/) either never existed or has been deleted by a moderator.",
  "follow_up_questions": [],
  "shapes": [
    {
      "label": "error-messaging",
      "where": "page center",
      "size": "minimal"
    }
  ]
}
```


---

## 6. docs-anthropic (declared: `api-reference`)

`https://docs.claude.com/en/api/messages`


**Fetch**: tier=`raw` · status=`ok` · chars=726


**V_CTX_V2** · 10083 ms · $0.01179 · kind=`api-reference` (low)

```json
{
  "page_kind": "api-reference",
  "page_kind_confidence": "low",
  "reasoning": "The page is classified as API reference based on URL pattern and og:description, but the fetched content contains ONLY OpenGraph metadata (726 chars)—no actual API documentation body is present.",
  "answer": "This page is the Claude API reference documentation for Messages endpoints. However, only OpenGraph metadata was fetched; the actual API reference content (parameters, examples, response schemas) is not visible in the provided content.",
  "follow_up_questions": [],
  "shapes": [
    {
      "label": "blocked / content-not-fetched",
      "where": "body",
      "size": "unknown (SPA or client-rendered; OpenGraph only)"
    }
  ]
}
```


---

## 7. news-bbc (declared: `news-article`)

`https://www.bbc.com/news/articles/c1k7nzjpz7eo`


**Fetch**: tier=`jina` · status=`ok` · chars=10652


**V_CTX_V2** · 9872 ms · $0.02050 · kind=`error` (high)

```json
{
  "page_kind": "error",
  "page_kind_confidence": "high",
  "reasoning": "HTTP 404 error page with explicit 'Error 404 - Oops, the page you're looking for is no longer here' heading and search recovery affordance; the requested article (c1k7nzjpz7eo) no longer exists.",
  "answer": "This is a BBC News 404 error page indicating the requested article has been removed or is no longer available. The page displays the standard BBC error template with navigation and a suggestion to search for content instead. No article content is retrievable at this URL.",
  "follow_up_questions": [],
  "shapes": [
    {
      "label": "error_message",
      "where": "main content area",
      "size": "dominant"
    },
    {
      "label": "site_search",
      "where": "error recovery section",
      "size": "medium"
    },
    {
      "label": "related_stories",
      "where": "footer suggestions",
      "size": "medium"
    }
  ]
}
```


---

## 8. blog-julia-evans (declared: `blog-post`)

`https://jvns.ca/blog/2024/01/05/2023-in-review/`


**Fetch**: tier=`jina` · status=`ok` · chars=1442


**V_CTX_V2** · 14389 ms · $0.01217 · kind=`error` (high)

```json
{
  "page_kind": "error",
  "page_kind_confidence": "high",
  "reasoning": "Server returned HTTP 404 with explicit 'Page not found' messaging; the URL points to a specific blog post that no longer exists or has been removed.",
  "answer": "This is a 404 error page from Julia Evans' blog (jvns.ca). The requested blog post at /blog/2024/01/05/2023-in-review/ does not exist or has been deleted. Only the site navigation, header, and footer are present.",
  "follow_up_questions": [],
  "shapes": [
    {
      "label": "error-message",
      "where": "page body",
      "size": "minimal"
    },
    {
      "label": "navigation-structure",
      "where": "header and footer",
      "size": "standard"
    }
  ]
}
```


---

## 9. code-gh-readme (declared: `readme`)

`https://github.com/encode/httpx`


**Fetch**: tier=`site_handler:github` · status=`ok` · chars=5317


**V_CTX_V2** · 79710 ms · $0.01586 · kind=`readme` (high)

```json
{
  "page_kind": "readme",
  "page_kind_confidence": "high",
  "reasoning": "GitHub README with substantial content (~5300 chars), standard structure (header, installation, features, documentation, contribution links), and clear project overview for the HTTPX Python HTTP client library.",
  "answer": "HTTPX is a modern, fully-featured HTTP client library for Python 3 that extends the familiar `requests` API with support for HTTP/1.1, HTTP/2, both sync and async operations, and includes an integrated command-line client. The project emphasizes developer experience with type annotations, comprehensive test coverage, and extensive features like session management, authentication, streaming, and proxy support.",
  "follow_up_questions": [
    "What are the core installation options and minimum Python version required?",
    "What are the key differences between HTTPX and the requests library it builds upon?",
    "What are the optional dependencies and what features do they unlock (e.g., http2, cli, brotli)?",
    "Where is the full documentation and API reference located?",
    "What are the primary dependencies that HTTPX relies on internally?"
  ],
  "shapes": [
    {
      "label": "list",
      "where": "Features section enumerates 14+ capabilities with bullet points",
      "size": "medium"
    },
    {
      "label": "code",
      "where": "Installation examples and quickstart code snippets (pip, pycon, shell)",
      "size": "small"
    },
    {
      "label": "key-value",
      "where": "Dependencies listed with names and optional extras in parentheses",
      "size": "small"
    },
    {
      "label": "list",
      "where": "Standard requests library features (authentication, cookies, proxies, etc.) as bulleted items",
      "size": "medium"
    }
  ]
}
```


---

## 10. media-yt-video (declared: `video-page`)

`https://www.youtube.com/watch?v=dQw4w9WgXcQ`


**Fetch**: tier=`raw` · status=`ok` · chars=1013


**V_CTX_V2** · 8321 ms · $0.01179 · kind=`video-page` (high)

```json
{
  "page_kind": "video-page",
  "page_kind_confidence": "high",
  "reasoning": "OpenGraph metadata unambiguously identifies this as a YouTube video page with rich video properties (og:type=video.other, video embed URLs, dimensions). Content is thin (~1000 chars) but structural signals are definitive.",
  "answer": "This is Rick Astley's official 4K remaster of 'Never Gonna Give You Up' on YouTube. The page provides OpenGraph metadata for the video, including title, thumbnail image (1280×720), and embedded video player dimensions. This is the famous rickroll video.",
  "follow_up_questions": [
    "What is the video duration and view count?",
    "Who are the creator/channel and upload date?",
    "What are the comment threads discussing?",
    "Are there related videos or playlists linked?",
    "Does the page include chapter markers or captions?"
  ],
  "shapes": [
    {
      "label": "key-value",
      "where": "OpenGraph metadata table",
      "size": "16 properties (og:title, og:image, og:video:url, og:video:tag, etc.)"
    },
    {
      "label": "video-player",
      "where": "Embedded YouTube player",
      "size": "1280×720px, secure HTTPS embed"
    }
  ]
}
```


---

## 11. spa-react-dev (declared: `spa`)

`https://react.dev/learn`


**Fetch**: tier=`raw` · status=`ok` · chars=12130


**V_CTX_V2** · 12121 ms · $0.01969 · kind=`tutorial` (high)

```json
{
  "page_kind": "tutorial",
  "page_kind_confidence": "high",
  "reasoning": "This is React's official Quick Start tutorial—substantial educational content (12K+ chars) with progressive learning objectives, code examples, and interactive demos, structured as guided introduction to core concepts.",
  "answer": "React's Quick Start tutorial introduces 80% of daily React usage through hands-on examples: creating and nesting components, JSX syntax, styling, data display, conditional rendering, list rendering, event handling, state management with hooks, and component data sharing via props.",
  "follow_up_questions": [
    "What is the difference between a React component and an HTML tag, and how does naming convention reflect this?",
    "How does the `useState` hook work, and what are the two values it returns?",
    "What is 'lifting state up' and when should you use it to share data between components?",
    "How do you handle events in React, and what's the convention for event handler naming?",
    "What are JSX curly braces used for, and how do they differ from JavaScript string concatenation?"
  ],
  "shapes": [
    {
      "label": "learning-objectives",
      "where": "\"You will learn\" section near top",
      "size": "6 bullet points"
    },
    {
      "label": "code",
      "where": "throughout (MyButton, MyApp, Profile, ShoppingList examples)",
      "size": "10+ executable code snippets with embedded interactive demos"
    },
    {
      "label": "timeline",
      "where": "conceptual progression from components → JSX → styles → data → conditionals → lists → events → state → hooks → props",
      "size": "10 major sections"
    },
    {
      "label": "comparison",
      "where": "conditional rendering section (if/else vs ternary vs &&)",
      "size": "3 syntax patterns side-by-side"
    }
  ]
}
```


---

## 12. gated-nyt (declared: `paywalled`)

`https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html`


**Fetch**: tier=`jina` · status=`failed` · chars=536


**V_CTX_V2** · 11227 ms · $0.01048 · kind=`blocked` (high)

```json
{
  "page_kind": "blocked",
  "page_kind_confidence": "high",
  "reasoning": "HTTP 403 Forbidden error with explicit CAPTCHA/bot-wall warning; the fetched content is empty except for error metadata. No article content is present.",
  "answer": "This New York Times article about Biden vs Trump (dated 2024-03-04) is blocked by a 403 Forbidden error and CAPTCHA wall, preventing access to the full content. The page exists but is inaccessible without solving a CAPTCHA or authentication challenge. No summary of the article content is possible.",
  "follow_up_questions": [],
  "shapes": [
    {
      "label": "error-obstacle",
      "where": "page-level",
      "size": "blocking"
    }
  ]
}
```


---

## 13. paper-arxiv-pdf-stub (declared: `pdf-stub`)

`https://arxiv.org/pdf/2402.17753`


**Fetch**: tier=`site_handler:arxiv` · status=`ok` · chars=1853


**V_CTX_V2** · 11189 ms · $0.01307 · kind=`reference` (high)

```json
{
  "page_kind": "reference",
  "page_kind_confidence": "high",
  "reasoning": "ArXiv abstract page with clear academic paper metadata (authors, categories, abstract text), structured as a reference document with title, author list, category tags, and scholarly content summary.",
  "answer": "This is an arXiv paper abstract presenting LoCoMo, a dataset and benchmark for evaluating long-term conversational memory in LLM agents across very extended dialogues (300+ turns, 9K tokens, up to 35 sessions). The authors introduce a machine-human pipeline to generate high-quality long-term conversations grounded in personas and temporal event graphs, then evaluate how well current LLMs handle long-range consistency, temporal dynamics, and multi-modal dialogue tasks.",
  "follow_up_questions": [
    "What are the specific evaluation tasks included in the LoCoMo benchmark (question answering, summarization, etc.)?",
    "How do long-context LLMs and RAG techniques compare to human performance on LoCoMo tasks?",
    "What are the key limitations of current LLMs in maintaining very long-term conversational coherence?",
    "How is temporal consistency verified and graded in the human annotation process?",
    "What are the dataset statistics (number of conversations, average conversation length, session distribution)?"
  ],
  "shapes": [
    {
      "label": "metadata",
      "where": "header (title, authors, categories)",
      "size": "small"
    },
    {
      "label": "citations",
      "where": "implicit (multi-author paper with category tags)",
      "size": "small"
    },
    {
      "label": "key-value",
      "where": "abstract (dataset size: 300 turns/9K tokens; sessions: up to 35)",
      "size": "medium"
    }
  ]
}
```


---

## 14. docs-cf-page (declared: `marketing`)

`https://www.cloudflare.com/products/registrar/`


**Fetch**: tier=`raw` · status=`ok` · chars=6042


**V_CTX_V2** · 15698 ms · $0.01614 · kind=`product-page` (high)

```json
{
  "page_kind": "product-page",
  "page_kind_confidence": "high",
  "reasoning": "Substantial marketing content (>2000 chars) with clear product positioning, benefits, use cases, and CTA buttons; unambiguous SaaS product landing structure.",
  "answer": "Cloudflare Registrar is a domain registration and management service that charges at-cost pricing (no markups) and includes built-in security features like free DNS, CDN, and SSL. It supports 390+ TLDs and protects domains against hijacking via registry lock and DNSSEC. The page positions it as a transparent alternative to traditional registrars with hidden renewal fees.",
  "follow_up_questions": [
    "What are the exact renewal pricing and TLD support limits?",
    "How does the registry lock and DNSSEC protection work technically?",
    "What is the domain transfer process from another registrar?",
    "Are there any limitations on domain portfolios or bulk management?",
    "What does 'at-cost' mean—does it include ICANN fees?"
  ],
  "shapes": [
    {
      "label": "product-benefits",
      "where": "Benefits of Cloudflare Registrar section",
      "size": "3 key points: transparent fees, TLD support, built-in security"
    },
    {
      "label": "use-cases",
      "where": "Top use cases section",
      "size": "3 scenarios: register new, transfer existing, defend against hijacking"
    },
    {
      "label": "features",
      "where": "Registrar Products section",
      "size": "2 advanced features: custom domain protection, DNSSEC"
    },
    {
      "label": "key-value",
      "where": "FAQ section",
      "size": "2 Q&A pairs (What is Registrar, How does at-cost work)"
    },
    {
      "label": "cta",
      "where": "Multiple sections",
      "size": "3 action buttons: Search domains, Get started register, Get started transfer"
    }
  ]
}
```


---

## Totals

- Cost: $0.2083 · time: 237.2s
- Fetch failures: 0 / 14
- Parse failures: 0
- Confidence distribution: {'high': 13, 'low': 1}
