# Sihcom Savings and Loans — Codebase Notes for Future Agents

A Flask app for an EVE Online corporation. Members save toward ship goals; the corp pays interest. As of 2026-05-17, also offers loans (admin-originated general loans + member-requested credit lines collateralized by savings).

## Stack

- Flask + Jinja2 (Python 3.13), no ORM — raw SQLite via `sqlite3.Row`
- EVE SSO via `preston` for auth (members no scope; admin has wallet read scope)
- Bootstrap 5 + CSS-variable design system (`--sl-*` tokens in `static/style.css`); bank-style light theme as of 2026-05-24. Inter + Source Serif 4 from Google Fonts (loaded in `base.html`)
- Deployed on Railway.app: single Gunicorn worker + persistent volume for SQLite (multi-worker breaks in-memory Flask sessions)
- `apscheduler` for two background jobs: wallet sync + interest accrual

## Files (entire app is in the project root)

- `app.py` — all Flask routes (member + admin), template filters, scheduler setup
- `models.py` — all data access functions; no ORM, just direct SQL via `database.get_db()`
- `database.py` — `SCHEMA_SQL` (full schema), `_try_alter()` helper for migrations, `DEFAULT_SETTINGS`, `init_db()`
- `interest.py` — savings accrual + loan accrual + frozen-collateral math; also `estimate_time_to_goal(order, balance_info)` for the order-detail timer
- `wallet.py` — ESI wallet sync; auto-matches deposits to active loans (loan-first) then to goals
- `esi.py` — EVE image and type-id helpers
- `config.py` — env-driven config (`Config` class)
- `templates/` — Jinja templates; admin templates under `templates/admin/`; public marketing pages under `templates/products/` (`savings.html`, `loans.html`, `credit_lines.html`)
- `static/style.css` — design tokens (`--sl-*`) + Bootstrap component overrides. Replaced the old dark-theme tweaks on 2026-05-24

## Schema migrations

SQLite, schema migrations via `_try_alter()` in `init_db()` — wraps `ALTER TABLE ADD COLUMN` and ignores duplicate-column errors. Always additive. Bring your own backfill if needed (see the `category` backfill near the bottom of `init_db`).

To add a column or table:
1. Add it to `SCHEMA_SQL` so fresh DBs get it
2. Add a `_try_alter(db, "ALTER TABLE ... ADD COLUMN ...")` line in `init_db()` so existing DBs get it
3. Backfill in `init_db()` if defaults aren't enough

## Conventions

- **One savings goal per user.** Enforced via `user_has_active_or_pending_order`.
- **One loan per user.** Enforced via `get_open_loan_for_user` (covers `pending_disbursement` + `active`).
- **No tests.** No test suite exists. Verify changes with the Flask test client manually (see commit `a06e102` for an example smoke-test script in the conversation history).
- **No new comments unless they explain *why*.** Existing code follows this.
- **Money amounts** are floats (ISK). Comparisons use a small tolerance (e.g. `<= 0.0001` for "paid in full"). Don't try to convert to integers — EVE wallet deltas have fractional ISK.
- **Interest period** comes from `settings.interest_period` (one of `daily`, `weekly`, `biweekly`, `monthly`), mapping in `interest.PERIOD_DAYS`. Same period drives savings accrual, credit-line accrual, and general loan accrual.
- **All deposits earn full interest immediately.** No age proration. The only reduction to the savings earning base is the frozen credit-line collateral (see `_apply_frozen_collateral`).
- **Wallet sync is the source of truth** for member-initiated deposits and loan payments. Auto-matches on sender's EVE character id. Outgoing ISK from the corp (e.g. loan disbursements) is NOT reconciled by the app — admin sends in-game and marks disbursed in the UI.
- **Admin is a single character** (`Config.ADMIN_CHARACTER_ID`). Auth is session-based; the admin's `refresh_token` is used for ESI wallet calls.
- **Admin display name** comes from the `inject_admin_link` context processor in `app.py` (`admin_character_name`, `admin_evewho_url`). When you want to render "Bernie May Doff" in a template, use `{% from '_macros.html' import bernie_link with context %}` and `{{ bernie_link() }}` — never hardcode the name. The `with context` is required because Jinja macros don't inherit context-processor values otherwise.
- **Design tokens.** Always reach for `var(--sl-navy)`, `var(--sl-green)`, `var(--sl-red)`, `var(--sl-muted)`, etc. before adding hex colors inline. See `static/style.css:1-20` for the full token list. The shim block at the bottom of that file remaps legacy Bootstrap utility classes (`text-white`, `text-light`, `bg-secondary`) onto the new tokens; new code shouldn't add those — use the tokens directly.
- **Public routes are public.** `/`, `/savings`, `/loans`, `/credit-lines` have no `@login_required` and render for logged-out + logged-in users with CTAs that swap on `session.get('character_id')`. The landing does NOT redirect logged-in users to the dashboard — that behavior was removed deliberately on 2026-05-24.
- **Per-product rates** come from `models.get_current_rates()` (savings rate, general loan rate, period). Use this on product pages, not per-call lookups via `get_setting`.

