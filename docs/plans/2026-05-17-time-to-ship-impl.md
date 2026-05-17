# Time-to-Ship Timer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show a member how long until their savings goal is fully funded by compound interest alone, with a concrete target date.

**Architecture:** Add a pure estimator `interest.estimate_time_to_goal(order)` that returns `{'state', 'days'}`. Wire it into the existing `order_detail` route. Render in the member-side template under the progress bar with a Jinja filter that formats float days into smart units (`~12 days`, `~3 months 12 days`, `~1 year 4 months`). Add the absolute target date in parentheses.

**Tech Stack:** Python 3.13, Flask, Jinja2, raw SQLite (per project convention). No test framework — use the existing smoke-script pattern (see prior commits `36a0f49`, `a06e102`).

**Design doc:** `docs/plans/2026-05-17-time-to-ship-design.md`

---

### Task 1: Add `estimate_time_to_goal` to `interest.py`

**Files:**
- Modify: `interest.py` (add new function near `calculate_pending_interest`)

**Step 1: Write the smoke test first**

Create `_smoke_time_to_goal.py`:

```python
"""Smoke test for interest.estimate_time_to_goal."""
import os, tempfile
os.environ.setdefault('EVE_CLIENT_ID', 'test')
os.environ.setdefault('EVE_CLIENT_SECRET', 'test')
os.environ.setdefault('EVE_CALLBACK_URL', 'http://localhost/callback')
os.environ.setdefault('ADMIN_CHARACTER_ID', '999')
os.environ.setdefault('FLASK_SECRET_KEY', 'test')
os.environ['DATA_DIR'] = tempfile.mkdtemp()

import sqlite3
from config import Config
import database, models, interest

def setup():
    database.init_db()
    db = sqlite3.connect(Config.DATABASE_PATH)
    db.execute("INSERT INTO users (id, character_id, character_name, refresh_token) VALUES (1, 1, 'Saver', 't')")
    db.execute("UPDATE settings SET value='0.05' WHERE key='interest_rate'")
    db.execute("UPDATE settings SET value='monthly' WHERE key='interest_period'")
    db.commit()
    db.close()
    return models.create_order(1, 'Nyx', 10_000_000_000, status='active')

def main():
    order_id = setup()
    import flask
    from app import app
    with app.app_context():
        # Status not active
        from database import get_db
        get_db().execute("UPDATE ship_orders SET status='pending_approval' WHERE id=?", (order_id,))
        get_db().commit()
        order = models.get_order(order_id)
        r = interest.estimate_time_to_goal(order)
        assert r['state'] == 'inactive', r
        print('[OK] non-active goal -> inactive')

        # Active but 0 balance
        get_db().execute("UPDATE ship_orders SET status='active' WHERE id=?", (order_id,))
        get_db().commit()
        order = models.get_order(order_id)
        r = interest.estimate_time_to_goal(order)
        assert r['state'] == 'frozen', r
        print('[OK] zero balance -> frozen (no earning base)')

        # Active with balance below goal
        models.record_deposit(order_id, 1_000_000_000, recorded_by_user_id=1)
        order = models.get_order(order_id)
        r = interest.estimate_time_to_goal(order)
        assert r['state'] == 'ok', r
        assert r['days'] is not None and r['days'] > 0, r
        print(f'[OK] active+below-goal -> ok, days={r["days"]:.1f}')

        # Funded
        models.record_deposit(order_id, 10_000_000_000, recorded_by_user_id=1)
        order = models.get_order(order_id)
        r = interest.estimate_time_to_goal(order)
        assert r['state'] == 'funded', r
        print('[OK] over-goal -> funded')

        # User paused
        get_db().execute("UPDATE ship_orders SET status='active' WHERE id=?", (order_id,))
        get_db().commit()
        models.set_user_interest_paused(1, True)
        order = models.get_order(order_id)
        r = interest.estimate_time_to_goal(order)
        assert r['state'] == 'paused', r
        print('[OK] paused user -> paused')

    print('\nAll states verified.')

if __name__ == '__main__':
    main()
```

**Step 2: Run to verify it fails**

Run: `python _smoke_time_to_goal.py`
Expected: `AttributeError: module 'interest' has no attribute 'estimate_time_to_goal'`

**Step 3: Implement `estimate_time_to_goal`**

In `interest.py`, after the existing balance/interest helpers:

```python
import math

def estimate_time_to_goal(order):
    """Estimate periods/days until compound interest alone funds the goal.

    Returns dict with:
      - state: 'ok' | 'funded' | 'paused' | 'frozen' | 'inactive'
      - days:  float days, or None when state != 'ok'
    """
    if order['status'] != 'active':
        return {'state': 'inactive', 'days': None}

    settings = models.get_interest_settings()
    period = settings['interest_period']
    rate = float(settings['interest_rate'])

    if models.is_user_interest_paused(order['user_id']) or rate <= 0:
        return {'state': 'paused', 'days': None}

    effective_balance = _get_effective_balance(order)
    goal = float(order['goal_price'])

    if effective_balance >= goal:
        return {'state': 'funded', 'days': None}
    if effective_balance <= 0:
        return {'state': 'frozen', 'days': None}

    period_days = PERIOD_DAYS[period]
    n_periods = math.log(goal / effective_balance) / math.log(1 + rate)
    return {'state': 'ok', 'days': n_periods * period_days}
```

