---
name: change-of-plans
description: >
  Handle trip changes after plans or bookings exist: date shifts, cancellations,
  rebooks, and cascading updates across flights, hotels, cars, and activities.
  Use when the user says plans changed, delay or move dates, cancel part of the
  trip, rebook, swap hotel, or fix a booking after disruption — not for first-time
  package planning (use compound-travel-package instead).
---

# Change of plans

Use when the user already has a **draft itinerary, pending approvals, or confirmed
bookings** and wants to **change** something — not when they are starting a new trip
from scratch.

## Skills vs todo list

- **Skill** = order of operations, safety gates, and how to explain impact to the user.
- **`write_todos`** = this change’s checklist (discover → propose → confirm → execute).

Re-read this file with `read_file` if you are unsure whether to book or only research.

## Hard stops (never violate)

1. **Discover before mutate** — Call the right `*_fetch` (via sub-agents) for this
   `user_id` before cancel/update/book. SQLite is the source of truth; never guess
   ticket or reservation numbers.
2. **One coherent proposal** — Present what will change (old → new) and ask for
   confirmation before destructive steps. Do not cancel and rebook silently.
3. **Sequential booking changes** — When multiple products must change, execute in
   order: **flights first** (they anchor dates), then hotel, then car, then
   activities. Do not parallelize flight-book and hotel-book tasks.
4. **No probe-booking** — Use search/fetch only to compare alternatives; book only
   after the user picks one option.
5. **Party size** — One book per distinct product under this user; state headcount
   in summaries; do not duplicate identical book calls per traveller.

## When to use vs not use

| Use | Do not use |
|-----|------------|
| “Move my return flight by one day” | “Plan a new trip to Tokyo” → `compound-travel-package` |
| “Cancel the hotel but keep flights” | Pure destination Q&A → `web_search` |
| “Something came up — shift the whole trip” | Compare two cities before choosing → `compare-destinations` |

## Step 1 — Clarify the change

Establish:
- What is **fixed** vs **flexible** (dates, destination, budget)
- Which products are affected (flights / hotel / car / activities)
- Whether bookings already exist or only options were discussed

Use `request_travel_info` only if blocking (e.g. new return date unknown).

## Step 2 — Inventory current state

Delegate fetches as needed:
- Flights → `flights_fetch` (tickets, segments)
- Hotels → `hotels_fetch`
- Car → `car_fetch`
- Activities → `activity_fetch`

Summarize internally: reservation IDs / ticket numbers, dates, names (not internal catalog IDs in user text).

## Step 3 — Impact analysis (user-facing)

Explain in plain language:
- What stays valid vs what must change
- **Cascade**: e.g. later return flight → hotel checkout, car return, last activity day
- Risks: non-refundable assumptions (honest; do not invent policies)

## Step 4 — Propose a change plan

Offer **one recommended path** plus **one alternative** when reasonable, e.g.:
- **A)** Rebook outbound; update hotel check-in; adjust car pickup
- **B)** Cancel hotel; re-search stays for new dates (search only until they choose)

Wait for explicit approval before book/update/cancel.

## Step 5 — Execute in order

1. Flights: `flights_update` / `flights_cancel` / `flights_book` as needed — finish + HITL
2. Hotels: `hotels_update` / `hotels_cancel` / `hotels_book`
3. Car, then activities

After each step, confirm outcome before the next delegation.

## Step 6 — Close with a refreshed summary

One message: new dates, what was cancelled/changed, what remains to book, and next optional steps.

## Integration with other skills

- **Hotels** sub-agent: apply `stay-aligned-to-flights` when recomputing stay dates.
- **Flights** sub-agent: `round-trip-assembler` / `flexible-date-finder` for new date windows.
- **Activity** sub-agent: `day-fit-curator` to drop or move activities on affected days.

## User-facing communication

- One assistant voice; no sub-agents, tools, or internal IDs
- Use flight numbers, hotel names, activity titles
- On failure: brief apology + outcome + next step

## Example intents

- “Push my whole Zurich trip back by two days.”
- “Cancel the activity on Friday but keep the hotel.”
- “My meeting moved — I need a later return flight and to extend the hotel.”