## Background jobs

In `app.py`, gated on `not app.debug`:

- **Wallet sync** every `WALLET_SYNC_INTERVAL` minutes (default 5)
- **Interest accrual** every `INTEREST_ACCRUAL_INTERVAL` hours (default 6) + a one-off catch-up 30 seconds after boot

Jobs run with `app.app_context()`. Single worker means single scheduler instance — don't add more workers without rethinking scheduling.

## Loans data model (added 2026-05-16)

Three tables:
- `loans` — `product_type` is `credit_line` or `general`; `status` cycles `pending_disbursement` → `active` → `paid_in_full`; `interest_paused` allows per-loan pause; `principal` doubles as the original draw amount for credit lines.
- `loan_payments` — every payment (wallet or manual). `source` is `wallet` or `manual`. `journal_id` links wallet-sourced payments back to `wallet_journal` for audit.
- `loan_interest_log` — one row per accrued period, mirrors `interest_log` shape.

Plus `users.interest_paused` (boolean; pauses both savings and loan accrual for that member) and `settings.general_loan_rate` (configurable, default `0.125`).

## How loan interest math works

- **General loan**: compounds on `current_balance` at `general_loan_rate` per period.
- **Credit line**: compounds on `current_balance` at `interest_rate` (savings rate) per period.
- **Savings with active credit line**: the savings effective balance is scaled by `max(0, savings - outstanding_loan) / savings`. Implementation: `_apply_frozen_collateral` in `interest.py`.
- **Paused user**: short-circuits both `accrue_interest_for_order` and `accrue_interest_for_loan` to a no-op.
- **Wallet payment to a borrower**: `wallet.py` calls `interest.accrue_interest_for_loan(loan_id)` *before* `record_loan_payment` so the borrower pays the up-to-date balance, not a stale one.

## Important plan files

- `docs/plans/2026-02-23-affiliate-distribution-impl.md` — Savings Boost (USD-to-ISK affiliate distribution)
- `docs/plans/2026-03-26-prorated-interest-design.md`, `2026-03-26-prorated-interest-impl.md` — **historical**, the per-deposit age weighting for savings (removed 2026-05-22; see Resolved gaps below)
- `docs/plans/2026-05-16-loans-design.md` — loans, credit lines, per-user pause, complete-paid-directly. Includes implementation-status notes and known gaps at the bottom.
- `docs/plans/2026-05-17-time-to-ship-design.md`, `2026-05-17-time-to-ship-impl.md` — time-to-ship estimator on order detail (member + admin views)
- `docs/plans/2026-05-17-bernie-info-link-design.md`, `2026-05-17-bernie-info-link-impl.md` — Bernie May Doff link to evewho + copy-name button
- `docs/plans/2026-05-24-ui-redesign-design.md`, `2026-05-24-ui-redesign-impl.md`, `2026-05-24-ui-redesign-preview.html` — bank-style reskin (Phase 1) + public product surface at `/savings`, `/loans`, `/credit-lines` (Phase 2). Phase 3 (dashboard product cards) deferred pending real-world use of Phase 2.

## Known gaps (next-agent worth-fixing)

- **No collateral release accounting.** The "frozen" portion of savings is computed dynamically each accrual run via `_apply_frozen_collateral`; there's no per-deposit flag. That's fine for the math but means there's no audit trail of *which* ISK is "frozen".
- **No manual loan payment beyond admin UI.** Members can't self-record a manual loan payment. That's deliberate — wallet sync is the canonical path — but worth confirming if user feedback diverges.

## Resolved gaps

