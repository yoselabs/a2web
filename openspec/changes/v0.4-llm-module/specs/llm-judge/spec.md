# llm-judge (new)

## Purpose

Provides the LLM-as-judge primitive used by the eval suite and reusable for any future internal quality gate. Wraps `Extractor` with a fixed JSON-output template (`JUDGE_V1`) and a structured `JudgeVerdict` return shape.

## ADDED Requirements

### Requirement: Judge scores an answer against criteria

`Judge(model: ModelSpec)` SHALL expose `score(task: str, criteria: list[str], answer: str) -> JudgeVerdict`.

`JudgeVerdict` SHALL be a `dataclass(slots=True)` with:
- `scores: list[int]` — one int 0-5 per criterion, same order as input
- `overall: int` — 0-5
- `reached: bool` — True if the answer conveyed real page content (not a failure notice)
- `reasoning: str` — one-sentence rationale
- `model: str`
- `cost_usd: float`

#### Scenario: correct answer scores high

- **GIVEN** `task="Who designed Rust?"`, `criteria=["mentions Graydon Hoare"]`, `answer="Graydon Hoare designed Rust at Mozilla in 2006."`
- **WHEN** `Judge(ModelSpec("anthropic", "claude-sonnet-4-6")).score(...)` is awaited
- **THEN** the result has `overall >= 4` and `scores[0] >= 4` and `reached is True`

#### Scenario: failure notice scores low

- **GIVEN** the same task/criteria as above, but `answer="The server returned HTTP 404."`
- **WHEN** judge is invoked
- **THEN** `reached is False` and `overall <= 1`

### Requirement: Judge parses JSON robustly

The Judge SHALL parse the model's response as JSON. On strict-parse failure, it SHALL attempt a permissive parse by extracting the first object-shaped substring matching `\{[\s\S]*\}`. On both failures, `JudgeParseError` SHALL be raised carrying the raw text.

#### Scenario: well-formed JSON parses

- **WHEN** the model returns `{"scores":[5],"overall":5,"reached":true,"reasoning":"clear hit"}`
- **THEN** `JudgeVerdict.overall == 5` and `JudgeVerdict.scores == [5]`

#### Scenario: JSON wrapped in prose still parses

- **WHEN** the model returns `Here is my verdict: {"scores":[3],"overall":3,"reached":true,"reasoning":"partial"}`
- **THEN** parsing succeeds with `overall == 3`

#### Scenario: garbage text raises JudgeParseError

- **WHEN** the model returns text containing no JSON object
- **THEN** `JudgeParseError` is raised with the raw text in the message
