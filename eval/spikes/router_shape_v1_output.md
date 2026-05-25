# Router-shape spike v1 — catalog vs router

Model: `claude-haiku-4-5` · max_tokens=1024 · thinking disabled

Two prompts, same content_md, same question. Compared on:
- did the suggestion arrays actually help follow up?
- were reasons Q-conditioned?
- did router emit empty arrays when its answer was complete?
- token/cost delta


---

## 1. arxiv-abs

`https://arxiv.org/abs/2402.17753`

Q: **what does the paper claim?**

Fetch: tier=`raw` · status=`ok` · chars=3170

### CATALOG · 13706 ms · $0.02942

```json
{
  "answer": "The paper introduces LoCoMo, a dataset of very long-term conversations (300 turns, 9K tokens avg. over 35 sessions) and an evaluation benchmark showing that LLMs struggle with long-range temporal/causal understanding in dialogues. Even with long-context LLMs or RAG, models substantially lag behind human performance on question answering, event summarization, and multi-modal dialogue tasks.",
  "page_kind": "reference",
  "page_kind_confidence": "high",
  "content_value": "high",
  "shapes": [
    {
      "label": "citations",
      "where": "References & Citations section",
      "size": "extensive (tools listed: Connected Papers, Litmaps, scite)"
    },
    {
      "label": "key-value",
      "where": "Abstract and metadata",
      "size": "small (title, submission date, authors, category)"
    },
    {
      "label": "code/data",
      "where": "Code, Data and Media section",
      "size": "medium (7 tools: alphaXiv, CatalyzeX, DagsHub, Gotit.pub, Hugging Face, ScienceCast)"
    }
  ],
  "follow_up_questions": [
    "What are the specific task metrics used in LoCoMo's evaluation benchmark?",
    "How does RAG retrieval strategy compare to long-context LLMs on this dataset?",
    "What persona/temporal event graph structure powers the conversation generation pipeline?",
    "Which LLM architectures were tested and what were their performance gaps vs. humans?",
    "Is the LoCoMo dataset publicly available, and what's the reproduction pipeline?"
  ],
  "next_links": [
    {
      "url": "https://arxiv.org/abs/2402.17753",
      "anchor": "View PDF HTML (experimental)",
      "kind": "drilldown",
      "reason": "Access full paper text, methods, experimental results, and figures"
    },
    {
      "url": "https://arxiv.org/list/cs.CL",
      "anchor": "cs.CL",
      "kind": "related",
      "reason": "Related NLP/dialogue papers in Computation and Language category"
    },
    {
      "url": "https://huggingface.co",
      "anchor": "Hugging Face",
      "kind": "source",
      "reason": "Likely host for LoCoMo dataset and model checkpoints used in evaluation"
    }
  ]
}
```

### ROUTER · 9557 ms · $0.01173

```json
{
  "answer": "The paper introduces LoCoMo, a dataset of very long-term conversations (300 turns, 9K tokens avg., spanning up to 35 sessions), generated via a machine-human pipeline using LLM-based agents grounded in personas and temporal event graphs. It presents a comprehensive evaluation benchmark measuring long-term memory across QA, event summarization, and multi-modal dialogue tasks, finding that LLMs struggle with lengthy conversations and long-range temporal/causal dynamics—improvements from long-context LLMs or RAG exist but substantially lag human performance.",
  "answer_completeness": "complete",
  "ask_here": [],
  "try_url": []
}
```

---

## 2. hn-item

`https://news.ycombinator.com/item?id=39745700`

Q: **what is the top objection in the discussion?**

Fetch: tier=`site_handler:hn` · status=`ok` · chars=15211

### CATALOG · 16646 ms · $0.02144

