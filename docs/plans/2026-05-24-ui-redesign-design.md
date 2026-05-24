# UI Redesign — Bank-style Reskin

**Date:** 2026-05-24
**Status:** Design approved. Implementation plan pending (separate `writing-plans` session).

## Goal

Shift the visual aesthetic of the Sihcom Savings and Loans app from its current Bootstrap 5 dark theme to a traditional bank-website look (Fifth Third Bank-ish). The motivation is a vibe shift, not a functional change — but Phase 2 also delivers a public marketing surface and folds in the deferred Terms-of-Service content as per-product rules sections.

## Approach

Phased rollout in three shippable phases. Phase 3 is optional.

- **Phase 1 — Foundation.** Design system + reskin of all existing templates (member + admin). No new routes, no logic changes.
- **Phase 2 — Public product surface.** New routes `/savings`, `/loans`, `/credit-lines`. Landing page redesigned with hero + product grid. Per-product rules sections.
- **Phase 3 (deferred).** Dashboard product cards. Evaluate after Phase 2 lands; may not be needed.

Rejected alternatives:

- **Big-bang single PR** — too risky, too large to review, and the user's commit policy favors bundling by default but not single mega-PRs for redesigns of this scope.
- **Pilot one page** — bank sites are visual systems; a half-redesigned app reads worse than either endpoint during the in-between.

## Phase 1 — Foundation

### Design tokens

CSS custom properties on `:root`. All colors named with `--sl-` prefix to avoid Bootstrap collisions.

| Token | Value | Use |
|---|---|---|
| `--sl-bg` | `#fafaf7` | Page background (cream) |
| `--sl-surface` | `#ffffff` | Cards, tables, nav |
| `--sl-ink` | `#1a1f2c` | Body text |
| `--sl-muted` | `#5a6472` | Secondary text, metadata |
| `--sl-border` | `#e3e5e8` | Card borders, table dividers |
| `--sl-navy` | `#003765` | Primary actions, links, headlines |
| `--sl-navy-hover` | `#002a4d` | Hover state |
| `--sl-green` | `#00834a` | Positive money (deposits, interest, paid in full) |
| `--sl-red` | `#a8232b` | Negative money (outstanding loans, overdue) |
| `--sl-warn` | `#b8770b` | Warnings, pending statuses, frozen collateral |

### Typography

Loaded once from Google Fonts CDN via a `<link>` in `base.html`, alongside the existing Bootstrap CDN link.

- **Headlines** (`h1`–`h4`, `.navbar-brand`): *Source Serif 4*, weight 600.
- **Body & UI**: *Inter*, weight 400/500/600.
- **Numbers**: Inter with `font-variant-numeric: tabular-nums` applied at the `body` level. No separate monospace font — tabular nums align decimals well enough for ISK amounts.

### Spacing and radius

Reuse Bootstrap defaults (`0.25rem` steps, `0.375rem` border radius). The design system overrides colors and fonts via CSS variables; Bootstrap's grid and spacing utilities stay untouched. Less rewriting, less to break.

### Component patterns

- **Nav:** white surface, navy brand and active-link underline, ink-colored inactive links.
- **Buttons:** navy primary (filled), navy outline secondary, green for money-positive verbs only (deposit, fund, pay off).
- **Cards:** white surface, 1px `--sl-border`, soft shadow (`0 1px 2px rgba(20,30,50,0.04)`).
- **Tables:** uppercase muted column headers on `#f4f4f0` band, thin row dividers, right-aligned `.num` cells using tabular nums, `.pos`/`.neg` color classes on amount cells.
- **Progress bars:** light track (`#eceae3`), navy fill. Leaderboard's `.progress-glow` retinted but otherwise preserved.
- **Alerts:** soft tinted backgrounds with matching borders, per category.

A live preview of these tokens and components exists at `docs/plans/2026-05-24-ui-redesign-preview.html`.

### Template change inventory

| File | Weight | Change |
|---|---|---|
| `static/style.css` | Heavy | Rebuild from 70 → ~350 lines: `:root` tokens, button/card/table/progress/alert overrides, nav styles. |
| `templates/base.html` | Medium | Drop `bg-dark text-light`, drop `navbar-dark bg-black`, add Google Fonts `<link>`, restyle nav structure, flip footer color. |
| `templates/dashboard.html` | Medium | Card class swap, button class swap, money color treatment. |
| `templates/order_detail.html` | Medium-heavy | Progress bar retint, time-to-ship card, deposit history table, action buttons. |
| `templates/loan_detail.html` | Medium | Same patterns as `order_detail.html`. |
| `templates/leaderboard.html` | Medium | Preserve `.progress-glow` (retinted), restyle table, preserve badge hover behavior. |
| `templates/catalog.html` | Light | Ship grid card restyle. |
| `templates/notifications.html` | Light | List item restyle. |
| `templates/index.html` | Light | Retheme only — Phase 2 rebuilds it. |
| `templates/error.html` | Trivial | One alert. |
| `templates/_macros.html` | Light | Verify `bernie_link` reads on light background. |
| `templates/admin/*.html` (9 files) | Light-medium each | Mechanical class swaps. Settings form, users/loans/unmatched tables get new treatment. |

