---
name: compare-destinations
description: >
  Compare two or more destination options for a trip the user has not committed to
  yet: fit for party type, season, budget band, and travel style using preferences
  and web_search — without booking. Use when the user asks which city/country is
  better, A vs B, family-friendly choice, or where to go under a budget — not when
  they already chose a destination and want flights/hotels (delegate or package skill).
---

# Compare destinations

Help the user **choose where to go** before locking flights or hotels.

## Skills vs todo list

- **Skill** = comparison framework, evidence rules, and when to stop at decision support.
- **`write_todos`** = useful for 3+ destinations or multi-criteria comparisons.

## Hard stops (never violate)

1. **No booking** — Do not call sub-agent book tools; at most light catalog **search** if the user asks “can we afford either?” and you need cost signals — still no `*_book`.
2. **No fabricated prices** — Use the price + currency (EUR) from search results and the user's budget band from preferences.
3. **Personalize** — Always apply `preferred_travel_types`, `price_sensitivity`, `special_preferences`, party size.
4. **Decisive finish** — End with a clear recommendation and one question (“Which should I plan in detail?”).

## Step 1 — Frame the decision

Capture:
- Candidate destinations (2–4; if more, ask to narrow)
- Time window or season (flexible vs fixed)
- Party composition and trip purpose (leisure, business, family)
- Budget cap in `preferred_currency` if stated

## Step 2 — Criteria matrix (internal)

Score each destination on dimensions the user cares about, e.g.:
- Weather / season fit (web_search)
- Flight distance and rough convenience from `base_city` (qualitative; delegate flight **search** only if user wants a concrete sample itinerary)
- Family / food / safety / pace fit from preferences
- Relative cost (price + currency from catalog search when available)

## Step 3 — Research (`web_search`)

Run focused queries per destination; avoid long essays in the reply.

Note source uncertainty for time-sensitive facts.

## Step 4 — Deliverable format (mandatory)

Present a **comparison table or parallel sections**:

| | Destination A | Destination B |
|---|----------------|-----------------|
| Best for | … | … |
| Weather (your dates) | … | … |
| Budget fit | … | … |
| Caveats | … | … |

Then:
- **Recommendation** in one paragraph (“For 2 adults and medium budget, B edges ahead because…”)
- **If you pick A / B, next step** — offer to run `compound-travel-package` or single-product search

Do not book until they choose a destination and package.

## Step 5 — Handoff

When they pick a winner → switch to `compound-travel-package` or targeted delegation (flights first for dated trips).

## User-facing communication

- Neutral, helpful tone; no winner-takes-all unless user asked for a single pick
- No internal architecture or catalog IDs
- Distinguish catalog search prices (quoted EUR) from web_search estimates (indicative)

## Example intents

- “Malaysia or Thailand for a family with a baby in August?”
- “Zurich vs Geneva for a 4-night long weekend — which is easier?”
- “We have SGD 3000 — better value, Tokyo or Seoul?”