- **2026-05-17 — Withdrawal/cancel/complete blocked when credit line open.** `request_withdrawal`, `admin_approve_withdrawal`, `admin_cancel_order`, and `admin_complete_paid_directly` all guard on `get_outstanding_credit_line_balance_for_user`. `record_deposit` also skips auto-completion when a credit line is outstanding (sends a `goal_funded_pending_loan` notification instead). Member and admin order-detail templates surface the conflict and disable the relevant buttons.
- **2026-05-17 — Missing badges on the leaderboard.** Orders created before the 2026-02-23 `type_id` wiring had NULL `type_id`, which the badge query filters out. `init_db` now backfills `type_id` from `ship_catalog` by exact `ship_name` match (same pattern as the existing category backfill). For orders with no catalog match, the admin order-detail page surfaces a "Refresh ship data" button that calls Fuzzwork via `admin_order_refresh_ship_data`.
- **2026-05-17 — Admin can cancel a pending credit-line draw.** `admin_cancel_pending_loan` route + `cancel_pending_loan` model function add `cancelled` as a new `loans.status` value (no schema migration — TEXT column with no CHECK constraint). Sets `closed_at` and leaves `disbursed_at` NULL. Borrower gets a `loan_request_rejected` notification and is immediately unblocked to re-request (since `get_open_loan_for_user` only matches `pending_disbursement` + `active`). UI: "Reject Draw" button on the admin loan detail page, alongside "Mark Disbursed". Uses a status-guarded UPDATE to avoid racing with `mark_loan_disbursed`.
- **2026-05-22 — 30-day deposit proration removed entirely.** Two user-reported bugs traced back to the age weighting: (1) time-to-ship estimates were wildly pessimistic because `effective_balance` was a small fraction of `savings_balance` for recent deposits, so the `growth_needed = 1 + (goal - total) / effective` math gave years instead of months. (2) After paying off a credit line and re-depositing, the new deposits looked stuck at near-zero accrual for ~30 days. Replaced `_get_effective_balance` with the raw `amount_deposited + interest_earned`; `_apply_frozen_collateral` still reduces the earning base when a credit line is open. The `effective_balance` key in `calculate_current_balance`'s return dict is preserved (templates still branch on it) and now means "savings minus frozen credit-line collateral". Historical plans `docs/plans/2026-03-26-prorated-interest-*.md` describe the now-removed model.
- **2026-05-24 — Bank-style reskin + public product surface.** Two-phase change. Phase 1 (`cf0c02e`): rewrote `static/style.css` as a `--sl-*` token system + Bootstrap overrides; stripped dark-theme classes from all 19 templates. Phase 2 (`b9397ff`): added `models.get_current_rates()`, four new GET routes (`/`, `/savings`, `/loans`, `/credit-lines`), three product page templates under `templates/products/`, and a new hero+grid landing in `index.html`. The per-product Rules sections fold in what would otherwise have been a separate `/terms` page (Terms-of-Service deferred feature is now partially resolved — the *page* isn't needed; the *implementation hooks* for boost-activity and force-close are still pending). Plan files: `docs/plans/2026-05-24-ui-redesign-*`. Phase 3 (dashboard product cards) explicitly deferred.

## Local dev

- `pip install -r requirements.txt`
- Set env vars: `EVE_CLIENT_ID`, `EVE_CLIENT_SECRET`, `EVE_CALLBACK_URL`, `ADMIN_CHARACTER_ID`. `FLASK_SECRET_KEY` recommended. `DATA_DIR` for db path.
- `python app.py` (uses Flask debug server; background jobs disabled in debug)

## Deferred features

The user has explicitly deferred these to future sessions:

- **Bonds product** (new product type — no plan yet).
- **Leaderboard enhancements** (the leaderboard is the most-loved feature, so polish has high payoff). Glow + badges survived the 2026-05-24 reskin; future polish would build on top.
- **Phase 3 of the UI redesign — dashboard product cards.** Restyle `templates/dashboard.html`'s "My Loan" and "My Savings Goals" sections to use the same card patterns as `templates/products/*.html`. Punted pending feedback on whether the dashboard already feels cohesive enough next to the public product surface.
- **Stock photography for the bank aesthetic.** Phase 2 landed text-only product pages and a text-only hero on `/`. The bank-website vibe would land harder with imagery — generic banking stock photos in the hero right-column (currently empty) and possibly one per product page. Candidate sources: Unsplash, Pexels, or Pixabay (all CC0-ish and EVE-corp-safe). Subject suggestions: glass-fronted skyscraper exteriors, blurred trading-floor motion, an ATM keypad close-up, hands signing paperwork — the cliché "stock bank" tropes. Drop them into `static/img/` and reference via `url_for('static', filename='img/...')`. Worth doing only if real-world use of Phase 2 confirms it still feels too austere; otherwise YAGNI.
- **Boost-activity ESI signal.** The `/savings` Rules section now states "Savings boosts only apply to accounts with in-game activity in the previous month" — but the app doesn't track last-active. Needs an ESI character-online or similar derived signal, plus a check in the affiliate-distribution flow.
- **Admin forced-close action.** The `/savings` Rules section now states "The bank reserves the right to close an account by paying out balance plus accrued interest" — but there's no admin button for this. `admin_complete_paid_directly` is the closest existing action but is semantically "member paid out for the ship in-game", not "bank forcibly closes the account". Probably a new route + button on admin order detail.
