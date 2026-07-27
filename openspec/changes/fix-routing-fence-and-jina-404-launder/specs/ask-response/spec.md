## ADDED Requirements

### Requirement: The ask answer never carries raw model scaffolding

`AskResponse.answer` SHALL contain prose only. It SHALL NEVER carry a fenced code block that was part of the model's output contract — `\`\`\`next_links`, `\`\`\`json`, or an unlabelled fence whose body parses as JSON. Such a fence is un-contracted scaffolding leaking into the one field every caller parses: it inflates tokens, breaks prose rendering, and presents structured data in the channel reserved for the answer while the field that should carry it (`other_pages`) sits absent.

This SHALL hold on every path, including the degraded ones — a routing parse failure is precisely when the raw response is most likely to contain a fence, so the guarantee SHALL be enforced after sanitization rather than assumed from a successful parse.

#### Scenario: A routing parse failure yields fence-free prose

- **WHEN** a `query` call's router envelope fails to parse because the model returned prose followed by a `\`\`\`next_links` fenced JSON array
- **THEN** the `answer` on both the structured and text channels carries the prose only, with no `\`\`\`next_links` substring and no JSON array of `{anchor, url, reason, kind}` objects

#### Scenario: The guarantee is asserted at the wire, not only in the extractor

- **WHEN** the wire contract suite exercises `query` across its frozen cases
- **THEN** every captured `answer` is asserted free of fenced blocks on the `content[0].text` channel, not only on `structured_content`
