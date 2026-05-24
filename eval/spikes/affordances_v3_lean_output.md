# Affordances spike v3 — V_LEAN (no answer field)

Primer ask: `Give a 2-3 sentence summary of what this page is.` · Model: claude-haiku-4-5 (post v0.20 opt-outs)

Corpus: 30 URLs (same as v2 for cross-comparison)



---

## 1. tiny-arxiv (declared: `article-short`)

`https://arxiv.org/abs/2402.17753`


**Fetch**: tier=`site_handler:arxiv` · status=`ok` · chars=1853


**V_LEAN** · 11886 ms · $0.01094 · 18973p+260c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "header section",
      "size": "6 authors"
    },
    {
      "label": "citations",
      "where": "throughout abstract",
      "size": "implicit references to prior work on long-context LLMs, RAG, dialogue evaluation"
    },
    {
      "label": "key-value",
      "where": "bottom section",
      "size": "3 categories (cs.CL, cs.AI, cs.LG)"
    }
  ],
  "follow_up_questions": [
    "What is LoCoMo and what are its key statistics (conversation length, number of turns, sessions)?",
    "What three evaluation tasks does the benchmark encompass?",
    "How do long-context LLMs and RAG compare in performance on very long-term dialogue understanding?",
    "What specific challenges do LLMs exhibit when processing lengthy conversations?",
    "Which authors are affiliated with which institutions?"
  ]
}
```


---

## 2. tiny-gh-gist (declared: `code-snippet`)

`https://gist.github.com/jboner/2841832`


**Fetch**: tier=`raw` · status=`ok` · chars=22132


**V_LEAN** · 9934 ms · $0.01872 · 22510p+242c

```json
{
  "shapes": [
    {
      "label": "comments",
      "where": "entire page",
      "size": "30 records"
    },
    {
      "label": "citations",
      "where": "scattered throughout comments",
      "size": "~8 external links"
    },
    {
      "label": "timeline",
      "where": "comments listed chronologically",
      "size": "Apr 2021 - Dec 2023"
    }
  ],
  "follow_up_questions": [
    "What specific latency measurements or performance numbers are discussed in the comments?",
    "Which external resources or research papers are referenced in the discussion thread?",
    "What gaps or missing measurements do commenters suggest should be added to the original gist?",
    "Who are the key contributors discussing this topic, and what domains do they represent?",
    "What criticisms or clarifications are raised about the terminology or accuracy of the original measurements?"
  ]
}
```


---

## 3. tiny-status-page (declared: `status`)

`https://status.openai.com/`


**Fetch**: tier=`raw` · status=`ok` · chars=758


**V_LEAN** · 21648 ms · $0.01094 · 18744p+378c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "top section",
      "size": "1 pair (status statement)"
    },
    {
      "label": "timeline",
      "where": "system status header",
      "size": "1 period (Feb 2026-May 2026)"
    },
    {
      "label": "list",
      "where": "main content area",
      "size": "4 service categories (APIs, ChatGPT, Codex, FedRAMP)"
    },
    {
      "label": "key-value",
      "where": "under each service category",
      "size": "3 pairs per category (component count, uptime percentage, component details)"
    },
    {
      "label": "comments",
      "where": "bottom of page",
      "size": "1 disclaimer note about aggregate metrics vs individual availability"
    }
  ],
  "follow_up_questions": [
    "What is the uptime percentage for each OpenAI service (APIs, ChatGPT, Codex, FedRAMP) over the Feb-May 2026 period?",
    "How many components comprise each service offering and what is their collective availability?",
    "What is the current operational status of OpenAI's systems (are there any active incidents)?",
    "How do aggregate availability metrics differ from individual customer availability based on subscription tier?",
    "Which service has the highest vs lowest uptime performance in the measured period?"
  ]
}
```


---

## 4. huge-wikipedia (declared: `encyclopedia`)

`https://en.wikipedia.org/wiki/Rust_(programming_language)`


**Fetch**: tier=`site_handler:wikipedia` · status=`ok` · chars=42295