Roughly 19 templates touched + 1 CSS rewrite. No JS changes beyond keeping the existing clipboard handler in `base.html`. No changes to `app.py`, `models.py`, `interest.py`, or `wallet.py`.

### Things to preserve

- **Leaderboard `.progress-glow` effect** (`static/style.css:29-37`) — central to the leaderboard's appeal. Preserved, retinted.
- **Completion badges** (`static/badges/*`) — already use transparency. PNG variants may need a quick visual check on the cream background; spot-fix with a subtle white halo in CSS if any are too dark.
- **Time-to-ship UI** on order detail (member + admin) — recently shipped, must survive the table restyle.
- **`bernie_link` macro** — currently styled for dark bg.
- **Clipboard `<script>` block** in `base.html`.
- **Bootstrap utilities** that aren't dark-specific (grid, spacing, display) — keep loaded.

### Risk

The leaderboard is the most-loved feature in the app. Phase 1 verification must include eyeballing the leaderboard on a running Flask instance, not just route-load checks.

## Phase 2 — Public product surface

### New routes

All accessible logged-out and logged-in. CTAs conditional on `session.get('character_id')`.

| Route | Template | CTA (logged-out) | CTA (logged-in) |
|---|---|---|---|
| `/savings` | `templates/products/savings.html` | Log in with EVE | Open a savings goal → dashboard |
| `/loans` | `templates/products/loans.html` | Log in with EVE | Speak to Bernie (in-game contact info) |
| `/credit-lines` | `templates/products/credit_lines.html` | Log in with EVE | Request a draw → dashboard |

Each product page is one template with sections: Hero · How it works · Current rate · Rules · CTA.

### Index (`/`) redesign

Currently a one-button login splash. Becomes:

- Hero (navy gradient, ship render slot, tagline, "Log in with EVE" CTA — or "Go to dashboard" if logged in).
- Product card grid: three cards linking to the product pages above.
- No stats / AUM / member-count blocks. YAGNI.

Logged-in users hitting `/` still see the landing, with the hero CTA changed to go to dashboard. No redirect.

### Current rate sourcing

New `models.get_current_rates()` returns a dict with `interest_rate`, `general_loan_rate`, and `interest_period` (read from `settings`). Rendered as "2.0% / month" etc.

### Rules content (Terms of Service replacement)

Each product page carries its own Rules section. This closes the deferred ToS to-do without a separate `/terms` page.

Initial content:

- **/savings rules:** boost-activity rule (boosts only apply to accounts with in-game activity in the previous month — implementation hook deferred); force-close rule (bank reserves the right to close an account by paying out balance + accrued interest — implementation hook deferred).
- **/loans rules:** to be written.
- **/credit-lines rules:** to be written (collateral-freeze behavior, blocked-actions while open).

User will add rules over time; sections are designed to be append-only.

### App.py changes

Four new GET routes (`/`, `/savings`, `/loans`, `/credit-lines`), all small — render template with rates context. Roughly 30 LOC total. The existing `/` route gets replaced; the others are net-new.

### Out of scope for Phase 2

- No `/bonds` page (deferred product).
- No stats / leaderboard preview on the landing.
- No images beyond ship renders via the existing `esi.py` image helpers.

## Phase 3 — Dashboard product cards (deferred)

Restyle the logged-in dashboard so a member's Savings / Loan / Credit Line render as cards matching the public product surface. Defer the decision to ship this until after Phase 2 lands — the dashboard may already feel cohesive enough at that point.

## Verification

- **Phase 1:** boot the Flask dev server, walk every member page and every admin page in a browser. Confirm the leaderboard's progress-glow still reads. Confirm bernie_link macro reads on light. No route should 500.
- **Phase 2:** boot the Flask dev server, visit `/`, `/savings`, `/loans`, `/credit-lines` both logged-out and logged-in. Confirm CTA behavior swap. Confirm rate values match `admin/settings`.

No test suite exists; manual browser verification is the standard for this project.

## Open follow-ups

- Boost-activity rule and force-close rule have implementation hooks beyond Phase 2 (ESI last-active signal, admin forced-close action). Those remain deferred features; Phase 2 only documents the rules.
- Phase 3 (dashboard product cards) deferred pending Phase 2 results.
