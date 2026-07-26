---
name: one-way-multi-day-rental-shaping
description: >
  Shape car rental start and end dates from flight arrival/departure and hotel stay,
  including multi-day coverage only where driving is needed. Use when booking or
  searching rentals for a trip with known flights/hotels, one-way rental questions,
  or aligning pickup/drop with itinerary days.
---

# One-way / multi-day rental shaping

Rent a car for the **right days**, not the whole calendar by default.

## Hard stops (never violate)

1. **Align to itinerary** — Pickup after flight lands; return before flight departs (buffers in Notes).
2. **No probe-booking** — `car_search` until one rental is chosen.
3. **One `car_book` per decision** — Party size in Notes only.
4. **user_id** on all operations.

## Step 1 — Anchor times

Gather from task:
- Flight arrival datetime / airport
- Flight departure datetime / airport
- Hotel location if relevant
- Whether user needs car **entire stay** or **specific days** (e.g. day trips only)

## Step 2 — Propose rental window

| Scenario | Start | End |
|----------|--------|-----|
| Airport pickup | Arrival date (or +1 day if late arrival + sleep first) | Day before departure or departure morning |
| City stay only | First day needing car | Last day needing car |
| One-way mention | Same catalog location unless task confirms different drop-off — **demo**: assume round-trip rental at same location unless data supports one-way |

State **inclusive day count** in summary.

## Step 3 — Search

`car_search` by location/name near pickup point (airport city or hotel area).

Rank by `price_tier` vs `price_sensitivity`.

## Step 4 — Present

2–4 options with:
- Company name / location / tier
- Proposed start_date → end_date
- Why window fits flights

## Step 5 — Book

`car_book` with `user_id`, `rental_id`, `start_date`, `end_date`.

After flight or hotel change → recompute window before `car_update`.

## Integration

- `stay-aligned-to-flights` for hotel nights
- Main `change-of-plans` for cascade updates

## Example intents

- “Rent a car from Basel airport when we land until we leave.”
- “Car only for the two days we visit the mountains.”
