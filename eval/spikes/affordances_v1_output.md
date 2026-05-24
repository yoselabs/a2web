# Affordances spike v1 — outputs

Primer ask: `Give a 2-3 sentence summary of what this page is.`

Model: claude-haiku-4-5 via ClaudeCodeProvider (post v0.20 opt-outs)



---

## hn-front — https://news.ycombinator.com/

**Fetch tier**: `site_handler:hn` · **chars**: 6632 · **status**: `ok`


**Affordances call**: 15110 ms · 20921 prompt + 417 completion · $0.01610


```json

{
  "answer": "This is the Hacker News front page showing the top 30 stories ranked by community engagement, fetched on May 23, 2026. Each entry displays a story title, upvote count, comment count, and links to both the original article and the HN discussion thread. The stories span technology, science, politics, and cultural topics with varying levels of traction and community interest.",
  "follow_up_questions": [
    "What are the most engaged stories by comment count, and what topics dominate the top discussions?",
    "How is the ranking determined—purely by upvotes, or do other factors like comment velocity matter?",
    "Are there patterns in which domains (anthropic.com, github.com, reuters.com, etc.) consistently appear on the front page?",
    "What's the age distribution of these stories—were they all posted recently, or does HN feature older content?",
    "How can I filter or search this list by topic, domain, or minimum engagement threshold?"
  ],
  "shapes": [
    {
      "label": "list",
      "where": "entire page body",
      "size": "30 items"
    },
    {
      "label": "key-value",
      "where": "each story entry",
      "size": "5 fields per story (title, points, comments, article link, discussion link)"
    }
  ],
  "missed_sections": [
    "navigation menu or header controls",
    "user account/login section",
    "search functionality",
    "sidebar (jobs, classifieds, etc.)",
    "pagination controls",
    "timestamp metadata for when stories were posted",
    "submitter/author information",
    "tags or categories"
  ]
}

```


---

## wikipedia-rust — https://en.wikipedia.org/wiki/Rust_(programming_language)

**Fetch tier**: `site_handler:wikipedia` · **chars**: 42295 · **status**: `ok`


**Affordances call**: 12355 ms · 21734 prompt + 496 completion · $0.01826


```json

{
  "answer": "This Wikipedia article provides a comprehensive overview of Rust, a general-purpose programming language emphasizing performance, type safety, concurrency, and memory safety. It covers Rust's history (created by Graydon Hoare in 2006, first stable release in 2015), key technical features like the borrow checker and ownership system, governance evolution, adoption by major companies, and syntax examples demonstrating basic language constructs.",
  "follow_up_questions": [
    "What specific companies or projects have adopted Rust, and for what use cases?",
    "How does Rust's borrow checker work to prevent memory safety errors without garbage collection?",
    "What was the significance of the Rust Foundation's formation in 2021?",
    "How does Rust's syntax compare to C++ and functional programming languages?",
    "What were the major controversies or governance challenges Rust faced, such as the 2021 moderation team resignation?"
  ],
  "shapes": [
    {
      "label": "key-value",
      "where": "top of page (infobox)",
      "size": "small"
    },
    {
      "label": "timeline",
      "where": "History section (2006–present)",
      "size": "medium"
    },
    {
      "label": "code",
      "where": "Syntax section (Hello World, variables, loops, conditionals)",
      "size": "large"
    },
    {
      "label": "citations",
      "where": "throughout (numbered references like [20], [21], [22])",
      "size": "large"
    }
  ],
  "missed_sections": [
    "Pattern matching (mentioned in intro but not detailed)",
    "Traits and methods (mentioned briefly, not expanded)",
    "Macros (referenced in code example but not explained)",
    "Error handling and Result/Option types",
    "Concurrency and threading models",
    "Performance characteristics and benchmarks",
    "Standard library overview",
    "Cargo package manager details"
  ]
}

```


---

## pypi-httpx — https://pypi.org/project/httpx/

**Fetch tier**: `raw` · **chars**: 6711 · **status**: `ok`


**Affordances call**: 11727 ms · 21218 prompt + 533 completion · $0.01730


