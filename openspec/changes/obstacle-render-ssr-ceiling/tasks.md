# Tasks — obstacle-render-ssr-ceiling

Test-first (BDD). `make check` is the gate. (Driven by the live SSR finding.)

## 1. Content-length ceiling guard

- [x] 1.1 Test (predicate): `_obstacle_wants_render` False when `content_md` is
      ≥ the ceiling even with SPA markers + thin-tier (the SSR case); True when
      content is thin + markers + non-JS tier.
- [x] 1.2 Test (fetch-level): an SSR-style page (SPA markers + full content ≥
      ceiling) with `obstacle: empty` does NOT render (no `zyte` step), obstacle
      survives → `retrieval_incomplete`.
- [x] 1.3 Add `_RENDER_CONTENT_CEILING` + the `len(content_md) < ceiling` check to
      `_obstacle_wants_render`.

## 2. Marker accuracy

- [x] 2.1 Widen `_SPA_MOUNT_MARKERS` to include Nuxt (`id="__nuxt"`,
      `__NUXT_DATA__`, `__NEXT_DATA__`); the ceiling (not markers) carries the SSR
      exclusion.

## 3. Gate + live verification

- [x] 3.1 `make check` green.
- [x] 3.2 Live: rfc-editor.org (Nuxt) + a Wikipedia off-topic ask no longer
      render (both flag `retrieval_incomplete` without paid egress).
- [x] 3.3 CHANGELOG.md entry; patch version bump + `make install-global`.