**Step 4: Run test to verify all five states pass**

Run: `python _smoke_time_to_goal.py`
Expected: 5 `[OK]` lines, then `All states verified.`

**Step 5: Commit deferred — see Task 4.**

---

### Task 2: Add `format_days_smart` Jinja filter to `app.py`

**Files:**
- Modify: `app.py` near the existing `badge_url_filter` (`app.py:159`)

**Step 1: Implement the filter**

```python
@app.template_filter('format_days_smart')
def format_days_smart(days):
    """Convert float days into a human-readable estimate string."""
    if days is None:
        return ''
    days = max(0, int(round(days)))
    if days < 30:
        return f'~{days} day{"s" if days != 1 else ""}'
    if days < 365:
        months = days // 30
        rem = days - months * 30
        if rem == 0:
            return f'~{months} month{"s" if months != 1 else ""}'
        return f'~{months} month{"s" if months != 1 else ""} {rem} day{"s" if rem != 1 else ""}'
    years = days // 365
    rem_days = days - years * 365
    months = rem_days // 30
    if months == 0:
        return f'~{years} year{"s" if years != 1 else ""}'
    return f'~{years} year{"s" if years != 1 else ""} {months} month{"s" if months != 1 else ""}'
```

**Step 2: Smoke-check via Python REPL**

Run:
```python
python -c "
from app import format_days_smart
assert format_days_smart(0)   == '~0 days'
assert format_days_smart(1)   == '~1 day'
assert format_days_smart(12)  == '~12 days'
assert format_days_smart(30)  == '~1 month'
assert format_days_smart(102) == '~3 months 12 days'
assert format_days_smart(365) == '~1 year'
assert format_days_smart(490) == '~1 year 4 months'
assert format_days_smart(None) == ''
print('OK')
"
```

Expected: `OK`

---

### Task 3: Wire estimator + filter into `order_detail` view

**Files:**
- Modify: `app.py:order_detail` route (~line 379)
- Modify: `templates/order_detail.html` — place block under the progress bar

**Step 1: Pass `time_to_goal` to the member-side template**

In `app.py:order_detail`:

```python
time_to_goal = interest.estimate_time_to_goal(order)
if time_to_goal.get('days') is not None:
    from datetime import date, timedelta
    time_to_goal['target_date'] = (date.today() + timedelta(days=time_to_goal['days'])).strftime('%b %d, %Y')

return render_template(
    'order_detail.html',
    order=order,
    balance=balance_info,
    deposits=deposits,
    interest_logs=interest_logs,
    owner=user,
    outstanding_credit_line=outstanding_credit_line,
    time_to_goal=time_to_goal,
)
```

**Step 2: Render in `templates/order_detail.html`** — find the progress bar inside the order summary card; insert this block immediately after it:

```jinja
{% if time_to_goal %}
<div class="mt-3 small">
    {% if time_to_goal['state'] == 'ok' %}
    <div class="text-info">
        ⏱ Time to {{ order['ship_name'] }}:
        <strong>{{ time_to_goal['days'] | format_days_smart }}</strong>
        ({{ time_to_goal['target_date'] }})
    </div>
    <div class="text-secondary">
        Estimated, assuming no further deposits and current interest rate.
    </div>
    {% elif time_to_goal['state'] == 'frozen' %}
    <div class="text-warning">Pay off your credit line to start earning interest on this savings.</div>
    {% elif time_to_goal['state'] == 'paused' %}
    <div class="text-secondary">Interest paused.</div>
    {% endif %}
</div>
{% endif %}
```

**Step 3: Visual check**

Run `python app.py`, log in as the test user, visit `/order/<id>`. Confirm:
- Block renders under progress bar with the smart-unit string + target date in parentheses
- Pausing interest changes the block to "Interest paused"
- Completing the goal hides the block

---

### Task 4: Cleanup and commit

**Step 1: Delete `_smoke_time_to_goal.py`** (it served its purpose, mirroring prior commits)

**Step 2: Stage and commit**

```bash
git add interest.py app.py templates/order_detail.html docs/plans/2026-05-17-time-to-ship-design.md docs/plans/2026-05-17-time-to-ship-impl.md
git commit -m "Add time-to-ship estimate on member order detail"
```

**Step 3: Push** when user confirms.

---

## Verification checklist

- [ ] `estimate_time_to_goal` returns 5 documented states
- [ ] `format_days_smart` handles all unit thresholds + None
- [ ] Order detail page shows the line and the date in parens
- [ ] Frozen / paused / inactive states render correctly
- [ ] Funded goal hides the line entirely
