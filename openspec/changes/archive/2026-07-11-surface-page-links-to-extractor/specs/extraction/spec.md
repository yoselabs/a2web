## ADDED Requirements

### Requirement: Extractor input includes the link digest

For pages classified `structural_form ∈ {product, listing}`, the extractor input menu SHALL include the placeholder link digest (owned by `link-affordances`) in addition to the existing content candidates. The digest SHALL be appended such that the byte-stable cache prefix is preserved (digest rides the tail, like the routing schema).

#### Scenario: Digest present for product page

- **WHEN** the extractor runs on a `product` page with a non-empty digest
- **THEN** the digest lines are present in the extractor's input alongside prose/JSON-LD

#### Scenario: Cache prefix stability preserved

- **WHEN** the digest is appended to the extractor input
- **THEN** the cache prefix used for prompt caching is unchanged by digest content

### Requirement: Router prompt carries an affordance principle, not a genre table

The router prompt SHALL instruct link selection via a generative principle — surface links that extend the page's primary entity (deeper detail, community signal, transaction terms, sibling/parent entities) — plus at most one or two worked examples explicitly marked non-exhaustive. The prompt SHALL NOT contain a per-genre affordance checklist. Per-genre expectations SHALL be encoded as eval-corpus tests, not prompt content.

#### Scenario: No genre checklist in prompt

- **WHEN** the router prompt is rendered
- **THEN** it contains the extend-the-primary-entity principle and no hardcoded `product ⇒ {reviews, specs, …}` table

### Requirement: Link references emitted as handles and validated closed-set

The extractor SHALL reference links by their `{{n}}` handle, never by raw URL. The router-payload parser SHALL validate emitted handles against the closed digest set, dropping any handle not present, and SHALL rehydrate surviving handles to real hrefs at the domain seam. A closed-set violation SHALL emit the `llm_wobble` signal (consistent with existing closed-enum handling) without failing the fetch.

#### Scenario: Handle rehydrated

- **WHEN** the extractor emits `{{3}}` and handle 3 maps to a real href
- **THEN** the response carries that real href

#### Scenario: Invalid handle wobbles, fetch survives

- **WHEN** the extractor emits a handle absent from the digest
- **THEN** the entry is dropped, `llm_wobble` is emitted, and the fetch still returns an answer

### Requirement: Suggestion count is justification-gated, not quantity-targeted

The router prompt SHALL NOT contain a quantity gradient (e.g. "3 good, 5 great, up to 10"). It SHALL instruct emitting a link only when the model can state what question the link answers that the current page cannot, with zero being an acceptable count. A hard maximum SHALL be enforced server-side as a circuit breaker, never surfaced in the prompt as a target.

#### Scenario: Zero suggestions is valid

- **WHEN** no linked page answers a question the current page cannot
- **THEN** the extractor emits no suggestion links and this is accepted

### Requirement: ask_here items disclose unreturned page content

Each `ask_here` item SHALL point at specific content present on the page but not returned in the answer (a coverage inventory), not a speculative curiosity whose answer the caller could generate unaided.

#### Scenario: ask_here grounded in omitted content

- **WHEN** the page contains a specs table the answer did not include
- **THEN** an `ask_here` item may point at that omitted specs content