**V_LEAN** · 9517 ms · $0.01718 · 21734p+284c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "top of page, infobox",
      "size": "12 fields"
    },
    {
      "label": "timeline",
      "where": "history section",
      "size": "large"
    },
    {
      "label": "code",
      "where": "syntax examples section",
      "size": "6 examples"
    },
    {
      "label": "citations",
      "where": "throughout history and features sections",
      "size": "44+ numbered references"
    }
  ],
  "follow_up_questions": [
    "What companies and organizations have adopted Rust, and when did each adoption occur?",
    "What was the role of Mozilla in Rust's development, and how did the 2020 layoffs affect the project?",
    "Which programming languages influenced Rust's design, and what specific features did each contribute?",
    "What are the key syntax differences between Rust and C/C++?",
    "How does Rust's ownership and borrow checker system prevent memory safety errors?"
  ]
}
```


---

## 5. huge-mdn-array (declared: `api-reference`)

`https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array`


**Fetch**: tier=`raw` · status=`ok` · chars=40505


**V_LEAN** · 18220 ms · $0.01846 · 17412p+595c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "Core characteristics section",
      "size": "4 key facts about JavaScript arrays"
    },
    {
      "label": "code",
      "where": "Array indices section",
      "size": "3 code examples"
    },
    {
      "label": "code",
      "where": "Relationship between length and numerical properties section",
      "size": "4 code examples"
    },
    {
      "label": "list",
      "where": "Array methods and empty slots section",
      "size": "~30 method names across two categories"
    },
    {
      "label": "code",
      "where": "Array methods and empty slots section",
      "size": "2 code examples demonstrating empty slot behavior"
    },
    {
      "label": "table",
      "where": "Copying methods and mutating methods section",
      "size": "8 rows (mutating methods vs non-mutating alternatives)"
    },
    {
      "label": "code",
      "where": "Copying methods and mutating methods section",
      "size": "3 code examples on copy conversion"
    },
    {
      "label": "key-value",
      "where": "Iterative methods section",
      "size": "callback signature definition with 3 parameters"
    },
    {
      "label": "list",
      "where": "Iterative methods section",
      "size": "10 iterative method names"
    },
    {
      "label": "code",
      "where": "Iterative methods section",
      "size": "2 code examples (callback signature + pseudocode iteration)"
    }
  ],
  "follow_up_questions": [
    "What is the difference between how older array methods (forEach, concat, slice) handle empty slots versus newer methods (keys, entries, find)?",
    "Which array methods mutate the original array in-place versus returning a new array, and what are the non-mutating alternatives?",
    "How does JavaScript's length property interact with sparse arrays and numerical indices, especially when setting elements outside current bounds?",
    "What are the callback function signature and parameters for iterative array methods like map, filter, and forEach?",
    "Why can't JavaScript arrays use arbitrary strings as indices like associative arrays, and how does bracket notation work with array indices?"
  ]
}
```


---

## 6. huge-changelog (declared: `changelog`)

`https://github.com/pydantic/pydantic/releases`


**Fetch**: tier=`raw` · status=`ok` · chars=10503


**V_LEAN** · 12807 ms · $0.02024 · 10859p+407c

```json
{
  "shapes": [
    {
      "label": "timeline",
      "where": "entire page",
      "size": "10 release entries spanning 2025-12-18 to 2026-05-22"
    },
    {
      "label": "list",
      "where": "within each release entry",
      "size": "multiple bullet points per release (What's Changed, Packaging, Fixes, New Features)"
    },
    {
      "label": "citations",
      "where": "throughout each entry",
      "size": "PR numbers (#13199, #13109, etc.), contributor mentions (@Viicos, @davidhewitt, etc.), GitHub comparison links"
    },
    {
      "label": "key-value",
      "where": "release headers",
      "size": "version number, date, pre-release/latest status markers"
    },
    {
      "label": "comments",
      "where": "below entries (e.g., v2.13.4, v2.13.3)",
      "size": "emoji reaction counts and reaction types (👍, 😄, 🎉, 🚀, ❤️, 👀)"
    }
  ],
  "follow_up_questions": [
    "What were the specific bug fixes included in v2.13.4?",
    "Which releases are marked as pre-releases vs. stable?",
    "What breaking changes or migration notes are mentioned across these releases?",
    "When was the pydantic-core repository merged into the main pydantic repository?",
    "What Python versions are explicitly supported in the most recent releases?"
  ]
}
```