```json
{
  "answer": "The top objection in the discussion is the lack of quantified training data metrics. When asked 'How many tokens have you trained on?', the author admits 'Absolutely no idea sorry!!' and later estimates ~3B tokens (by another commenter), highlighting uncertainty around fundamental training parameters despite the model's demonstrated capabilities.",
  "page_kind": "qa",
  "page_kind_confidence": "high",
  "content_value": "high",
  "shapes": [
    {
      "label": "code",
      "where": "dataset references section with JSONL file paths",
      "size": "~13 datasets listed"
    },
    {
      "label": "key-value",
      "where": "Specs section (layers, context, embedding dimension, etc.)",
      "size": "10 technical parameters"
    },
    {
      "label": "comments",
      "where": "threaded discussion below main post",
      "size": "~6 comment chains with sub-replies"
    },
    {
      "label": "code",
      "where": "example inference outputs (sushi puzzle, parakeet room, robot cafe HTML)",
      "size": "3 detailed examples with timing"
    },
    {
      "label": "list",
      "where": "Learnings section (bullet points about model behavior)",
      "size": "8 observations"
    }
  ],
  "follow_up_questions": [
    "What does the Parakeet model architecture (18 layers, 1152 dim) imply about parameter efficiency vs. SOTA tiny models?",
    "How does the author's layered dataset streaming approach (JSONL with offset caching) compare to modern data-loading frameworks?",
    "Why does the model show recency bias and 'forget' earlier training despite cyclic resampling — is this a fundamental small-model limitation?",
    "How does Grouped Query Attention with 2-student groups affect hallucination rate vs. MQA/MHA baselines?",
    "What would reproducible token-count tracking (using HF tokenizer logs) add to the research publication?"
  ],
  "next_links": [
    {
      "url": "https://colab.research.google.com/drive/1gI8CM9Bz9ov0-E6aL2jF808rE56UtZyF?usp=sharing",
      "anchor": "Interactive Colab notebook",
      "kind": "drilldown",
      "reason": "Live inference demo; test model behavior firsthand"
    },
    {
      "url": "https://huggingface.co/datasets/euclaise/LittleTown",
      "anchor": "LittleTown dataset",
      "kind": "source",
      "reason": "One of 13 training datasets; HF hub provenance"
    },
    {
      "url": "https://huggingface.co/datasets/WizardLM/WizardLM_evol_instruct_V2_196k",
      "anchor": "WizardLM evol instruct V2",
      "kind": "source",
      "reason": "Largest synthetic instruction dataset used (196k)"
    },
    {
      "url": "https://github.com/kyegomez/AttentionIsOFFByOne",
      "anchor": "Softmax1 implementation",
      "kind": "related",
      "reason": "Experimental attention variant author mentions; sparse impact noted"
    },
    {
      "url": "https://lifearchitect.ai/models",
      "anchor": "Models Table (adt's database)",
      "kind": "related",
      "reason": "Parakeet catalogued alongside other tiny/small models; curated taxonomy"
    },
    {
      "url": "https://ftp.bytebreeze.dev/ftpuser/",
      "anchor": "Author's FTP server (partial code release)",
      "kind": "drilldown",
      "reason": "Raw training code and model details; author notes cleanup pending"
    }
  ]
}
```

### ROUTER · 9488 ms · $0.01721

```json
{
  "answer": "The top objection in the discussion is the lack of scientific methodology and documentation. The author acknowledges that 'my methods aren't exactly scientific unfortunately' due to hundreds of model iterations, bug fixes, and code changes over time, making it difficult to track exact training parameters (token count, training hours) and reproduce results. This is compounded by incomplete code cleanup and hosting on unstable infrastructure.",
  "answer_completeness": "complete",
  "ask_here": [],
  "try_url": []
}
```

---

## 3. blog-julia

`https://jvns.ca/blog/2026/05/15/moving-away-from-tailwind--and-learning-to-structure-my-css-/`

Q: **what does the author conclude about tailwind?**

Fetch: tier=`raw` · status=`ok` · chars=12223

### CATALOG · 14612 ms · $0.02027

