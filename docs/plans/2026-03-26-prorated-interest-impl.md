# Prorated Interest Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the binary 30-day interest eligibility gate with per-deposit proration so all deposits earn interest immediately (weighted by age).

**Architecture:** Single function replacement in `interest.py` — swap `_get_eligible_deposits()` (binary 30-day cutoff) with `_get_effective_balance()` (weighted sum using `min(age/30, 1.0)`). Update two consumers and three templates.

**Tech Stack:** Python, SQLite (`julianday()`), Jinja2

---

### Task 1: Replace `_get_eligible_deposits()` with `_get_effective_balance()`

**Files:**
- Modify: `interest.py:15-22`

**Step 1: Replace the function**

Replace `_get_eligible_deposits` (lines 15-22) with:

```python
def _get_effective_balance(db, order_id):
    """Compute weighted deposit balance for interest: deposits aged 30+ days
    count fully, newer deposits are prorated by age/30."""
    row = db.execute("""
        SELECT COALESCE(SUM(
            amount * MIN(julianday('now') - julianday(deposit_date), 30) / 30.0
        ), 0) as total
        FROM deposits WHERE order_id = ?
    """, (order_id,)).fetchone()
    return float(row['total'])
```

**Step 2: Commit**

```bash
git add interest.py
git commit -m "Replace binary deposit eligibility with prorated weighting"
```

---

### Task 2: Update `calculate_current_balance()` to use effective balance

**Files:**
- Modify: `interest.py:25-91` (the `calculate_current_balance` function)

**Step 1: Update the function**

Replace these lines in `calculate_current_balance()`:

```python
    # Only deposits older than 30 days earn interest
    eligible_deposits = _get_eligible_deposits(db, order['id'])
    eligible_balance = eligible_deposits + accrued_interest
```

With:

```python
    # All deposits earn interest, weighted by age (prorated under 30 days)
    effective_deposits = _get_effective_balance(db, order['id'])
    effective_balance = effective_deposits + accrued_interest
```

Replace `eligible_balance` → `effective_balance` in the rest of the function (the `temp_balance` assignment and the return dict key).

Update the docstring to remove "30 days" language:

```python
    """Calculate the current savings balance including pending (un-accrued) interest.

    Interest accrues on the 'effective balance': each deposit is weighted by
    min(age_in_days / 30, 1.0), so newer deposits earn prorated interest.
    Previously accrued interest always earns at the full rate.

    Returns a dict with:
      - savings_balance: all deposits + accrued interest
      - effective_balance: age-weighted deposits + accrued interest (earns interest)
      - pending_interest: estimated interest since last accrual (not yet recorded)
      - total_balance: savings_balance + pending_interest
      - progress: percentage toward goal_price
      - remaining: ISK still needed to reach goal
      - periods_due: number of full periods since last accrual
    """
```

**Step 2: Commit**

```bash
git add interest.py
git commit -m "Update calculate_current_balance to use prorated effective balance"
```

---

### Task 3: Update `accrue_interest_for_order()` to use effective balance

**Files:**
- Modify: `interest.py:94-196` (the `accrue_interest_for_order` function)

**Step 1: Update the function**

Replace:

```python
    # Only deposits older than 30 days earn interest
    eligible_deposits = _get_eligible_deposits(db, order_id)
    eligible_balance = eligible_deposits + order['interest_earned']

    if eligible_balance <= 0:
        logger.info('Order %s (%s): eligible_balance=0 (eligible_deposits=%.2f, interest_earned=%.2f)',
                     order_id, order['ship_name'], eligible_deposits, order['interest_earned'])
        return {'periods_accrued': 0, 'interest_added': 0, 'new_balance': 0}
```

With:

```python
    # All deposits earn interest, weighted by age (prorated under 30 days)
    effective_deposits = _get_effective_balance(db, order_id)
    effective_balance = effective_deposits + order['interest_earned']

    if effective_balance <= 0:
        logger.info('Order %s (%s): effective_balance=0 (effective_deposits=%.2f, interest_earned=%.2f)',
                     order_id, order['ship_name'], effective_deposits, order['interest_earned'])
        return {'periods_accrued': 0, 'interest_added': 0, 'new_balance': 0}
```

Update the log line and remaining references from `eligible` → `effective`:

```python
    logger.info('Order %s (%s): effective=%.2f, last_accrual=%s, days_elapsed=%d, '
                'period=%s(%dd), full_periods=%d',
                order_id, order['ship_name'], effective_balance,
                last_accrual.isoformat(), days_elapsed, period, period_days, full_periods)

    if full_periods == 0:
        return {'periods_accrued': 0, 'interest_added': 0, 'new_balance': effective_balance}

    total_new_interest = 0.0
    balance = effective_balance
```

Update the docstring:

```python
    """Record interest accrual for all due periods on a single order.

    Interest accrues on the effective balance: each deposit is weighted by
    min(age_in_days / 30, 1.0), plus all previously accrued interest at full
    rate. Returns a dict with results or None if order is not active.
    """
```

**Step 2: Commit**

```bash
git add interest.py
git commit -m "Update accrue_interest_for_order to use prorated effective balance"
```

---

### Task 4: Update member-facing order detail template

**Files:**
- Modify: `templates/order_detail.html:58-61`

**Step 1: Replace the eligible balance display**

Replace:

```html
                {% if balance['eligible_balance'] is defined and balance['eligible_balance'] < balance['savings_balance'] %}
                <div class="mt-2">
                    <small class="text-light">Earning interest on <strong class="text-white">{{ balance['eligible_balance'] | isk }}</strong>
                    &mdash; new deposits earn interest after 30 days.</small>
```

With:

```html
                {% if balance['effective_balance'] is defined and balance['effective_balance'] < balance['savings_balance'] %}
                <div class="mt-2">
                    <small class="text-light">Effective earning balance: <strong class="text-white">{{ balance['effective_balance'] | isk }}</strong>
                    &mdash; recent deposits earn prorated interest.</small>
```

**Step 2: Commit**

```bash
git add templates/order_detail.html
git commit -m "Update member order detail to show prorated interest info"
```

---

### Task 5: Update member dashboard template

**Files:**
- Modify: `templates/dashboard.html:63-64`

**Step 1: Replace the 30-day message**

Replace:

```html
                {% if bal['eligible_balance'] is defined and bal['eligible_balance'] < bal['savings_balance'] %}
                <small class="text-secondary">New deposits earn interest after 30 days</small>
```

With:

```html
                {% if bal['effective_balance'] is defined and bal['effective_balance'] < bal['savings_balance'] %}
                <small class="text-secondary">Recent deposits earn prorated interest</small>
```

**Step 2: Commit**

```bash
git add templates/dashboard.html
git commit -m "Update dashboard to show prorated interest message"
```

---

### Task 6: Update admin settings "How Interest Works" card

**Files:**
- Modify: `templates/admin/settings.html:57-74`

**Step 1: Replace the explanation card**

Replace the entire "How Interest Works" card body (lines 61-72) with:

```html
                <p>Interest compounds on each member's <strong>effective balance</strong> every period.</p>
                <p>
                    <strong>Proration:</strong> Deposits less than 30 days old earn interest at a reduced rate
                    proportional to their age (e.g., a 15-day-old deposit earns at 50% of the rate).
                    Deposits 30+ days old and all previously earned interest earn at the full rate.
                </p>
                <p class="mb-0">
                    <strong>Example:</strong> At 10% monthly, a member deposits 1,000,000,000 ISK.
                    After 15 days, the effective balance is ~500,000,000 ISK (50% proration),
                    earning ~50,000,000 ISK. Once the deposit is 30+ days old, the full 1B ISK
                    earns 100,000,000 ISK per period.
                </p>
```

**Step 2: Commit**

```bash
git add templates/admin/settings.html
git commit -m "Update settings page interest explanation for proration model"
```

---

### Task 7: Final commit and push

**Step 1: Push to deploy**

```bash
git push
```

**Step 2: Verify on Railway**

After deploy, check Railway logs for the next scheduled interest accrual run. The diagnostic logging should now show `effective=` values that include all deposits (prorated), not just 30-day-old ones.

---

## Verification

1. **Railway logs**: After deploy, the startup catch-up accrual runs within 30 seconds. Logs should show non-zero `effective` balances for orders that previously showed `eligible_balance=0`.
2. **Member dashboard**: The "30 days" message should now say "Recent deposits earn prorated interest".
3. **Admin settings**: The "How Interest Works" card should describe the proration model.
4. **Admin should set rate to 0.10** in Settings for the desired 10% monthly rate.
