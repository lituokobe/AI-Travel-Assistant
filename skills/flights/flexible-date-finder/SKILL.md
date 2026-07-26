---
name: flexible-date-finder
description: >
  Find better flight dates inside a flexible window (e.g. ±3 days, cheapest week,
  long weekend) by searching multiple date bands and ranking round-trips or one-way
  options. Use when the user or task mentions flexible dates, cheapest in range,
  shift by a few days, or date window without fixed depart day.
---

# Flexible-date finder

Optimize **when** to fly inside a window without asking the user to guess each date.

## Hard stops (never violate)

1. **Search only** unless the task explicitly names book + chosen dates.
2. **Honest pricing** — If search exposes only schedules/tiers, say so; never probe-book.
3. **Bounded window** — Default ±3 days or the task’s stated range; do not exhaust infinite calendars.
4. **passenger_id = user_id** on any book; party size in Notes only.

## Step 1 — Define the window

- Anchor destination and origin airports
- Flexible outbound range and return range (or trip length: “4–5 nights”)
- Constraints: avoid weekends, must return by X, business hours preference

## Step 2 — Sample the window

Strategy (efficient):
- Search 3–5 representative outbound dates (start, middle, end of window)
- For each viable outbound, search return dates matching trip length band
- Reuse `round-trip-assembler` pairing logic when return is required

Do not exceed ~6–8 search calls without summarizing partial results.

## Step 3 — Rank candidates

Score by:
- Schedule quality (red-eye penalty if `special_preferences` imply it)
- Tier / qualitative cost vs `price_sensitivity`
- Alignment with hotel/car needs if stated in task (“need Friday night arrival”)

## Step 4 — Deliverable

Present **top 3 date combinations** (not 20 rows):

| Rank | Outbound date | Return date | Highlight |
|------|---------------|-------------|-----------|
| 1 | … | … | Best balance |
| 2 | … | … | Cheapest tier signal |
| 3 | … | … | Best times |

Each row: sample flight numbers/times from search (real rows only).

Ask which combination to use for full shortlist or booking.

## Step 5 — Handoff

- Main agent packages → feed chosen dates into hotel search (`stay-aligned-to-flights`)
- Booking → one book per leg after user/main confirms exact `flight_id`s

## Notes for `[Notes]`

- State search window searched and if wider search is needed
- Customer-safe language only

## Example intents

- “Cheapest weekend in July for CDG–BSL, ±2 days flexible.”
- “Pick depart date within Jul 20–25 that works with 4-night stay.”
