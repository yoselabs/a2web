# Router-shape spike v2 — stressed URLs · catalog vs router vs hybrid

Model: `claude-haiku-4-5` · max_tokens=1024 · thinking disabled

Three prompts on the same fetch. URLs deliberately chosen to force partial answers.
Key question: does Haiku correctly self-assess partiality, or does it falsely
claim `completeness: complete` and starve the agent of suggestions?


---

## 1. arxiv-pdf-stub

`https://arxiv.org/abs/2402.17753`

Q: **what experimental setup did the authors use in section 4?**

_expected gap_: deep section content — likely only in the PDF

Fetch: tier=`site_handler:arxiv` · status=`ok` · chars=1853

### CATALOG · 11658 ms · $0.01180

```json
{
  "answer": "The fetched content is an abstract only and does not contain section 4 or experimental setup details. You would need to access the full PDF at arxiv.org/pdf/2402.17753 to find the experimental methodology.",
  "page_kind": "reference",
  "shapes": [
    {
      "label": "metadata",
      "where": "header",
      "size": "compact"
    },
    {
      "label": "abstract",
      "where": "body",
      "size": "medium"
    },
    {
      "label": "key-value",
      "where": "footer (categories)",
      "size": "small"
    }
  ],
  "follow_up_questions": [
    "What are the specific evaluation metrics used in the LoCoMo benchmark?",
    "How many human annotators were involved in the verification pipeline?",
    "What LLM models were compared in the experimental results?",
    "What is the inter-annotator agreement score for long-range consistency?",
    "How were temporal event graphs constructed and represented?"
  ],
  "next_links": [
    {
      "url": "https://arxiv.org/pdf/2402.17753",
      "anchor": "Full PDF version",
      "kind": "drilldown",
      "reason": "Contains section 4 experimental setup details (abstract only available here)"
    },
    {
      "url": "https://arxiv.org/abs/2402.17753",
      "anchor": "arxiv abstract page",
      "kind": "source",
      "reason": "Official paper metadata and citation info"
    }
  ]
}
```

### ROUTER · 10034 ms · $0.01065

```json
{
  "answer": "I cannot answer this question. The fetched content is only the abstract of the arxiv paper, which does not include section 4 or any experimental setup details. Section 4 content is not present in the provided material.",
  "answer_completeness": "none",
  "ask_here": [
    "What evaluation metrics did the authors use to measure long-term memory?",
    "How many conversation turns were included in the LoCoMo dataset?",
    "Which LLM models were evaluated in the study?"
  ],
  "try_url": [
    {
      "url": "https://arxiv.org/pdf/2402.17753",
      "reason": "Full PDF will contain section 4 with complete experimental setup, methodology, hyperparameters, and implementation details missing from abstract"
    }
  ]
}
```

### HYBRID · 10103 ms · $0.01100

```json
{
  "answer": "The provided abstract does not contain section 4 or details about the experimental setup. The abstract only describes the LoCoMo dataset creation pipeline (LLM-based agent architectures with personas and temporal event graphs) and mentions that evaluation tasks include question answering, event summarization, and multi-modal dialogue generation, but experimental methods, hyperparameters, model configurations, and statistical details are not included in this excerpt.",
  "answer_completeness": "none",
  "ask_here": [
    "Does the paper describe which specific LLM models were evaluated in section 4?",
    "What baseline models or comparison methods were used in the experiments?",
    "What metrics were used to evaluate long-term memory performance?"
  ],
  "try_url": [
    {
      "url": "https://arxiv.org/pdf/2402.17753",
      "reason": "Full PDF will contain section 4 with complete experimental setup, model details, hyperparameters, and evaluation methodology."
    }
  ]
}
```

---

## 2. hn-front-page

`https://news.ycombinator.com/`

Q: **what is the top-voted comment on the #1 story right now?**

_expected gap_: comments are not on this page — need the item permalink

Fetch: tier=`site_handler:hn` · status=`ok` · chars=7056

### CATALOG · 11759 ms · $0.01705