```json

{
  "answer": "This is the PyPI package page for HTTPX, a next-generation HTTP client library for Python 3. It provides project metadata, installation instructions, feature highlights (HTTP/1.1 and HTTP/2 support, sync/async APIs), verified maintainer information, and a complete release history with downloadable distributions.",
  "follow_up_questions": [
    "What are the key differences between HTTPX and the standard `requests` library?",
    "How do I install HTTPX and what are the optional dependencies (brotli, cli, http2, socks, zstd)?",
    "What is the current stability status—why is it still in Beta (Development Status 4) rather than stable (1.0)?",
    "Where can I find the full documentation and what do the async/HTTP/2 support examples look like?",
    "How do I file bugs or contribute to HTTPX development?"
  ],
  "shapes": [
    {
      "label": "key-value",
      "where": "Project description section",
      "size": "small"
    },
    {
      "label": "key-value",
      "where": "Project details section (Metadata, License, Author, Python version requirement)",
      "size": "medium"
    },
    {
      "label": "timeline",
      "where": "Release history section",
      "size": "large"
    },
    {
      "label": "list",
      "where": "Download files section (wheel and source distributions)",
      "size": "small"
    },
    {
      "label": "key-value",
      "where": "File details sections (file hashes, metadata, upload dates)",
      "size": "medium"
    },
    {
      "label": "citations",
      "where": "Project links (Homepage, Documentation, Changelog, Source)",
      "size": "small"
    }
  ],
  "missed_sections": [
    "Code examples or usage snippets beyond the basic import/GET example",
    "Dependencies and their versions",
    "Project statistics (download counts, stars, forks)",
    "Community/contributor information",
    "Issue tracker or discussion links"
  ]
}

```


---

## arxiv-abstract — https://arxiv.org/abs/2402.17753

**Fetch tier**: `site_handler:arxiv` · **chars**: 1853 · **status**: `ok`


**Affordances call**: 11990 ms · 18973 prompt + 499 completion · $0.01209


```json

{
  "answer": "This page presents LoCoMo, a benchmark dataset and evaluation framework for measuring long-term conversational memory in LLM agents across very lengthy dialogues (300 turns, 35 sessions). The authors use a machine-human pipeline to generate high-quality, temporally-grounded conversations with personas and event graphs, then assess how well current LLMs (including long-context and RAG variants) perform on memory-dependent tasks like question answering and event summarization. Results show significant gaps between LLM and human performance on understanding long-range temporal and causal dynamics in extended conversations.",
  "follow_up_questions": [
    "How does LoCoMo's evaluation differ from prior long-term dialogue benchmarks that only covered up to five sessions?",
    "What specific memory failures do current LLMs exhibit—do they lose early context, conflate events, or struggle with causal reasoning?",
    "How much does retrieval-augmented generation improve over standard long-context LLMs on this benchmark, and what are the remaining gaps?",
    "What were the inter-annotator agreement rates for the human verification/editing phase, and how did consistency checks work across 300-turn conversations?",
    "Could this dataset and benchmark be used to fine-tune or train better memory mechanisms for conversational AI?"
  ],
  "shapes": [
    {
      "label": "key-value",
      "where": "header metadata (authors, categories)",
      "size": "small"
    },
    {
      "label": "list",
      "where": "Categories section (cs.CL, cs.AI, cs.LG)",
      "size": "small"
    }
  ],
  "missed_sections": [
    "Abstract (full structured abstract with Motivation/Method/Results sections)",
    "Introduction",
    "Related Work",
    "Dataset construction methodology (detailed pipeline steps)",
    "Evaluation tasks and metrics",
    "Experimental results (tables, figures, baseline comparisons)",
    "Analysis and error breakdown",
    "Conclusion and future work",
    "References/citations"
  ]
}

```


---

## reddit-comments — https://www.reddit.com/r/LocalLLaMA/comments/1iqz5nb/

**Fetch tier**: `raw` · **chars**: 0 · **status**: `failed`


(no content_md returned)


---

**Total affordances cost across 5 URLs**: $0.0637