---

## 7. listing-hn (declared: `listing`)

`https://news.ycombinator.com/`


**Fetch**: tier=`site_handler:hn` · status=`ok` · chars=6655


**V_LEAN** · 14848 ms · $0.01438 · 16465p+218c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "entire front page",
      "size": "30 items"
    },
    {
      "label": "key-value",
      "where": "each list item",
      "size": "title, points, comments count, article link, discussion link"
    }
  ],
  "follow_up_questions": [
    "Which stories have the highest engagement (comment count relative to upvotes)?",
    "What are the dominant topic categories across the front page (politics, tech, hardware, culture)?",
    "Which articles are from the last 24 hours vs older re-shared content?",
    "What is the relationship between HN discussion thread size and external article publication date?",
    "Which Show HN submissions are currently on the front page and what are their upvote counts?"
  ]
}
```


---

## 8. listing-lobste (declared: `listing`)

`https://lobste.rs/active`


**Fetch**: tier=`raw` · status=`ok` · chars=20483


**V_LEAN** · 12530 ms · $0.02156 · 23658p+294c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "entire page",
      "size": "25 records"
    },
    {
      "label": "citations",
      "where": "each list item",
      "size": "25 items with links"
    },
    {
      "label": "key-value",
      "where": "each list item metadata",
      "size": "25 items with score, tags, domain, submitter, timestamp"
    },
    {
      "label": "comments",
      "where": "each list item",
      "size": "comment counts per item (range 2-44)"
    }
  ],
  "follow_up_questions": [
    "What are the top-scored articles on Lobsters right now by upvotes?",
    "Which topics/tags are most represented in the active feed (e.g., go, linux, historical)?",
    "Who are the most recent submitters and what domains do they typically share?",
    "Which articles have generated the most discussion (comment count)?",
    "What is the age distribution of stories on the active feed (hours/days ago)?"
  ]
}
```


---

## 9. listing-gh-trending (declared: `listing`)

`https://github.com/trending/python?since=daily`


**Fetch**: tier=`raw` · status=`ok` · chars=11714


**V_LEAN** · 17603 ms · $0.01866 · 18397p+205c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "entire page",
      "size": "15 records"
    },
    {
      "label": "key-value",
      "where": "per list item (repository metadata)",
      "size": "~8 fields per item"
    }
  ],
  "follow_up_questions": [
    "Which Python repositories on today's GitHub trending list have the most stars gained in the last 24 hours?",
    "What are the primary contributors across these trending Python projects?",
    "Which repositories mention Claude or Anthropic in their description or contributor list?",
    "What is the total fork count and star count for the top 5 trending Python repos listed here?",
    "Which of these repositories offer sponsorship opportunities?"
  ]
}
```


---

## 10. listing-pypi (declared: `package-page`)

`https://pypi.org/project/httpx/`


**Fetch**: tier=`raw` · status=`ok` · chars=6711


**V_LEAN** · 13221 ms · $0.02290 · 14231p+361c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "Project description section",
      "size": "~8 pairs (description, links, features)"
    },
    {
      "label": "key-value",
      "where": "Project details section",
      "size": "~12 pairs (maintainers, license, author, requirements, classifiers)"
    },
    {
      "label": "timeline",
      "where": "Release history section",
      "size": "30+ releases from Nov 2021 to Sep 2025"
    },
    {
      "label": "table",
      "where": "Download files section",
      "size": "2 main distributions (source + wheel) with metadata rows"
    },
    {
      "label": "key-value",
      "where": "File details sections",
      "size": "2 files with hash algorithms, sizes, upload dates, upload method"
    }
  ],
  "follow_up_questions": [
    "What are the maintainers and verified PyPI details for this project?",
    "What Python versions and optional dependencies (extras) does httpx support?",
    "What is the complete release history and when was the latest stable version released?",
    "What are the SHA256, MD5, and BLAKE2b hashes for the current distribution files?",
    "What is the file size difference between the source distribution and the wheel distribution?"
  ]
}
```


---

## 11. comments-hn-item (declared: `threaded`)

`https://news.ycombinator.com/item?id=39745700`


