# Prorated Interest Design

## Problem

The current interest system has a "double-gate" bug: deposits must be 30+ days old to be eligible (binary), AND the period clock must tick (30 days since last accrual). These two independent clocks mean deposits can be stuck earning nothing for up to 60 days.

## Solution

Replace the binary 30-day eligibility gate with **per-deposit proration**. Every deposit earns interest immediately, but weighted by its age:

- **30+ days old**: full rate (e.g., 10%)
- **< 30 days old**: prorated — `(age_in_days / 30) * rate`

A deposit made 15 days ago earns 50% of the rate. A deposit made yesterday earns ~3%. Previously accrued interest always earns the full rate.

## Implementation

### `interest.py`

Replace `_get_eligible_deposits()` with:

```python
def _get_effective_balance(db, order_id):
    row = db.execute("""
        SELECT COALESCE(SUM(
            amount * MIN(julianday('now') - julianday(deposit_date), 30) / 30.0
        ), 0) as total
        FROM deposits WHERE order_id = ?
    """, (order_id,)).fetchone()
    return float(row['total'])
```

Update `calculate_current_balance()` and `accrue_interest_for_order()` to use `_get_effective_balance()` instead of `_get_eligible_deposits()`. Rename `eligible_balance` → `effective_balance` in returned dicts.

### UI

- Update settings page "How Interest Works" to describe proration
- Update member/admin order detail to remove "30 days" cliff language
- Keep the `effective_balance` display so members understand their weighted earning power

### Interest rate

Keep configurable via admin settings. Default remains whatever the admin has set (currently 0.05). Admin should update to 0.10 for the desired 10% monthly rate.