```json
{
  "answer": "The author concludes that while Tailwind was invaluable for learning CSS structure, they've outgrown it. They moved away due to build-system overhead (2.8MB files), improved personal CSS skills, Tailwind's limitations for custom layouts (especially CSS Grid), mixed vanilla+Tailwind maintenance friction, and philosophical concerns that Tailwind devalues CSS expertise in an era where human skills matter.",
  "page_kind": "blog",
  "page_kind_confidence": "high",
  "content_value": "high",
  "shapes": [
    {
      "label": "comparison",
      "where": "throughout article (Tailwind vs vanilla CSS approaches)",
      "size": "~9 major sections"
    },
    {
      "label": "code",
      "where": "sections 1-9 (CSS examples, reset, grid, esbuild)",
      "size": "~15 code blocks"
    },
    {
      "label": "citations",
      "where": "section 8 responsive design, section 9 build system, concluding section",
      "size": "~8 linked references"
    },
    {
      "label": "list",
      "where": "section 'why migrate away from Tailwind' and 'CSS features I'm curious about'",
      "size": "~5 + 4 bullet points"
    }
  ],
  "follow_up_questions": [
    "What specific CSS Grid patterns does the author recommend for responsive layouts without media queries?",
    "How does the @scope CSS feature solve component isolation better than the naming convention the author uses?",
    "What are the performance implications of moving from 270K gzipped Tailwind to custom vanilla CSS with esbuild?",
    "Does semantic HTML in the author's new approach affect accessibility testing workflow compared to Tailwind projects?",
    "How does this CSS philosophy apply to larger team codebases vs single-author sites like the author's?"
  ],
  "next_links": [
    {
      "url": "https://www.bram.us/2023/10/17/a-whole-cascade-of-layers/",
      "anchor": "A whole cascade of layers",
      "kind": "source",
      "reason": "CSS @layer cascade architecture reference for structuring vanilla CSS"
    },
    {
      "url": "https://www.chromeunboxed.com/tailwind-femininity-css",
      "anchor": "Tailwind and the Femininity of CSS",
      "kind": "source",
      "reason": "Philosophical critique that influenced author's decision to value CSS expertise over tooling"
    },
    {
      "url": "https://css-tricks.com/a-responsive-grid-layout-with-no-media-queries/",
      "anchor": "A responsive grid layout with no media queries",
      "kind": "drilldown",
      "reason": "Demonstrates CSS Grid auto-fit technique for responsive design without breakpoints"
    },
    {
      "url": "https://developer.mozilla.org/en-US/docs/Web/CSS/@scope",
      "anchor": "@scope specification",
      "kind": "drilldown",
      "reason": "Native CSS component isolation feature alternative to naming conventions"
    },
    {
      "url": "https://wizardzines.com",
      "anchor": "wizardzines.com",
      "kind": "related",
      "reason": "Author's production site migrated away from Tailwind with credited designer Melody Starling"
    }
  ]
}
```

### ROUTER · 9649 ms · $0.01693

```json
{
  "answer": "The author concludes that while Tailwind was genuinely useful for learning CSS structure, she has moved away from it because: (1) modern Tailwind requires a build system she avoids, (2) it's inefficient (2.8MB files), (3) she's now skilled enough to handle vanilla CSS and wants flexibility for \"weird stuff\", (4) mixing Tailwind and vanilla CSS became unmaintainable, and (5) philosophically, she believes Tailwind contributes to devaluing CSS expertise in an era where human expertise matters.",
  "answer_completeness": "complete",
  "ask_here": [],
  "try_url": []
}
```

---

## 4. status-openai

`https://status.openai.com/`

Q: **is the API up right now?**

Fetch: tier=`raw` · status=`ok` · chars=758

### CATALOG · 13186 ms · $0.01136

```json
{
  "answer": "Yes, the API is up right now. OpenAI reports no known issues affecting their systems, with APIs showing 99.98% uptime over the Feb-May 2026 period.",
  "page_kind": "status",
  "page_kind_confidence": "high",
  "content_value": "high",
  "shapes": [
    {
      "label": "key-value",
      "where": "System status section with uptime metrics",
      "size": "4 service tiers × uptime percentage"
    },
    {
      "label": "timeline",
      "where": "Header showing 'Feb 2026-May 2026' reporting period",
      "size": "3-month aggregate window"
    },
    {
      "label": "table",
      "where": "Service breakdown (APIs, ChatGPT, Codex, FedRAMP) with component counts and uptime",
      "size": "4 rows × 3 columns (service, components, uptime)"
    }
  ],
  "follow_up_questions": [
    "Which OpenAI service has the lowest uptime in this period?",
    "How many total components across all services are being monitored?",
    "What is the disclaimer about availability metrics and subscription tiers?",
    "Has there been any incident history prior to this 3-month window?"
  ],
  "next_links": [
    {
      "url": "https://status.openai.com/",
      "anchor": "status.openai.com (full page)",
      "kind": "drilldown",
      "reason": "Access full incident history, subscribe to updates, view component-level status"
    }
  ]
}
```

### ROUTER · 9711 ms · $0.00986

```json
{
  "answer": "Yes, the OpenAI API is up right now. The status page reports no known issues affecting systems, with APIs showing 99.98% uptime over the Feb-May 2026 period.",
  "answer_completeness": "complete",
  "ask_here": [],
  "try_url": []
}
```
