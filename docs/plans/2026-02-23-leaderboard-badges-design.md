# Leaderboard Completion Badges — Design

## Problem
The first user completed a savings goal. There's no way to recognize past achievements on the leaderboard. We want a visual "trophy case" that celebrates completed goals.

## Solution
Show small EVE ship render images ("badges") inline after each pilot's name on the leaderboard. Each badge represents a previously completed savings goal. On hover, a Bootstrap tooltip shows the ship name they earned.

## Decisions
- **Scope:** Active pilots only (must have a current active goal to appear on leaderboard)
- **Placement:** Inline after pilot name in the Pilot column
- **Privacy:** Badges always show — completed goals are achievements regardless of `is_public`
- **Architecture:** Route handler lookup dict — `get_leaderboard()` stays untouched
- **Badge size:** 28px CSS, 64px image request (crisp on Retina)
- **Tooltip:** Bootstrap 5 tooltip (already loaded via bundle)
- **NULL type_id:** Filtered out in SQL — old orders without images silently skipped

## Data Flow
1. New `models.get_completed_badges_for_active_users()` queries completed orders for users with active goals
2. Route handler builds `badges` dict keyed by `character_name`
3. Template loops `badges.get(name, [])` to render `<img>` tags with tooltip attributes

## Files Modified
- `models.py` — new query function
- `app.py` — updated leaderboard route
- `templates/leaderboard.html` — badge rendering + tooltip init script
- `static/style.css` — `.completion-badge` class
- `CONTEXT.md` — documentation
