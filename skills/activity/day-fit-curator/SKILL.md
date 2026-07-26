---
name: day-fit-curator
description: >
  Place activities on the correct calendar days given flight arrival, hotel nights,
  and pace — avoid clashes with travel days and over-packed schedules. Use when
  suggesting or booking activities for a dated itinerary, building a daily plan, or
  after flight/hotel times are known.
---

# Day-fit curator

Assign activities to **days that make sense**, not every blank slot.

## Hard stops (never violate)

1. **No activity on impossible days** — No major tours on long-haul arrival day unless user insists; no bookings after last flight day.
2. **Search before book** — `activity_search` until one activity per booking decision.
3. **One `activity_book` per activity** — Party size in `details`/Notes.
4. **user_id** always.

## Step 1 — Build day skeleton

From task / fetches:
- Day 0: travel to destination (arrival time)
- Day 1…N-1: full days at destination
- Day N: departure (morning travel?)

Mark **low-energy** days (arrival, red-eye aftermath) vs **full** days.

## Step 2 — Pace rules

Default caps unless user wants packed schedule:
- Arrival day: 0–1 light items
- Full days: 1 major + optional 1 light
- Departure day: none or morning-only short activity

Respect `preferred_travel_types` (leisure vs business — business may skip daytime tours).

## Step 3 — Search and slot

`activity_search` by location/keywords; map results to days:
- Long tours → full days
- Evening experiences → days without early next-day flight
- Family items → align with `special_preferences`

## Step 4 — Deliverable (research)

**Day-by-day outline** (mandatory for curation tasks)  
Each item: activity **name**, not `recommendation_id` in user-facing lines.

Example:  
**Thu Jul 24** — Arrival evening: (optional) short walk  
**Fri Jul 25** — Morning: Tour A; Afternoon: free  
…

## Step 5 — Book

Only activities the user/main agent confirmed; one book each; put day/time intent in `details`.

## Integration

- `theme-packs` for themed shortlists before slotting
- `change-of-plans` → re-curate affected days

## Example intents

- “Spread these three tours across our four full days in Zurich.”
- “Don’t book anything on our arrival day.”