**Fetch**: tier=`site_handler:hn` · status=`ok` · chars=15211


**V_LEAN** · 12911 ms · $0.01760 · 17454p+414c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "Specs section",
      "size": "10 items"
    },
    {
      "label": "list",
      "where": "References / datasets section",
      "size": "13 datasets"
    },
    {
      "label": "list",
      "where": "Learnings section",
      "size": "7 bullet points"
    },
    {
      "label": "code",
      "where": "First example (sushi puzzle Q&A)",
      "size": "small"
    },
    {
      "label": "code",
      "where": "Second example (Parakeet role-play Q&A)",
      "size": "small"
    },
    {
      "label": "code",
      "where": "Third example (Robot Cafe HTML generation)",
      "size": "medium"
    },
    {
      "label": "comments",
      "where": "Post replies section",
      "size": "6 nested comment threads"
    }
  ],
  "follow_up_questions": [
    "What are Parakeet's specific architectural choices (layer count, embedding dimension, attention mechanism variants) and why were they selected?",
    "What datasets was Parakeet trained on and in what proportions?",
    "How does Parakeet's inference performance compare to other 378M-parameter models on standard benchmarks?",
    "What are the observed failure modes and hallucination patterns at this model scale?",
    "When will the full codebase, model checkpoints, and synthetic data generation code be publicly released?"
  ]
}
```


---

## 12. comments-lobste (declared: `threaded`)

`https://lobste.rs/s/2hu3pq/`


**Fetch**: tier=`jina` · status=`ok` · chars=880


**V_LEAN** · 10212 ms · $0.00995 · 18813p+150c

```json
{
  "shapes": [],
  "follow_up_questions": []
}
```


---

## 13. docs-fastapi (declared: `tutorial`)

`https://fastapi.tiangolo.com/tutorial/first-steps/`


**Fetch**: tier=`raw` · status=`ok` · chars=12570


**V_LEAN** · 12055 ms · $0.01801 · 17642p+416c

```json
{
  "shapes": [
    {
      "label": "code",
      "where": "Top section - 'The simplest FastAPI file'",
      "size": "5 code blocks"
    },
    {
      "label": "code",
      "where": "Terminal output - 'Run the live server'",
      "size": "1 large terminal session"
    },
    {
      "label": "key-value",
      "where": "'Recap, step by step' section",
      "size": "6 steps"
    },
    {
      "label": "list",
      "where": "HTTP methods enumeration",
      "size": "8 methods (POST, GET, PUT, DELETE, OPTIONS, HEAD, PATCH, TRACE)"
    },
    {
      "label": "code",
      "where": "Configuration section - pyproject.toml examples",
      "size": "3 code blocks"
    },
    {
      "label": "code",
      "where": "Deployment examples - fastapi login and deploy commands",
      "size": "2 terminal examples"
    },
    {
      "label": "code",
      "where": "OpenAPI schema example",
      "size": "1 JSON block"
    }
  ],
  "follow_up_questions": [
    "How do I run a FastAPI development server locally?",
    "What HTTP methods (operations) are available in FastAPI?",
    "How do I configure the app entrypoint in pyproject.toml?",
    "What are the auto-generated documentation endpoints FastAPI provides?",
    "How do I deploy a FastAPI app using FastAPI Cloud?"
  ]
}
```


---

## 14. docs-postgres (declared: `api-reference`)

`https://www.postgresql.org/docs/current/sql-select.html`


**Fetch**: tier=`raw` · status=`ok` · chars=61780


**V_LEAN** · 12613 ms · $0.01751 · 17445p+405c

