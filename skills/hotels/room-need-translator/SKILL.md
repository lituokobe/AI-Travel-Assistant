---
name: room-need-translator
description: >
  Translate party size and preferences into plain-language room and occupancy
  guidance for hotel search and booking notes without inventing extra guest profiles.
  Use when the task mentions adults, children, family, rooms, occupancy, or
  multi-person stays in demo mode (single logged-in user).
---

# Room-need translator

Map **who is traveling** to **how we describe the stay** — one `user_id`, honest headcount.

## Hard stops (never violate)

1. **Single account demo** — Book **one** `hotels_book` per stay; do not create fake guest IDs.
2. **No fabricated room types** — Catalog may not expose room SKU; describe needs in `details`/Notes and standard book args only.
3. **Headcount in Notes** — Always state adults/children counts the user gave.

## Step 1 — Parse party

From task or `request_travel_info`:
- Adults count
- Children (ages if given)
- Infants / “baby friendly” from `special_preferences`
- Bed/space needs (connecting room, crib — as **requests**, not guaranteed inventory)

## Step 2 — Translate to search bias

Adjust `hotels_search` keywords/location narrative:
- Family → family-friendly areas, quieter districts if preferences say so
- Business → central / transit if `special_preferences` include public transportation
- Large party → note “may need 2 rooms” as **advice** if catalog cannot split bookings (still one book under demo rules unless user asks otherwise)

## Step 3 — Booking language

On `hotels_book`:
- Same `user_id`
- In Notes / customer summary:
  - “Reservation for Luis (ID: …), **2 adults**”
  - “Please note: traveling with child (~age X) — crib request if available”

Do **not** repeat `hotels_book` per adult.

## Step 4 — Communicate limits honestly

If search doesn't expose a specific room SKU:
- “Exact room configuration isn’t in search; I’ve noted your party size for the property.”

## Integration

- Always pair with `stay-aligned-to-flights` for dates.
- Main agent party-size rules apply in user-visible text.

## Example intents

- “Book the hotel for me and my partner — 2 adults.”
- “Family of 4 with two kids — find something suitable near the old town.”