```json
{
  "answer": "The page does not contain the top-voted comment on the #1 story. The fetched content only shows the front-page listing with story titles, vote counts, and comment counts—it does not include the actual discussion threads or their comments.",
  "page_kind": "listing",
  "shapes": [
    {
      "label": "list",
      "where": "main content area",
      "size": "30 stories with metadata"
    },
    {
      "label": "key-value",
      "where": "per-story row",
      "size": "title, points, comment count, article link, discussion link"
    }
  ],
  "follow_up_questions": [
    "What is the #1 story's full article content?",
    "What are the top 5 comments in the #1 story's HN thread?",
    "Which stories have the highest comment-to-points ratio (most discussion)?",
    "Are there any patterns in story categories (AI/LLMs, systems, culture, history)?",
    "Which story links are paywalled or require authentication?"
  ],
  "next_links": [
    {
      "url": "https://news.ycombinator.com/item?id=48253386",
      "anchor": "discussion [Microsoft DOS source code story]",
      "kind": "drilldown",
      "reason": "Access the #1 story's discussion thread to find top-voted comments"
    },
    {
      "url": "https://arstechnica.com/gadgets/2026/04/microsoft-open-sources-the-earliest-dos-source-code-discovered-to-date/",
      "anchor": "article [Microsoft DOS source code]",
      "kind": "source",
      "reason": "Read the original article behind the #1 story"
    },
    {
      "url": "https://news.ycombinator.com/",
      "anchor": "Hacker News front page",
      "kind": "related",
      "reason": "Return to full front page (this is a snapshot from 2026-05-25T00:13:46Z)"
    }
  ]
}
```

### ROUTER · 12133 ms · $0.01514

```json
{
  "_parse_error": "Expecting value: line 1 column 1 (char 0)",
  "_raw": "I can see the Hacker News front page content, but I cannot directly access the comment threads. The page shows that the #1 story is \"Microsoft open-sources 'the earliest DOS source code discovered to date'\" with 411 points and 145 comments, but the actual comments are not included in the fetched content.\n\nTo find the top-voted comment, I would need to visit the discussion link for that story.\n\n```"
}
```

### HYBRID · 8615 ms · $0.00000

```json
{
  "_parse_error": "Expecting value: line 1 column 1 (char 0)",
  "_raw": ""
}
```

---

## 3. reddit-rust-hot

`https://www.reddit.com/r/rust/`

Q: **what is the most discussed objection in the top thread?**

_expected gap_: comments are in the thread page, not the listing

Fetch: tier=`raw` · status=`failed` · chars=0

(no content_md — skipping)

---

## 4. rfc-9110-deep

`https://datatracker.ietf.org/doc/html/rfc9110`

Q: **what does the spec say about the 421 Misdirected Request status code's interaction with HTTP/2?**

_expected gap_: very specific section — may need to navigate within

Fetch: tier=`raw` · status=`ok` · chars=403182

### CATALOG · 15684 ms · $0.01961

```json
{
  "answer": "No answer found on this page. RFC 9110 is the HTTP Semantics specification (June 2022) covering core protocol elements, methods, and status codes, but the fetched excerpt does not contain sections discussing HTTP/2 or the 421 Misdirected Request status code. You would need to search the full RFC or consult RFC 7540 (HTTP/2 specification) for that interaction.",
  "page_kind": "spec",
  "shapes": [
    {
      "label": "table",
      "where": "Section 1.4: Specifications Obsoleted by This Document",
      "size": "medium"
    },
    {
      "label": "hierarchical outline",
      "where": "Sections 1–2: Introduction, Conformance, Conformance subsections",
      "size": "large"
    },
    {
      "label": "citations",
      "where": "Throughout: RFC references (RFC 5234, RFC 7405, RFC 2119, RFC 8174, etc.)",
      "size": "medium"
    },
    {
      "label": "key-value",
      "where": "Abstract and Status section: metadata pairs (Title, Authors, Standards Track, etc.)",
      "size": "small"
    }
  ],
  "follow_up_questions": [
    "What are all HTTP status codes defined in RFC 9110 and their semantics?",
    "How does RFC 9110 define request methods (GET, POST, PUT, DELETE, PATCH, etc.) and their properties?",
    "What header fields and content negotiation mechanisms does RFC 9110 specify?",
    "Which RFCs does RFC 9110 obsolete and why (e.g., RFC 7231, RFC 7232)?",
    "How does RFC 9110 separate semantics from HTTP/1.1 and HTTP/2 transport syntax?"
  ],
  "next_links": [
    {
      "url": "https://www.rfc-editor.org/info/rfc9110",
      "anchor": "RFC 9110 Info Page",
      "kind": "drilldown",
      "reason": "Status, errata, feedback, and current metadata for this specification"
    },
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc7540",
      "anchor": "RFC 7540 (HTTP/2)",
      "kind": "related",
      "reason": "Defines HTTP/2 transport layer; would contain 421 Misdirected Request semantics"
    },
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc9111",
      "anchor": "RFC 9111 (HTTP Caching)",
      "kind": "related",
      "reason": "Companion caching spec referenced in RFC 9110 abstract; part of 2022 HTTP modernization"
    },
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc9112",
      "anchor": "RFC 9112 (HTTP/1.1 Messaging)",
      "kind": "related",
      "reason": "HTTP/1.1-specific syntax; RFC 9110 separates semantics from this transport definition"
    },
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc5234",
      "anchor": "RFC 5234 (ABNF)",
      "kind": "source",
      "reason": "Notation standard referenced for grammar definitions in RFC 9110"
    }
  ]
}
```