```json
{
  "shapes": [
    {
      "label": "code",
      "where": "top of page, immediately after title",
      "size": "large"
    },
    {
      "label": "list",
      "where": "under 'SELECT' heading, processing steps",
      "size": "medium"
    },
    {
      "label": "key-value",
      "where": "throughout document, keyword-definition pairs (WITH, FROM, WHERE, GROUP BY, etc.)",
      "size": "large"
    },
    {
      "label": "code",
      "where": "WITH Clause section, UNION/recursive examples",
      "size": "small"
    },
    {
      "label": "list",
      "where": "FROM Clause section, enumeration of source table specifications",
      "size": "medium"
    }
  ],
  "follow_up_questions": [
    "What is the execution order of clauses in a SELECT statement (WITH → FROM → WHERE → GROUP BY → SELECT list → DISTINCT → UNION/INTERSECT/EXCEPT → ORDER BY → LIMIT)?",
    "What are the differences between SELECT DISTINCT, SELECT DISTINCT ON, and SELECT ALL, and when should each be used?",
    "How do MATERIALIZED vs NOT MATERIALIZED WITH queries differ in performance characteristics, and when is each optimization appropriate?",
    "What are the syntax and use-case differences between FOR UPDATE, FOR NO KEY UPDATE, FOR SHARE, and FOR KEY SHARE locking clauses?",
    "How do SEARCH and CYCLE clauses work in recursive WITH queries, and what column names do they add to results?"
  ]
}
```


---

## 15. docs-anthropic (declared: `api-reference`)

`https://docs.claude.com/en/api/messages`


**Fetch**: tier=`raw` · status=`ok` · chars=726


**V_LEAN** · 10820 ms · $0.01032 · 7059p+134c

```json
{
  "shapes": [],
  "follow_up_questions": []
}
```


---

## 16. ref-rfc (declared: `spec`)

`https://datatracker.ietf.org/doc/html/rfc9110`


**Fetch**: tier=`raw` · status=`ok` · chars=403182


**V_LEAN** · 10219 ms · $0.01568 · 16886p+287c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "Document header (RFC metadata)",
      "size": "small"
    },
    {
      "label": "table",
      "where": "Section 1.4 (Specifications Obsoleted by This Document)",
      "size": "small"
    },
    {
      "label": "citations",
      "where": "Throughout document (bracketed RFC references)",
      "size": "large"
    },
    {
      "label": "code",
      "where": "Section 2.1 (ABNF notation examples)",
      "size": "medium"
    }
  ],
  "follow_up_questions": [
    "What are the core HTTP request methods and their semantics defined in Section 9?",
    "What HTTP status codes are defined and what do they signify?",
    "What is the detailed content negotiation algorithm described in Section 12?",
    "What are the specific requirements for HTTP/2 and HTTP/3 versus HTTP/1.1?",
    "What extensibility mechanisms and header field definitions does HTTP provide?"
  ]
}
```


---

## 17. ref-mdn-fetch (declared: `api-reference`)

`https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API`


**Fetch**: tier=`raw` · status=`ok` · chars=7591


**V_LEAN** · 10330 ms · $0.01660 · 16656p+577c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "opening paragraph",
      "size": "1 item with related links"
    },
    {
      "label": "list",
      "where": "Concepts and usage section",
      "size": "6 linked API objects (Request, Response, fetch(), Window, Worker, Promise)"
    },
    {
      "label": "list",
      "where": "Deferred Fetch section",
      "size": "2 linked items (fetchLater(), Using Deferred Fetch guide)"
    },
    {
      "label": "list",
      "where": "Interfaces section",
      "size": "8 interface links (Window.fetch, WorkerGlobalScope.fetch, fetchLater, DeferredRequestInit, FetchLaterResult, Headers, Request, Response)"
    },
    {
      "label": "key-value",
      "where": "HTTP headers section",
      "size": "2 permission policy headers with descriptions"
    },
    {
      "label": "list",
      "where": "Specifications section",
      "size": "2 spec links (Fetch# fetch-method, Fetch# deferred-fetch)"
    },
    {
      "label": "list",
      "where": "Browser compatibility section",
      "size": "2 compatibility tables (api.fetch, api.Window.fetchLater) - interactive, requires JavaScript"
    },
    {
      "label": "list",
      "where": "See also section",
      "size": "4 related topics (Using Fetch, Service Worker API, CORS, HTTP)"
    },
    {
      "label": "list",
      "where": "footer",
      "size": "3 contribution links (Learn to contribute, View on GitHub, Report problem)"
    }
  ],
  "follow_up_questions": [
    "What are the specific method signatures and parameters for fetch() and fetchLater()?",
    "What is the difference between Request and Response objects in the Fetch API?",
    "What browser versions support the deferred fetch (fetchLater) feature?",
    "How do CORS and HTTP Origin header semantics apply to Fetch API requests?",
    "What are the quota limits for the deferred-fetch and deferred-fetch-minimal permissions policies?"
  ]
}
```


