# Reference answer (correct)

The Lenovo E310 Beyaz True Wireless Stereo earphones sell for **≈700 TL**,
discounted **21%** from a struck-through list price of **890 TL**.

The page renders this as `890 TL%21700 TL` — list price 890, a −21% badge,
and the ~700 TL price the customer actually pays.

(Prices rotate; the durable rule is in `case.yaml` criteria — report the
*discounted* price, never the list price, and never fuse the discount badge
into the number.)

---

## History

**Before `typed-extraction-boundary` (the regression this case captured):**

> 890 TL (discounted from 1,700 TL original price, representing 48% off)

Three failures in one — reported the **list** price (890) as the selling
price, **fabricated** a 1,700 TL list from the fused `%21700` digits, and
invented a 48% discount, all at `confidence: high`. Root cause: the
`record_extract` projection (`_own_text`) concatenated adjacent DOM text nodes
with no separator, fusing `890 TL` + `%21` + `700 TL` into `890 TL%21700 TL`.

**After `typed-extraction-boundary` (node-separation fix, validated live):**

> 700 TL. The listing shows "890 TL %21 700 TL" — the original price of 890 TL
> with a 21% discount brings the current selling price to 700 TL.

Un-fusing the projection was sufficient to flip the answer — the extractor now
reads the separated values correctly and even cites them. The struck-price is
CSS `line-through` (not a `<del>` tag), so the markdown-strikethrough mark does
not fire here; the deeper rendered-surface grounding for CSS-styled
strikethrough remains future work (ADR-0007 / `real-surface-grounding`).
