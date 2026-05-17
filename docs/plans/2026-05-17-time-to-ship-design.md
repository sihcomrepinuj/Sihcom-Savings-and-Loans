# Time-to-Ship Timer — Design

**Date:** 2026-05-17

## Goal

On a member's savings goal detail page, show how long until the goal would be fully funded by compound interest alone, assuming no further deposits.

## User-facing display

Placed inside the order summary card on `templates/order_detail.html`, immediately below the progress bar. Two-line block:

```
⏱ Time to Nyx: ~3 months 12 days (Aug 29, 2026)
Estimated, assuming no further deposits and current interest rate.
```

- Ship name interpolated into the label.
- Magnitude in smart units: `~12 days` / `~3 months 12 days` / `~1 year 4 months`.
- Target date in parentheses, format `Mon DD, YYYY`.
- "~" signals approximation; caveat line clarifies the assumption.

## Math

Given:
- `B` = current effective balance (already accounts for prorated under-30-day deposits and frozen collateral from any open credit line — pulled from existing `interest._get_effective_balance` path)
- `G` = `order['goal_price']`
- `r` = per-period rate (`settings.interest_rate` for savings, mapped from period via `interest.PERIOD_DAYS`)
- `P` = period length in days (from `interest.PERIOD_DAYS[period]`)

Solve:
```
n_periods = log(G / B) / log(1 + r)
days_to_goal = n_periods * P
target_date = today + days_to_goal
```

The estimate is slightly pessimistic in practice because the under-30-day proration baked into `B` will wash out as deposits age past 30 days, but for display purposes that's fine.

## Edge cases

| Condition | Behavior |
|---|---|
| `order['status']` != `active` | Hide block |
| `B >= G` (already funded) | Hide block |
| `B <= 0` (frozen collateral wipes out earning base) | Show "Pay off credit line to start earning interest" |
| User interest paused, OR `interest_rate <= 0` | Show "Interest paused" |

## Implementation surface

1. **`interest.py`** — add `estimate_time_to_goal(order)` returning a dict like `{'days': float | None, 'state': 'ok' | 'funded' | 'paused' | 'frozen' | 'inactive'}`. Returns None days unless `state == 'ok'`. Uses the same effective-balance + period-rate path as `accrue_interest_for_order` so the math stays consistent.
2. **`app.py`** — call `estimate_time_to_goal` in `order_detail` route, pass to template as `time_to_goal`.
3. **`templates/order_detail.html`** — render the block under the progress bar. Switches on `time_to_goal['state']`.
4. **Template filter** — `format_days_smart` filter converts a float `days` into the smart-unit string (`~12 days` / `~3 months 12 days` / `~1 year 4 months`).
5. **Date computation** — use `datetime.date.today() + timedelta(days=days_to_goal)`, format with `strftime('%b %d, %Y')`.

## Scope decisions

- **Member view only.** Admin order detail unchanged.
- **No JS countdown.** Computed at page load. Day-granularity is plenty.
- **No precomputation/caching.** The math is O(1); fine to recompute per request.
- **Don't account for compounding period boundaries.** We treat interest as continuously accruing for display purposes (matches how users intuit it). Actual accrual is periodic, so the timer rounds at most one period.

## Verification

Smoke test covering: ok / funded / frozen / paused / inactive states.
