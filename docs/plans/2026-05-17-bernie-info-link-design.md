# Bernie May Doff Info Link — Design

**Date:** 2026-05-17

## Goal

Every mention of "Bernie May Doff" in the member-facing UI becomes a clickable affordance to (a) view his character info on evewho.com and (b) copy his name to clipboard for pasting into EVE's wallet "Give Money" dialog.

EVE's literal `showinfo:` URL is in-game-only (the in-game browser was removed in 2016), so we use a 3rd-party character lookup site as the closest practical substitute.

## User-facing display

Wherever "Bernie May Doff" appears today, it renders as:

```
Bernie May Doff ↗ 📋
```

- **Name** — clickable anchor to `https://evewho.com/character/{ADMIN_CHARACTER_ID}`, opens in new tab. Styled white/bold to match existing look; underline on hover, pointer cursor.
- **↗ glyph** — small visual cue that the name links externally. Sits inside the anchor.
- **📋 button** — separate small icon button immediately after the name. Click copies "Bernie May Doff" to clipboard via `navigator.clipboard.writeText`, briefly flashes a "Copied!" tooltip / label change.

## Surfaces touched

Five places where the name currently appears (from grep):
1. `templates/dashboard.html:47` — recurring "Send ISK to Bernie May Doff" callout
2. `templates/dashboard.html:167` — "Goal approved! Send ISK..." block
3. `templates/dashboard.html:204` — "How to send ISK" instructions
4. `templates/order_detail.html:271` — deposit instructions on a member's goal
5. `templates/loan_detail.html:192` — loan repayment instructions

## Implementation surface

1. **Context processor in `app.py`** — injects `admin_character_name` (constant string `"Bernie May Doff"`) and `admin_evewho_url` (`f"https://evewho.com/character/{Config.ADMIN_CHARACTER_ID}"`) into every template render.

2. **Jinja macro `bernie_link()` in a new `templates/_macros.html`** — renders the link + copy unit so all five sites use one source of truth.

3. **Replace the 5 hardcoded mentions** with `{% from '_macros.html' import bernie_link %}{{ bernie_link() }}`.

4. **JS handler in `templates/base.html`** — global event delegation on `[data-copy-value]` elements. On click: `navigator.clipboard.writeText(el.dataset.copyValue)`, briefly swap the button's tooltip/label to "Copied!" for ~1.2s, then restore.

## Scope decisions

- **One source of truth for the name + URL.** Context processor + macro means changing the admin character is a single-file edit.
- **The hardcoded literal "Bernie May Doff" string lives in the context processor** — it's not pulled from `users` table or ESI. That'd be a separate plumbing concern (out of scope).
- **No keyboard shortcut**, **no global persistent banner**, **no toast library**. Tiny inline feedback only.
- **No back-end change.** The link is generated from `Config.ADMIN_CHARACTER_ID`; the copy action is pure JS.

## Verification

- Visit dashboard, order detail, loan detail — each "Bernie May Doff" is rendered as the link+copy unit.
- Click the name — evewho opens in a new tab to Bernie's character.
- Click the copy icon — name lands in clipboard, "Copied!" label flashes briefly.
- Right-click on the link offers normal "Open in new tab" / "Copy link address" browser actions.
