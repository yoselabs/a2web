## ADDED Requirements

### Requirement: Sufficiency is assessed on every path that produced content

The sufficiency assessment — whether what was retrieved is all of it — SHALL run
for every retrieval that produced new content, including content obtained by
escalation.

Sufficiency is what the withheld-body index depends on. A path that reaches an
answer without assessing sufficiency ships a distilled answer with no faithful
account of what was left out, which is the harm the index exists to prevent.

The assessment SHALL have exactly one implementation. A stage that re-implements
assess-and-set inline, because there is no point in the pipeline to return to, is
a second implementation that will diverge.

#### Scenario: Escalated content is assessed for sufficiency

- **WHEN** content is obtained by an escalation path
- **THEN** sufficiency is assessed on it before an answer is produced

#### Scenario: The assessment has one call site

- **WHEN** the sufficiency assessment is invoked
- **THEN** it is invoked from the pipeline, and no stage re-implements it inline

### Requirement: The sufficiency question has a name in the code

The question "is this all of it?" SHALL have a named home in the source tree,
distinct from retrieval, comprehension, and answer.

An unnamed question is answered ad hoc wherever it becomes urgent, which is how
it comes to be skipped on some paths and re-implemented on others. Naming it is
what makes a missing assessment visible as a missing call rather than as absent
code nobody was looking for.

#### Scenario: The assessment lives under its own name

- **WHEN** the source tree is read for how completeness is decided
- **THEN** a single named module answers it