---

## 18. news-bbc (declared: `news-article`)

`https://www.bbc.com/news/articles/c1k7nzjpz7eo`


**Fetch**: tier=`jina` · status=`ok` · chars=10652


**V_LEAN** · 5479 ms · $0.01680 · 9020p+153c

```json
{
  "shapes": [],
  "follow_up_questions": []
}
```


---

## 19. blog-julia-evans (declared: `blog-post`)

`https://jvns.ca/blog/2024/01/05/2023-in-review/`


**Fetch**: tier=`jina` · status=`ok` · chars=1442


**V_LEAN** · 10427 ms · $0.00962 · 14614p+97c

```json
{
  "shapes": [],
  "follow_up_questions": []
}
```


---

## 20. forum-so-question (declared: `qa`)

`https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python`


**Fetch**: tier=`raw` · status=`ok` · chars=38038


**V_LEAN** · 12500 ms · $0.01761 · 17628p+342c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "main content area",
      "size": "31 records (answer threads)"
    },
    {
      "label": "code",
      "where": "throughout answers (multiple code blocks)",
      "size": "large (10+ snippets)"
    },
    {
      "label": "citations",
      "where": "within each answer record",
      "size": "medium (Python docs, PEPs, external refs)"
    },
    {
      "label": "comments",
      "where": "under selected answers",
      "size": "small (3-5 comment sections visible)"
    },
    {
      "label": "timeline",
      "where": "metadata row in each answer",
      "size": "31 timestamps"
    }
  ],
  "follow_up_questions": [
    "How does yield differ from return in terms of execution flow and stack frame management?",
    "What is the practical difference in memory usage between a function that builds a list vs. one that yields values?",
    "How do generators implement the iterator protocol, and what methods must they define?",
    "Can a generator function be infinite (never terminate), and if so, how is that used safely?",
    "What is the difference between yield and yield from in Python 3, and when would you use each?"
  ]
}
```


---

## 21. code-gh-file (declared: `source-file`)

`https://github.com/pydantic/pydantic/blob/main/pydantic/main.py`


**Fetch**: tier=`raw` · status=`ok` · chars=45970


**V_LEAN** · 9940 ms · $0.01911 · 22636p+261c

```json
{
  "shapes": [
    {
      "label": "code",
      "where": "entire page (lines 1-1866)",
      "size": "large"
    },
    {
      "label": "key-value",
      "where": "top section (lines 100-200), class attributes documentation",
      "size": "medium"
    },
    {
      "label": "comments",
      "where": "scattered throughout, docstrings and inline notes",
      "size": "medium"
    }
  ],
  "follow_up_questions": [
    "What are the main class attributes and their purposes in BaseModel?",
    "What configuration options are available via ConfigDict for model behavior?",
    "How does the __setattr__ mechanism work for different field types (model_field, validate_assignment, private, cached_property)?",
    "What is the role of __pydantic_validator__ and __pydantic_serializer__ in model instances?",
    "What private attributes and metadata does BaseModel maintain at runtime?"
  ]
}
```


---

## 22. code-gh-readme (declared: `readme`)

`https://github.com/encode/httpx`


**Fetch**: tier=`site_handler:github` · status=`ok` · chars=5317


**V_LEAN** · 10612 ms · $0.01399 · 20211p+329c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "Features section",
      "size": "15 items"
    },
    {
      "label": "list",
      "where": "Standard features subsection",
      "size": "12 items"
    },
    {
      "label": "code",
      "where": "Getting started examples",
      "size": "3 blocks"
    },
    {
      "label": "key-value",
      "where": "Installation options section",
      "size": "2 variants"
    },
    {
      "label": "list",
      "where": "Dependencies section",
      "size": "10+ libraries listed"
    },
    {
      "label": "list",
      "where": "Optional installs",
      "size": "6 packages"
    }
  ],
  "follow_up_questions": [
    "What are the minimum Python version requirements for HTTPX?",
    "How do I install HTTP/2 support with HTTPX?",
    "What is the difference between sync and async APIs in HTTPX?",
    "What are the core dependencies vs optional dependencies for HTTPX?",
    "Does HTTPX support SOCKS proxies, and how do I enable that?"
  ]
}
```


---

## 23. product-amazon (declared: `product-page`)

`https://www.amazon.com/dp/B0BSHF7WHW`