### ROUTER · 19810 ms · $0.01574

```json
{
  "answer": "The provided RFC 9110 excerpt does not contain information about the 421 Misdirected Request status code or its interaction with HTTP/2. The document is a partial fetch covering the introduction and conformance sections, which establish general protocol architecture but do not discuss specific status codes.",
  "answer_completeness": "none",
  "ask_here": [
    "What status codes are defined in RFC 9110 Section 15?",
    "How does HTTP/2 multiplexing affect request routing and error handling?",
    "What does RFC 9110 say about the relationship between connection state and request semantics?"
  ],
  "try_url": [
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc9110#section-15",
      "reason": "Section 15 defines HTTP status codes; 421 should be documented there with HTTP/2 context"
    },
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc9113",
      "reason": "RFC 9113 covers HTTP/2 framing and semantics; likely contains 421 + multiplexing interaction details"
    }
  ]
}
```

### HYBRID · 10474 ms · $0.01668

```json
{
  "answer": "RFC 9110 does not discuss the 421 Misdirected Request status code or its HTTP/2 interaction in the provided excerpt. The document is a general HTTP semantics specification covering core protocol elements, methods, and status codes, but the fetched content does not include sections detailing the 421 status code specifically.",
  "answer_completeness": "none",
  "ask_here": [
    "Does RFC 9110 have a dedicated section on 421 Misdirected Request (likely in Section 15 on status codes)?",
    "Is 421 mentioned in connection with HTTP/2 multiplexing or connection management?",
    "What RFC obsoletes or defines 421 if not RFC 9110?"
  ],
  "try_url": [
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc9110#section-15",
      "reason": "Section 15 covers all HTTP status codes; 421 should appear there with semantics"
    },
    {
      "url": "https://datatracker.ietf.org/doc/html/rfc7540",
      "reason": "RFC 7540 (HTTP/2) defines protocol-version-specific behavior; 421 interaction likely documented there"
    }
  ]
}
```

---

## 5. paywall-nyt

`https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html`

Q: **what did Biden say about Trump in this article?**

_expected gap_: paywalled — body content unavailable

Fetch: tier=`jina` · status=`failed` · chars=536

### CATALOG · 11181 ms · $0.01070

```json
{
  "answer": "No answer found. The page is paywalled (403 Forbidden) and requires CAPTCHA authorization to access. The fetched content only contains the page title and URL, with no article text available.",
  "page_kind": "paywalled",
  "shapes": [],
  "follow_up_questions": [
    "Can you access this NYT article through a different method (subscription, archive, cached version)?",
    "What is the article's publication date and section to search for alternative summaries?",
    "Does your knowledge base contain prior analysis of Biden-Trump coverage from March 2024?"
  ],
  "next_links": [
    {
      "url": "https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html",
      "anchor": "Original NYT article",
      "kind": "drilldown",
      "reason": "Requires authorized access (subscription or unblock method needed)"
    }
  ]
}
```

### ROUTER · 12159 ms · $0.00897

```json
{
  "answer": "I cannot answer this question. The New York Times article is behind a 403 Forbidden error and CAPTCHA protection, making the content inaccessible. The page fetch returned only the error message, not the article text.",
  "answer_completeness": "none",
  "ask_here": [],
  "try_url": [
    {
      "url": "https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html",
      "reason": "Try direct access without Jina proxy; may need NYT subscription or alternative archive (Archive.org, news aggregators)"
    }
  ]
}
```

### HYBRID · 10030 ms · $0.01057

```json
{
  "answer": "I cannot answer this question because the New York Times article is blocked with a 403 Forbidden error, likely due to paywall restrictions or CAPTCHA requirements. The fetched content contains no article text, only the error message.",
  "answer_completeness": "none",
  "ask_here": [],
  "try_url": [
    {
      "url": "https://archive.org/web/*/nytimes.com/2024/03/04/us/politics/biden-trump-2024.html",
      "reason": "Wayback Machine may have cached the article before paywall enforcement or access restrictions"
    },
    {
      "url": "https://news.google.com/search?q=Biden+Trump+March+2024+NYT",
      "reason": "Google News often displays NYT article snippets/headlines without paywall, revealing Biden's statements about Trump"
    },
    {
      "url": "https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html?unlocked_article_code=...",
      "reason": "NYT sometimes provides unlocked links via sharing; article may be accessible via different entry point or shared URL variant"
    }
  ]
}
```
