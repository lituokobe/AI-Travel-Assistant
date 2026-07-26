---
name: pre-trip-checklist
description: >
  Build a practical pre-departure checklist for an upcoming trip: documents, timing,
  weather, local tips, and alignment with existing bookings. Use when the user asks
  what to prepare before leaving, pre-trip checklist, what to pack, visa/passport
  reminders, or getting ready for a booked or planned trip — not for searching or
  booking inventory (delegate those to sub-agents).
---

# Pre-trip checklist

Turn **known trip context** (preferences + bookings + dates) into a **scannable
checklist** the user can act on before departure.

## Skills vs todo list

- **Skill** = what to include, what to verify, and how to use `web_search` safely.
- **`write_todos`** = optional for long trips (gather bookings → research → deliver).

## Hard stops (never violate)

1. **Bookings from DB** — If the user asks what they booked, delegate `*_fetch`; do not invent flights or hotels.
2. **No legal advice** — Visa/entry rules: summarize from `web_search` with uncertainty; suggest official sources for final decisions.
3. **Time-sensitive facts** — For weather or entry rules, prefer current-season search; if stale or empty, say so honestly.
4. **No booking** — This skill is preparation only unless the user separately asks to book something missing.

## Step 1 — Anchor the trip

Confirm or infer:
- Destination(s) and travel dates (from conversation or fetches)
- Party size and `special_preferences` (baby friendly, vegan, mobility, etc.)
- `base_city` / departure airport context from preferences

If dates or destination are unknown, ask one focused question or use fetches first.

## Step 2 — Load booking reality (when relevant)

If the trip is booked or partially booked, delegate fetches and extract:
- Flight times (first departure, last return) — buffer for airport arrival
- Hotel check-in/out
- Car pickup/return windows
- Activity dates

## Step 3 — Research supplements (main agent `web_search`)

Use targeted queries, e.g.:
- Seasonal weather for destination and dates
- Public holidays or major events that affect crowds
- General entry/document reminders for `passport_nationality` (high level only)

Do not fabricate requirements; cite uncertainty when sources conflict.

## Step 4 — Build the checklist (mandatory deliverable)

Use sections the user can skim:

**Documents & admin**
- Passport validity reminder (generic “often 6 months” unless search says otherwise)
- Tickets / reservation numbers they already have (from fetch)
- Travel insurance prompt if user cares about business/leisure type

**Timing & logistics**
- Leave-for-airport suggestion based on first flight (reasonable default, not airline-specific unless known)
- Check-in time vs hotel arrival; late arrival notes
- Car pickup aligned to flight arrival if applicable

**Health, comfort, and preferences**
- Map `special_preferences` (layers, adapters, child gear, dietary notes)
- `preferred_currency` / payment reminders if international

**On arrival**
- 2–3 practical tips from search (transit, SIM, tipping) — short bullets

**Before you go**
- Confirm bookings still on file (offer to re-fetch if they want)

End with: “Want me to adjust this for carry-on only / business meetings / kids?”

## Step 5 — Optional follow-ups

- Offer `change-of-plans` if they discover a conflict
- Offer `compound-travel-package` only if they are still planning, not preparing

## User-facing communication

- Warm, concise, professional; match `communication_style`
- No tool/skill/backend vocabulary
- Distinguish **confirmed bookings** vs **general travel tips**

## Example intents

- “I leave for Basel in four days — what should I prepare?”
- “Pre-trip checklist for my London booking.”
- “Anything I should know before flying with a toddler to Japan?”
