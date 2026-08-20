---
name: stay-aligned-to-flights
description: >
  Set hotel check-in and check-out dates from confirmed or proposed flight times,
  including buffers for late arrival and early departure. Use when booking or
  searching hotels for a flown trip, package assembly, or after flight date changes
  — always align lodging to the flight window, not calendar guesses.
---

# Stay aligned to flights

Hotel dates must **follow the flight anchor**, not arbitrary calendar defaults.

## Hard stops (never violate)

1. **Check-out after check-in** — Validate date order before `hotels_book` / `hotels_update`.
2. **No probe-booking** — Search and compare options until one hotel is chosen.
3. **One hotel book per decision** — No multi-hotel comparison via booking.
4. **user_id** on all fetch/book/update/cancel calls.

## Step 1 — Obtain flight anchor

From the delegated task or prior flight results:
- **First arrival** at destination (date + time if available)
- **Last departure** from destination (date + time)

If flights are not finalized, use the **proposed** package dates and label them “pending flight confirmation.”

## Step 2 — Derive stay dates

Rules of thumb (adjust in Notes when task specifies):
- **Check-in** — Arrival **date**; if arrival after ~22:00 local, note late check-in may be needed (do not invent hotel policy).
- **Check-out** — Departure **date**; if departure before ~10:00, previous night is last paid night.
- **Timezone** — Use airport city dates from flight schedule strings; if ambiguous, state assumption.

Count **nights** explicitly in the summary (checkout − checkin).

## Step 3 — Search hotels

`hotels_search` with location/name from task; filter mentally to dates computed.

If stay length changes (user changes flights), re-run search — do not book old dates.

## Step 4 — Present options (research tasks)

For each candidate hotel:
- Name / area / price (EUR/night)
- Check-in → check-out (nights)
- One line on proximity or preference fit

## Step 5 — Book

`hotels_book` only with:
- `user_id`, chosen `hotel_id`
- `checkin_date`, `checkout_date` from Step 2

Party size > 1: **one** reservation; mention guests in Notes (`room-need-translator`).

## Integration

- After `change-of-plans` flight moves → recompute Step 2 before update/book.
- Main `compound-travel-package` Step 3 expects this alignment.

## Return format

Standard hotel `[Operation Result]` blocks; Notes include night count and flight reference (numbers, not internal ids).

## Example intents

- “Search hotels for the Jul 24–28 flights we picked.”
- “Update hotel dates to match the new return flight on Aug 2.”
