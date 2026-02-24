# Military-Style Completion Badges — Design

## Problem
The leaderboard currently shows small ship render thumbnails (28px EVE images) inline after pilot names for completed savings goals. While functional, the thumbnails at 28px are hard to distinguish and lack visual punch. We want badges that are instantly recognizable and feel rewarding.

## Solution
Replace ship render thumbnails with custom-designed military-style shield/crest badges based on the ship's **category** (Titan, Super, Dread, Subcap). On hover, a rich Bootstrap popover shows the original ship render image + ship name — so no information is lost.

## Decisions
- **Badge style:** Shield/crest emblems — custom-designed images provided by a designer
- **Badge mapping:** One badge per category (4 categories: Titan, Super, Dread, Subcap)
- **File location:** `static/badges/<category_slug>.png` (e.g., titan.png, super.png, dread.png, subcap.png)
- **File format:** Support PNG or SVG — system handles either
- **Tooltip:** Rich HTML Bootstrap Popover showing 96px ship render image + ship name in bold
- **Category storage:** Add `category` column to `ship_orders` (persists even if catalog changes)
- **Backfill:** One-time SQL UPDATE joining to ship_catalog by ship_name for existing orders
- **Placeholders:** Ship with placeholder badges immediately; real art is a file swap with zero code changes
- **Visibility:** Always show (same as current behavior — completed goals are achievements regardless of is_public)

## Data Flow
1. Category stored on `ship_orders` at creation time (from catalog)
2. `get_completed_badges_for_active_users()` returns character_name, ship_name, type_id, category
3. Route builds badge dict with category included
4. Template renders badge image from `static/badges/` using `badge_url` filter
5. Bootstrap Popover initialized on hover with ship render + name

## Files Modified
- `database.py` — Add `category` column migration to `ship_orders`; call backfill
- `models.py` — Add `category` to `create_order()`; add `backfill_order_categories()`; update badge query
- `app.py` — Pass `category` at order creation; add `badge_url` filter; update leaderboard badge dict
- `templates/leaderboard.html` — Badge images + Popover replaces Tooltip
- `static/style.css` — Updated `.completion-badge` with cursor, transform hover
- `static/badges/` — New directory with placeholder badge images
- `CONTEXT.md` — Documentation
