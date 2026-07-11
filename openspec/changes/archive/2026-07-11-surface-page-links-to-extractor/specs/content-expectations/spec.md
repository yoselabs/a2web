## ADDED Requirements

### Requirement: The extractor receives the page's real links

The extractor SHALL be given the page's real anchor links — including chrome (nav/footer/tab) anchors that trafilatura removes as boilerplate — so it can return a real sub-resource/continuation URL rather than guess. This SHALL be satisfied by the selectolax `links[]` pass already produced by `content_extract` (flowing to `fc.links`); no shelf change is required.

> **Deferred enhancement (separate shelf EVOLVE, not this change):** enabling trafilatura `include_links=True` so *in-body* anchors additionally survive as inline `[label](url)` markdown (positional grounding). That depends on the shelf-adopted `content_extract`/`convert-md` and SHALL be enabled via a configuration passthrough or shelf contribution — never a local fork. It is additive on top of this requirement.

#### Scenario: Chrome anchor reaches the extractor

- **WHEN** a page links its reviews page only from a footer/tab anchor
- **THEN** that anchor's href is present in the link digest fed to the extractor (via the selectolax pass), even though trafilatura stripped it from the prose

### Requirement: Content concatenates prose and JSON-LD, never replaces

When both trafilatura prose and JSON-LD synthesized content are available, the content SHALL concatenate both rather than selecting one and discarding the other. This applies to the extractor input (already concatenated) and SHALL be extended to the caller-facing `content_md` so page prose is not made invisible when JSON-LD wins a display pick.

#### Scenario: Prose survives alongside JSON-LD

- **WHEN** a product page has both JSON-LD product data and body prose
- **THEN** the caller-facing content includes both, not JSON-LD alone

### Requirement: trafilatura duplicate body is de-duplicated

*(Applies only once the deferred `include_links=True` EVOLVE lands — the duplicate-body behavior was observed under `include_links`. Not a v1 concern.)* When trafilatura with `include_links=True` emits the body content more than once, the system SHALL de-duplicate the repeated block before use.

#### Scenario: Duplicated body collapsed

- **WHEN** trafilatura returns the same body block twice
- **THEN** the content used downstream contains it once
