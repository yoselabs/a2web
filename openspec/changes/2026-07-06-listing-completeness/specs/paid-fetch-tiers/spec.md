## ADDED Requirements

### Requirement: Paid render scrolls for listing completion

The paid render tier (Zyte `browserHtml`) SHALL gain a `listing_partial`
trigger, alongside the gate-wall, obstacle, and handler `escalate_to_render`
triggers, all sharing the single one-dispatch-per-fetch budget. When dispatched
for listing completion, the request SHALL include a bounded scroll `actions`
sequence (`scrollBottom` + `waitForTimeout`, repeated up to `scroll_cap` times)
so the server-side render materialises lazy-loaded items before snapshotting;
non-completion renders send today's plain request. A free own-browser scroll
SHALL be preferred before spending the paid tier where a local backend is
available. When the oracle exceeds the completion ceiling (`SCROLL_MAX`), no paid
render is dispatched — the response steers instead.

#### Scenario: Completion render sends scroll actions

- **WHEN** the paid tier is dispatched for a `listing_partial` verdict with an oracle within `SCROLL_MAX`
- **THEN** the `browserHtml` request carries a bounded `scrollBottom` / `waitForTimeout` action sequence

#### Scenario: Shared cap across all render triggers

- **WHEN** a paid render was already spent on a gate wall or obstacle and a `listing_partial` verdict follows
- **THEN** no second paid render is dispatched (the one-dispatch cap holds) and the signal stands

#### Scenario: Broad search does not spend a paid render

- **WHEN** the oracle exceeds `SCROLL_MAX`
- **THEN** no paid render is dispatched and the response carries the `listing_partial` signal plus a narrow-the-query steer
