---
name: compound-travel-package
description: >
  Plan multi-product trips (flights + hotels, optional car/activity) under a shared
  budget. Always research first, present 2–4 package options, wait for the user to
  choose one package, then book only that package (one flight set, one hotel, etc.).
  Never book multiple hotels/cars to “probe” prices. Use when the user asks for a
  trip package, business trip with stay + transport, family package, or any request
  spanning more than one travel product with a budget or date window.
---

# Compound travel package

Use this skill whenever the user wants a **combined trip** (not a single product).

## Skills vs todo list (DeepAgents)

- **Skill** = the durable playbook (order of work, hard stops, what to present).
- **`write_todos`** = the operational checklist for *this* turn, derived from the skill.

You may load the skill once at the start of a package request. On later turns in the
same package conversation, you do **not** need to re-show a skill load in thinking —
but you **must still obey** this playbook. Prefer todos that mirror Steps 1–6 below.
If the user’s constraints change (dates, budget, stay length), **update todos** and
keep following this skill; do not invent a parallel “research then book everything”
workflow.

Re-read this file with `read_file` if you are unsure whether booking is allowed yet.

## Hard stops (never violate)

1. **Present before book** — After research, show **2–4 package options** and wait
   for the user to pick **one** package. Do not call any `*_book` tool until then.
2. **One hotel per package / one booking after choice** — A package contains at most
   one hotel recommendation. After the user picks a package, book **that** hotel only
   (plus matching flights / car if included). Never book 2+ hotels in the same turn.
3. **No probe-booking** — Catalog search may only return `price_tier` / coarse prices.
   Report that honestly. **Never** call `hotels_book` / `car_book` / `flights_book`
   “just to discover pricing.” Booking is a customer commitment, not a price lookup.
4. **No multi-book for comparison** — Do not book Option A, B, and C in parallel to
   compare. Compare using search/fetch results only; let the user choose; then book once.

## Step 1 — Confirm constraints

Collect or confirm (use `request_travel_info` only if truly blocking):
- Origin / destination (and airports if known)
- Depart window and stay length (e.g. 4–5 nights) or return window
- Party size
- Budget and currency (from preferences if not stated)
- Whether car / activities are needed

If the user says “pick the cheapest dates within this window,” treat date selection as
part of package assembly — not as a reason to skip presentation.

## Step 2 — Flights first

Delegate flight research for the date window. Prefer options that leave room in the
budget for hotel (+ car if needed). Summarize a shortlist of viable round-trips
(including nearby airports when the destination has no direct flights).

## Step 3 — Hotels aligned to flight windows

For the best flight date windows only, search hotels (several tiers if possible).
Align check-in/out to those flights. Do **not** book.

## Step 4 — Optional cars / activities

Add only if asked or clearly needed. Search only; do not book yet.

## Step 5 — Build 2–4 packages (mandatory user-facing deliverable)

Create **Package A / B / C** (and D if useful). Each package must include:
- Flights summary (route, dates/times, rough cost if known)
- Hotel summary (name/area, nights, price tier or rough cost)
- Optional car/activity lines
- **Estimated total** in the user’s currency (or clear “tier only” caveat)
- One-line trade-off ("cheapest", "best times", "nicer hotel")

Rules:
- Prefer under budget; if impossible, show closest options and say what exceeds budget
- Do not invent prices or availability
- Make packages meaningfully different
- End with an explicit ask: which package should we book?

## Step 6 — Booking only after explicit choice

When the user picks a package (e.g. “Package B” or names the hotel/flights):
1. Book / change flights for that package only
2. Then book **one** hotel matching those dates
3. Then optional car/activity
4. Confirm the full package in one clear customer-facing summary

Approvals may pause the run — expected. Never batch-approve multiple alternative hotels.

## Todo-list guidance

When using `write_todos`, prefer this shape:
1. Confirm dates, party size, budget
2. Research flight options
3. Research hotels aligned to flight windows
4. (Optional) Research cars / activities
5. **Assemble 2–4 packages and present for user choice** ← stop here until they reply
6. Book **selected** package only (flight → hotel → …)

Do **not** write todos like “test book all hotels for Option A to determine pricing.”

## Mid-turn user messages

While research is in progress:
- Prefer silence until a real milestone, **or**
- Send a **concrete** progress update only (“Found 3 round-trips via Basel; next I’ll check hotels for Jul 24–28.”)

Never send vague filler (“Good progress”, “important findings”, “let me continue”)
as if it were the final answer while work is still running.

## User-facing communication (mandatory)

- One assistant voice; no sub-agent / tool / skill / backend vocabulary
- On failures: brief apology + outcome + next step
- Never quote SQL, stack traces, or "backend error"
- Match `communication_style` while staying professional

## Example intents

- "Plan a 3-day London family trip under 3000."
- "Book me flights and a hotel in Tokyo next month, keep it under SGD 2500."
- "Business trip to Zurich in the next few days; budget 5000; I need a car."