**Fetch**: tier=`raw` · status=`ok` · chars=13101


**V_LEAN** · 9523 ms · $0.01962 · 22977p+213c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "top of page",
      "size": "5 entries"
    },
    {
      "label": "comments",
      "where": "main content area",
      "size": "13 reviews"
    }
  ],
  "follow_up_questions": [
    "What is the distribution of star ratings for this product (percentage breakdown)?",
    "Which specific MacBook Pro configuration (chip, color, capacity) is being reviewed most frequently?",
    "What are the recurring positive themes across 5-star reviews (keyboard, screen, performance, battery)?",
    "Are there any negative or critical reviews visible, or do all visible reviews show 5-star ratings?",
    "What time period do these reviews span, and is there a recency trend?"
  ]
}
```


---

## 24. media-yt-video (declared: `video-page`)

`https://www.youtube.com/watch?v=dQw4w9WgXcQ`


**Fetch**: tier=`raw` · status=`ok` · chars=1013


**V_LEAN** · 10763 ms · $0.00919 · 18917p+151c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "OpenGraph metadata table",
      "size": "15 fields"
    }
  ],
  "follow_up_questions": [
    "What is the video dimensions and aspect ratio?",
    "When was this video published or last updated?",
    "Are there any associated tags or categories beyond the single og:video:tag shown?",
    "What is the canonical URL for this video content?",
    "Does the page include view count, like count, or engagement metrics in the metadata?"
  ]
}
```


---

## 25. gov-sec-filing (declared: `filing`)

`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605&type=10-K&dateb=&owner=include&count=40`


**Fetch**: tier=`browser` · status=`ok` · chars=4571


**V_LEAN** · 10547 ms · $0.01420 · 20486p+250c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "top of page",
      "size": "6 items"
    },
    {
      "label": "table",
      "where": "main content area",
      "size": "22 rows"
    },
    {
      "label": "timeline",
      "where": "implied by table filing dates",
      "size": "2011-2026"
    }
  ],
  "follow_up_questions": [
    "What is the most recent 10-K filing date and accession number for this company?",
    "How many amended 10-K filings (10-K/A) has this company submitted, and in which years?",
    "What is the file size range for annual reports across the dataset shown?",
    "Which filing has the largest document size, and when was it filed?",
    "How frequently does this company file amended annual reports versus standard 10-K reports?"
  ]
}
```


---

## 26. spa-react-dev (declared: `spa`)

`https://react.dev/learn`


**Fetch**: tier=`raw` · status=`ok` · chars=12130


**V_LEAN** · 12113 ms · $0.01788 · 17409p+493c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "\"You will learn\" section",
      "size": "6 items"
    },
    {
      "label": "code",
      "where": "Creating and nesting components section",
      "size": "2 examples"
    },
    {
      "label": "code",
      "where": "Writing markup with JSX section",
      "size": "1 example"
    },
    {
      "label": "code",
      "where": "Adding styles section",
      "size": "2 code snippets"
    },
    {
      "label": "code",
      "where": "Displaying data section",
      "size": "3 examples"
    },
    {
      "label": "code",
      "where": "Conditional rendering section",
      "size": "3 examples"
    },
    {
      "label": "code",
      "where": "Rendering lists section",
      "size": "2 examples"
    },
    {
      "label": "code",
      "where": "Responding to events section",
      "size": "1 example"
    },
    {
      "label": "code",
      "where": "Updating the screen section",
      "size": "3 examples"
    },
    {
      "label": "code",
      "where": "Sharing data between components section",
      "size": "3 examples"
    }
  ],
  "follow_up_questions": [
    "How do you pass data from a parent component to a child component in React?",
    "What is the difference between HTML tags and React component names in JSX syntax?",
    "How do you conditionally render components based on a boolean state variable?",
    "What is the purpose of the `key` prop when rendering lists of components?",
    "How do you update a component's state when a user interacts with an event handler?"
  ]
}
```


---

## 27. data-json-feed (declared: `json-feed`)

`https://hnrss.org/frontpage.jsonfeed`


