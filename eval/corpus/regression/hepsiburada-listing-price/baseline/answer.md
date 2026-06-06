# Reference answer (correct)

The Lenovo E310 Beyaz True Wireless Stereo earphones sell for **≈700 TL**,
discounted **21%** from a struck-through list price of **890 TL**.

The page renders this as `890 TL%21700 TL` — list price 890, a −21% badge,
and the ~700 TL price the customer actually pays.

(Prices rotate; the durable rule is in `case.yaml` criteria — report the
*discounted* price, never the list price, and never fuse the discount badge
into the number.)

---

## Today's answer (WRONG — the regression this case documents)

> 890 TL (discounted from 1,700 TL original price, representing 48% off)

Three failures in one: reports the **list** price (890) as the selling
price, **fabricates** a 1,700 TL list price out of the fused `%21700`
digits, and invents a 48% discount — all at `confidence: high`. The
extraction-fidelity program (ADR-0003 extraction seam, ADR-0007 real-surface
grounding) must flip this to the reference above.
