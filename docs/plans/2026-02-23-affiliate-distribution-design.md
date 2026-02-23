# Affiliate Earnings Distribution — Design

## Problem
Corp members use a referral code on an affiliate website, generating real-dollar kickbacks for the admin. We need a way to convert those dollars to ISK and distribute the ISK proportionally to all active savings accounts.

## Solution
Add a configurable USD-to-ISK ratio in admin settings, and a "Distribute Earnings" button on the admin dashboard that opens a Bootstrap modal. Admin enters a dollar amount, the system converts to ISK and distributes proportionally based on each member's deposited balance.

## Decisions
- **Distribution method:** Proportional to each order's `amount_deposited` relative to total deposits across all active goals
- **Deposit treatment:** Regular deposits — subject to 30-day interest lag, shows in deposit history with `'affiliate'` source
- **Ratio config:** Stored in the existing `settings` table, configured on the Settings page
- **UI:** Bootstrap modal triggered from admin dashboard button (Approach A)
- **Notifications:** Each member receives a notification when they get affiliate earnings
- **Fallback:** If all deposits are 0, distribute equally

## Data Flow
1. Admin configures `usd_to_isk_ratio` on Settings page (one-time or as needed)
2. Admin clicks "Distribute Earnings" on dashboard, enters dollar amount in modal
3. JS calculates and displays the ISK total in real-time as admin types
4. On submit, POST to `/admin/distribute-affiliate`
5. Backend computes `total_isk = dollars * ratio`
6. Fetches all active orders, sums `amount_deposited`
7. Each order gets `floor(total_isk * order_deposited / total_deposited)`
8. Remainder ISK (from rounding) goes to the largest account
9. Calls `record_deposit()` for each with source `'affiliate'`
10. Sends notification to each member
11. Flash summary: "Distributed X ISK across Y accounts"

## Edge Cases
- **No active orders:** Flash warning, no-op
- **All orders have 0 deposited:** Equal split fallback
- **Rounding:** Floor each share, remainder to largest account
- **Single active order:** Gets 100% of the ISK

## Files Modified
- `models.py` — new `get_active_orders_with_deposits()` helper (or reuse `get_active_orders()`)
- `app.py` — new `/admin/distribute-affiliate` route
- `templates/admin/settings.html` — new "Affiliate Settings" card with ratio input
- `templates/admin/dashboard.html` — new button + Bootstrap modal with dollar input and JS conversion preview
- `static/style.css` — minor styling if needed for the affiliate deposit badge
- `CONTEXT.md` — documentation
