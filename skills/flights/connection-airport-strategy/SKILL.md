---
name: connection-airport-strategy
description: >
  Improve flight options using nearby airports, connection timing, and hub routing
  when direct flights are weak or missing. Use when the task mentions alternate
  airport, connect via hub, no direct flights, Basel/Zurich style multi-airport
  regions, or minimize layover / avoid tight connections.
---

# Connection / airport strategy

Expand the **search space** intelligently when a single airport pair is too thin.

## Hard stops (never violate)

1. **Real flights only** — Every suggested leg must come from `flights_search` results.
2. **Minimum connection sanity** — Flag sub-90-minute international self-transfers as risky; prefer single-ticket style pairs when data is one airline/hub (heuristic only).
3. **No book until chosen** — Strategy and shortlists first.
4. **User-facing** — Lead with airport names and flight numbers, not `flight_id`.

## Step 1 — Map the region

From task context:
- Primary city destination
- Reasonable **alternate airports** (e.g. destination metro: BSL/ZRH/GVA; origin: city multi-airport)
- User tolerance: extra ground time vs fewer stops (`price_sensitivity`, `special_preferences`)

## Step 2 — Search patterns

Execute searches as needed:
- O&D primary pair
- Origin alt → destination
- Origin → destination alt
- Hub routing: origin → hub → destination (two search segments or filter connections from broader results if catalog supports)

Cap total searches; prefer the 2–3 most plausible airport combos.

## Step 3 — Classify strategies

Label each viable strategy:
- **Direct** — fewest moving parts
- **Nearby airport** — fly to alt + ground transfer (mention qualitatively)
- **Hub connect** — one stop, note layover duration from schedules
- **Open jaw** — only if task allows different return airport

## Step 4 — Recommend 2–3 strategies

For each:
- Why it helps (price tier, schedule, availability)
- Trade-offs (early start, late arrival, ground segment)
- Sample flights from search

End with a single recommendation aligned to `price_sensitivity` and trip type.

## Step 5 — Booking

Book only the **specific** `flight_id`s the user/main agent confirmed; sequential books for multi-segment itineraries, one call per segment, no party-size duplication.

## Integration

- Combine with `round-trip-assembler` for return pairing
- Combine with `flexible-date-finder` when hub options vary by day

## Example intents

- “No direct to Basel — try Zurich or via Frankfurt.”
- “Avoid 45-minute connections; show safer routings.”