**Fetch**: tier=`jina` · status=`ok` · chars=18390


**V_LEAN** · 11312 ms · $0.02133 · 23753p+204c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "entire page (items array)",
      "size": "15+ entries"
    },
    {
      "label": "key-value",
      "where": "each list item",
      "size": "~8 fields per item (id, title, url, points, comments, author, date, content_html)"
    }
  ],
  "follow_up_questions": [
    "What are the top-ranked stories by points on Hacker News right now?",
    "Which stories have the most discussion (comments) activity?",
    "Who posted or submitted the highest-engagement stories?",
    "What publication sources are represented in the front page feed?",
    "How recent are these stories (publish timestamps)?"
  ]
}
```


---

## 28. gated-nyt (declared: `paywalled`)

`https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html`


**Fetch**: tier=`jina` · status=`failed` · chars=536


**V_LEAN** · 10182 ms · $0.00859 · 14229p+67c

```json
{
  "shapes": [],
  "follow_up_questions": []
}
```


---

## 29. paper-arxiv-pdf-stub (declared: `pdf-stub`)

`https://arxiv.org/pdf/2402.17753`


**Fetch**: tier=`site_handler:arxiv` · status=`ok` · chars=1853


**V_LEAN** · 11621 ms · $0.01026 · 11986p+278c

```json
{
  "shapes": [
    {
      "label": "key-value",
      "where": "header section",
      "size": "6 authors"
    },
    {
      "label": "citations",
      "where": "throughout abstract",
      "size": "multiple citations to prior work"
    },
    {
      "label": "key-value",
      "where": "footer",
      "size": "3 categories (cs.CL, cs.AI, cs.LG)"
    }
  ],
  "follow_up_questions": [
    "What are the specific evaluation tasks included in the LoCoMo benchmark?",
    "How many total conversations are in the LoCoMo dataset and what is the average number of turns per conversation?",
    "What techniques (long-context LLMs vs RAG) were compared, and what were the relative performance gaps vs human performance?",
    "What metrics or methodologies were used to measure long-term memory retention across the 35 sessions?",
    "What are the key failure modes or limitations identified when models process very long-term conversational context?"
  ]
}
```


---

## 30. docs-cf-page (declared: `marketing`)

`https://www.cloudflare.com/products/registrar/`


**Fetch**: tier=`raw` · status=`ok` · chars=6042


**V_LEAN** · 12308 ms · $0.01391 · 15724p+453c

```json
{
  "shapes": [
    {
      "label": "list",
      "where": "Navigation menu near top",
      "size": "5 items (How it works, Use cases, Products, Resources, FAQs)"
    },
    {
      "label": "list",
      "where": "Benefits section",
      "size": "3 items (Transparent fees, TLD support, Built-in security)"
    },
    {
      "label": "list",
      "where": "Use cases section",
      "size": "3 items (Register new domains, Transfer/renew existing, Defend against hijacking)"
    },
    {
      "label": "list",
      "where": "Products section",
      "size": "2 items (Custom domain protection, DNSSEC)"
    },
    {
      "label": "list",
      "where": "Resources section",
      "size": "6 items (Ebook, Blog, FAQ, Abuse process, Security checklist, Domain search)"
    },
    {
      "label": "key-value",
      "where": "FAQs section",
      "size": "2 Q&A pairs (What is Cloudflare Registrar, How does it offer domains at cost)"
    }
  ],
  "follow_up_questions": [
    "How many TLDs does Cloudflare Registrar support and what is the full list of supported extensions?",
    "What specific security features are included with Cloudflare Registrar domains (DNS, CDN, SSL)?",
    "How does Cloudflare avoid marking up domain prices and what are the actual costs?",
    "What protection mechanisms does Cloudflare offer against domain hijacking?",
    "How does DNSSEC work with Cloudflare Registrar and is it available for all domain types?"
  ]
}
```


---

## Totals

- V_LEAN: $0.4718 total · 358.7s total
- Fetch failures: 0 / 30
- Parse failures: 0 / 30
