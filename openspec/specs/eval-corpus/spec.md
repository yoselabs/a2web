# eval-corpus Specification

## Purpose
TBD - created by archiving change eval-substrate. Update Purpose after archive.
## Requirements
### Requirement: a case separates inputs from expectations

Each corpus case SHALL store its frozen network/browser/LLM captures (`inputs/`) separately
from what the substrate asserts (`baseline/`). `inputs/` is a snapshot of the world and MAY
drift as the site changes; `baseline/` holds the asserted `contract.json` (deterministic
shape: fields present, token bounds, tier path) and `answer.md` (the reference answer for
LLM-judged axes). A case SHALL also carry `case.yaml` (question, url, failure class, tags,
expected tier path) and `meta.yaml` (per-layer capture timestamp, source URL, content-hash, sizes).

#### Scenario: a case's inputs and expectations are distinct artifacts

- **WHEN** a corpus case is inspected
- **THEN** its frozen captures live under `inputs/` and its asserted expectations live under
  `baseline/`, in separate files

### Requirement: refresh diffs against the blessed baseline and never overwrites silently

The `make eval-refresh` flow SHALL re-capture a case's `inputs/`, re-run replay, and present a
**diff** of the new extracted answer against the blessed `baseline/`. It SHALL NOT overwrite the
baseline without an explicit bless step. Re-blessing SHALL use the env-flag idiom consistent with
the existing contract-bless flow (`A2WEB_BLESS_EVAL=1`).

#### Scenario: a site change surfaces as a reviewable diff

- **WHEN** an operator refreshes a case whose site content has changed
- **THEN** the new answer is shown as a diff against the blessed baseline, and the baseline is
  updated only when the operator blesses it

#### Scenario: the confound is dissolved

- **WHEN** a refresh diff is reviewed
- **THEN** the operator can distinguish a code-driven answer change from a site-driven one before
  accepting, because the deterministic `contract.json` is reported alongside the prose diff

### Requirement: browser-snapshot capture is policy-driven per page class

Capture SHALL always freeze the raw HTTP layer, and SHALL eagerly freeze the browser-rendered
DOM for cases tagged `commerce` / `js` / `spa` (the classes that escalate). Other classes and the
jina/archive layers SHALL be captured on-use. A capture flag SHALL allow forcing eager capture of
all tiers.

#### Scenario: a commerce case freezes the browser layer up front

- **WHEN** a case tagged `commerce` is captured
- **THEN** both the raw HTTP layer and the browser-rendered DOM are frozen, even if the run did not
  escalate to the browser tier

#### Scenario: a static-doc case skips eager browser capture

- **WHEN** a case tagged neither `commerce` nor `js` nor `spa` is captured
- **THEN** the browser layer is captured only if the run actually used it

### Requirement: cases are grouped into named corpuses spanning the failure classes

Cases SHALL be grouped into named corpuses, including at least a `regression` set (cases the
product has actually gotten stuck on, which must keep passing) and a `breaking` set deliberately
spanning the failure taxonomy: class A (clean structured schema), class B (source omits the data /
JS-only / bot-walled), and class C (structured data present but wrong — list-vs-sale, stale, locale).
Each case SHALL declare its class.

#### Scenario: the regression corpus carries the original stuck case

- **WHEN** the `regression` corpus is loaded
- **THEN** it contains the Hepsiburada listing case that motivated the program, with a frozen
  cassette and a blessed baseline

#### Scenario: the breaking corpus spans A/B/C

- **WHEN** the `breaking` corpus is loaded
- **THEN** it contains at least one class-A, one class-B, and one class-C case, each declaring its class

### Requirement: fixtures are committed in plain form

Corpus fixtures SHALL be committed to the repository in plain (un-compressed) form so the diff/bless
review reads them and CI can gate on them without external fetch infrastructure. Capture SHALL warn
when a case bundle is unusually large rather than silently compressing it.

#### Scenario: a frozen fixture is a readable committed file

- **WHEN** a captured case is committed
- **THEN** its `inputs/` and `baseline/` files are plain committed files that produce human-readable
  diffs, not gzipped blobs

### Requirement: the corpus includes a selection-question case

The corpus SHALL include at least one case whose task is a selection question
("which is best?" / "which should I pick?") over a listing, so the benchmark
exercises answer neutrality (ADR-0012). The case's expectations SHALL assert that
the answer presents the option set and/or the criteria to judge on, and SHALL NOT
require the answer to name a single unqualified "best" (a criterion-disclosed lead
is acceptable). The case rides the existing four-axis scoring like any other.

#### Scenario: a selection case exists and exercises neutrality

- **WHEN** the corpus is loaded
- **THEN** at least one case carries a selection ("which is best?") task over a listing
- **AND** its expectations reward presenting options / criteria, not crowning a single unqualified best

### Requirement: a criterion is addressed to a reader that can read it

Every corpus criterion SHALL be readable by at least one scoring path, or SHALL
be recorded as unreadable. A criterion naming a field no axis is given, or a
property no axis can observe, contributes nothing to the score — and an
unreadable criterion left unrecorded reads as coverage while providing none.

A criterion asserting the absence of fabrication requires ground truth. Such
criteria SHALL be reformulated as deterministic assertions over the envelope
where the property admits one; where it does not, they SHALL appear in the
invariant-to-cell mapping as an open gap rather than be deleted. Deleting them
would satisfy the letter of this requirement while erasing the record of what is
unguarded.

Where a deterministic assertion vocabulary already exists for offline replay, the
live bench SHALL use the same vocabulary per cell rather than leaving the same
properties unchecked. A key one harness cannot evaluate SHALL be reported as
unobservable, never as a pass.

#### Scenario: A criterion naming an unobservable property is rejected

- **WHEN** a corpus criterion names an envelope field no axis reads
- **THEN** the criterion is wired to an axis that reads it, converted to a
  deterministic assertion, removed, or recorded as an open gap

#### Scenario: A URL claim is checked without a judge

- **WHEN** an answer cites a URL
- **THEN** it is asserted to appear in the retrieved body, the emitted index, or
  the page's own address, deterministically and with no model in the loop

### Requirement: every first-class invariant has at least one catching cell

Each first-class product invariant SHALL have at least one corpus cell whose
failure is caused by violating that invariant, and the mapping from invariant to
catching cell SHALL be recorded.

An invariant witnessed nowhere is enforced only by the code that implements it,
and a change to that code is unopposed. An invariant witnessed only where it has
no code implementer is witnessed exactly where it is not enforced — the two
halves must not be inverted.

The wire half of an invariant SHALL be witnessed as well as the attribute half.
Assertions reading response attributes do not exercise the wire projection, which
is the layer agents consume.

#### Scenario: An invariant with no catching cell is recorded as a gap

- **WHEN** the invariant-to-cell mapping is produced
- **THEN** every invariant with zero catching cells is listed as an open gap

#### Scenario: The observed projection carries the completeness signals

- **WHEN** a replay case observes a failed retrieval
- **THEN** the observation includes the incompleteness flag and the narrative, so
  a regression on either is catchable
