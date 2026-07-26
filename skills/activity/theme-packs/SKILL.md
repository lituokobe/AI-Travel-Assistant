---
name: theme-packs
description: >
  Curate themed activity shortlists (family, culture, food, outdoors, business-friendly)
  from catalog search and user preferences before booking. Use when the user asks for
  things to do by theme, kid-friendly ideas, food tours, or activity ideas for a
  destination — search and rank only until they pick one to book.
---

# Theme packs

Turn vague “what should we do?” into **named themed shortlists** the user can choose from.

## Hard stops (never violate)

1. **Real catalog items** — Every listed activity must appear in `activity_search` results.
2. **No book until chosen** — Present packs; single `activity_book` after explicit pick.
3. **No duplicate books** for party size — one reservation with headcount in Notes.
4. **Names, not IDs** — User-facing lines use activity titles and locations.

## Step 1 — Select themes (2–4 packs)

Map from `preferred_travel_types` and task keywords, e.g.:
- **Family pack** — interactive, shorter duration, baby-friendly cues
- **Culture pack** — museums, old town, heritage
- **Food pack** — markets, walking tastings (describe from catalog names)
- **Outdoors pack** — scenic, light adventure
- **Business-travel pack** — evening-only, near city center, ≤2 hours

Skip themes with zero search hits.

## Step 2 — Search per theme

`activity_search` with location + `keywords` / `name` filters.

3–5 items per pack max; dedupe across packs.

## Step 3 — Deliverable format

**Pack A — Family**  
1. Activity name (location) — one-line why it fits  
2. …

**Pack B — Culture**  
…

End with: “Which pack should I flesh out into a day plan, or which single activity should I book?”

## Step 4 — Next steps

- User picks pack → hand to `day-fit-curator` for scheduling
- User picks one item → `activity_book` with `recommendation_id` and optional `details`

## Personalization

Use `special_preferences` (vegan, public transportation, baby friendly) to reorder items, not to invent venues.

## Example intents

- “Kid-friendly things in Basel for our long weekend.”
- “Give me a food-focused and a culture-focused list.”
