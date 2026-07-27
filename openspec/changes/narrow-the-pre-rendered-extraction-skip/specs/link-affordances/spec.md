## ADDED Requirements

### Requirement: The digest gate is satisfiable on every retrieval path

The pre-LLM gate that admits a page to the link digest — the presence of a
structured (`json_synth` / `record_synth`) candidate standing in for
`structural_form ∈ {product, listing}` before the model classifies — SHALL be
reachable on every retrieval path. The gate's criterion is unchanged and
deliberately unchanged: a prose-only article still pays nothing for a digest.
What changes is that a product or listing page can now satisfy it whatever tier
served it.

The gate was never the defect. It was unsatisfiable on the pre-rendered path
because the candidates that satisfy it were never produced there, and relaxing
it would have put a digest on prose articles in direct contradiction of the
requirement that says not to. Recorded here because a reader arriving at the
gate while chasing a missing `other_pages` will reach for it, as this project
did.

#### Scenario: Browser-served product page gets a digest

- **WHEN** a product page carrying a Product schema payload is retrieved by the
  browser tier
- **THEN** the `json_synth` candidate satisfies the gate and the link digest is
  assembled from the page's anchors

#### Scenario: Browser-served article still pays nothing

- **WHEN** a prose article is retrieved by the browser tier and no structured rung
  produces output
- **THEN** no digest is assembled, exactly as on the raw tier

#### Scenario: Anchors alone do not open the gate

- **WHEN** a pre-rendered page carries many anchors but no structured candidate
- **THEN** no digest is assembled — link availability is necessary and not
  sufficient
