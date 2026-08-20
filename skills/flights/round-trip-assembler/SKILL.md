---
name: round-trip-assembler
description: >
  Search and present coherent round-trip flight options: pair outbound and return
  legs, summarize total journey quality, and return structured shortlists for the
  main agent. Use when the task involves return travel, round trip, both ways, or
  package flights — not for one-way-only changes (use update/cancel workflow).
---

# Round-trip assembler

Produce **paired itineraries** (outbound + return), not isolated leg dumps.

## Skills vs todo list

- **Skill** = pairing rules, ranking, and output shape for the main agent.
- **`write_todos`** = multi-city or multi-window searches.

Re-read if the task says **book** — booking requires explicit flight choice and approval.

## Hard stops (never violate)

1. **Search before book** — `flights_search` until the task explicitly requests booking one named itinerary.
2. **No duplicate books** — Party size > 1: one `flights_book` per **distinct** flight_id; note headcount in Notes.
3. **One book per model turn** — Never issue two `flights_book` calls in the same step (parallel outbound + return breaks approval). Book leg 1, then leg 2 on the next step.
4. **3-hour rule** — Do not book flights departing within 3 hours; filter or warn in summaries.
5. **passenger_id** — Always the task’s `user_id`; never invent passengers.
6. **Customer-safe failures** — No SQL, stack traces, or “backend error” in Notes.

## Step 1 — Extract search window

From the delegated task:
- Origin / destination airports (or cities → infer reasonable airports)
- Outbound window (`start_time` / `end_time` on search)
- Return window (separate search or second filter pass)
- Limits: red-eye, airline memberships from context (preferential ranking only)

## Step 2 — Search legs

- Search outbound: departure_airport → arrival_airport in depart window
- Search return: arrival_airport → departure_airport in return window

Use `limit` responsibly; widen window once before giving up.

## Step 3 — Pair and rank

Pair legs by:
- **Date feasibility** — return after outbound arrival (same day only if connection time realistic)
- **Total time burden** — avoid brutal layovers unless no options
- **Price (EUR)** — rank by fare from search results for `price_sensitivity: low`

Drop impossible pairs (return before outbound lands).

## Step 4 — Present 2–5 round-trips (mandatory shape)

For each option:
- **Option label** (e.g. Round-trip 1)
- Outbound: flight number, route, scheduled departure (local display)
- Return: flight number, route, scheduled departure
- Trade-off line (cheapest, best times, fewest connections)
- Internal `flight_id` values only in `[Flight Details]` for main agent — not as primary user identifiers

## Step 5 — Book only when instructed

When task says book a specific pair:
1. `flights_book` outbound `flight_id`
2. After approval/success, `flights_book` return `flight_id` (sequential, not parallel duplicate calls for party size)

## Return format

Use the standard `[Operation Result]` / `[Operation Type]` / `[Flight Details]` / `[Notes]` blocks.

## Example intents (via main agent task)

- “Find round trips SIN–ZRH Jul 24–28 for 2 adults.”
- “Shortlist RT options for the package skill, leave room in budget for hotel.”
