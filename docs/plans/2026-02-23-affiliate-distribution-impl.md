# Affiliate Earnings Distribution — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow the admin to enter a dollar amount from affiliate kickbacks, convert it to ISK using a configurable ratio, and distribute ISK proportionally to all active savings accounts.

**Architecture:** New setting `usd_to_isk_ratio` in existing settings table. New route `/admin/distribute-affiliate` handles proportional distribution via existing `record_deposit()`. Bootstrap modal on admin dashboard for the UI.

**Tech Stack:** Flask, SQLite, Jinja2, Bootstrap 5, vanilla JS

---

### Task 1: Add `usd_to_isk_ratio` default setting and model helper

**Files:**
- Modify: `database.py:109-112` (DEFAULT_SETTINGS dict)
- Modify: `models.py:400-404` (after `get_interest_settings()`)

**Step 1: Add default setting to `database.py`**

In `database.py`, add `'usd_to_isk_ratio': '1000000000'` to the `DEFAULT_SETTINGS` dict at line 109:

```python
DEFAULT_SETTINGS = {
    'interest_rate': '0.05',
    'interest_period': 'monthly',
    'usd_to_isk_ratio': '1000000000',
}
```

This seeds the setting for new and existing databases on next `init_db()` call (uses `INSERT OR IGNORE`).

**Step 2: Add `get_affiliate_settings()` to `models.py`**

After the existing `get_interest_settings()` function (around line 404), add:

```python
def get_affiliate_settings():
    return {
        'usd_to_isk_ratio': float(get_setting('usd_to_isk_ratio') or '1000000000'),
    }
```

**Step 3: Commit**

```bash
git add database.py models.py
git commit -m "Add usd_to_isk_ratio default setting and model helper"
```

---

### Task 2: Add affiliate ratio config to Settings page

**Files:**
- Modify: `templates/admin/settings.html:56-75` (after the "How Interest Works" card)
- Modify: `app.py:849-868` (admin_settings route)

**Step 1: Update the settings route to handle affiliate settings**

In `app.py`, in the `admin_settings()` route handler, add handling for the new field. In the POST block (around line 852), after the existing interest rate/period validation and save (around line 863), add:

```python
        # Affiliate settings
        ratio = request.form.get('usd_to_isk_ratio', type=float)
        if ratio is not None:
            if ratio <= 0:
                flash('USD to ISK ratio must be greater than 0.', 'danger')
            else:
                models.set_setting('usd_to_isk_ratio', str(ratio))
```

In the GET block (around line 867), pass affiliate settings alongside interest settings:

```python
    settings = models.get_interest_settings()
    affiliate = models.get_affiliate_settings()
    return render_template('admin/settings.html', settings=settings, affiliate=affiliate)
```

**Step 2: Add affiliate settings card to the Settings template**

In `templates/admin/settings.html`, after the closing `</div>` of the "How Interest Works" card (line 74), add a new card:

```html
        <div class="card bg-secondary bg-opacity-25 border-secondary mt-4">
            <div class="card-header">
                <h4 class="mb-0">Affiliate Settings</h4>
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label for="usd_to_isk_ratio" class="form-label">USD to ISK Ratio</label>
                        <div class="input-group">
                            <span class="input-group-text bg-dark text-light border-secondary">$1 =</span>
                            <input type="number" class="form-control bg-dark text-light border-secondary"
                                   id="usd_to_isk_ratio" name="usd_to_isk_ratio"
                                   step="1" min="1"
                                   value="{{ affiliate['usd_to_isk_ratio'] | int }}" required>
                            <span class="input-group-text bg-dark text-light border-secondary">ISK</span>
                        </div>
                        <div class="form-text text-secondary">
                            How many ISK per $1 USD of affiliate earnings. E.g., 1,000,000,000 = 1B ISK per dollar.
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success w-100">Save Affiliate Settings</button>
                </form>
            </div>
        </div>
```

**Step 3: Commit**

```bash
git add app.py templates/admin/settings.html
git commit -m "Add affiliate USD-to-ISK ratio config on Settings page"
```

---

### Task 3: Add distribution route in `app.py`

**Files:**
- Modify: `app.py` (add new route after admin_settings, around line 869)
- Read: `models.py` (uses `get_active_orders()`, `record_deposit()`, `create_notification()`, `get_affiliate_settings()`, `get_admin_user()`)

**Step 1: Add the `/admin/distribute-affiliate` route**

Add this route after the `admin_settings` route in `app.py`:

```python
@app.route('/admin/distribute-affiliate', methods=['POST'])
@admin_required
def admin_distribute_affiliate():
    dollars = request.form.get('dollars', type=float)
    if not dollars or dollars <= 0:
        flash('Please enter a valid dollar amount.', 'danger')
        return redirect(url_for('admin_dashboard'))

    affiliate = models.get_affiliate_settings()
    ratio = affiliate['usd_to_isk_ratio']
    total_isk = dollars * ratio

    # Get all active orders
    active_orders = models.get_active_orders()
    if not active_orders:
        flash('No active savings goals to distribute to.', 'warning')
        return redirect(url_for('admin_dashboard'))

    total_deposited = sum(o['amount_deposited'] for o in active_orders)
    admin_user = models.get_admin_user()
    admin_id = admin_user['id'] if admin_user else None

    import math

    if total_deposited <= 0:
        # Fallback: equal split
        per_order = math.floor(total_isk / len(active_orders))
        shares = [(o, per_order) for o in active_orders]
        remainder = total_isk - (per_order * len(active_orders))
    else:
        # Proportional distribution
        shares = []
        distributed = 0
        for o in active_orders:
            share = math.floor(total_isk * o['amount_deposited'] / total_deposited)
            shares.append((o, share))
            distributed += share
        remainder = total_isk - distributed

    # Give remainder to the largest account (last in sorted order by deposit)
    if remainder > 0 and shares:
        largest_idx = max(range(len(shares)), key=lambda i: shares[i][0]['amount_deposited'])
        order, share = shares[largest_idx]
        shares[largest_idx] = (order, share + remainder)

    # Record deposits and send notifications
    count = 0
    for order, share in shares:
        if share <= 0:
            continue
        models.record_deposit(
            order_id=order['id'],
            amount=share,
            recorded_by_user_id=admin_id,
            note=f'Affiliate distribution: ${dollars:.2f}',
            source='affiliate',
        )
        models.create_notification(
            user_id=order['user_id'],
            notification_type='deposit_recorded',
            message=f'{share:,.2f} ISK affiliate bonus deposited to your {order["ship_name"]} goal.',
            order_id=order['id'],
        )
        count += 1

    flash(
        f'Distributed {total_isk:,.0f} ISK (${dollars:.2f}) across {count} account(s).',
        'success',
    )
    return redirect(url_for('admin_dashboard'))
```

**Step 2: Commit**

```bash
git add app.py
git commit -m "Add /admin/distribute-affiliate route for proportional ISK distribution"
```

---

### Task 4: Add modal and button to admin dashboard

**Files:**
- Modify: `templates/admin/dashboard.html:6-16` (header button row)
- Modify: `templates/admin/dashboard.html` (add modal before closing `{% endblock %}`)

**Step 1: Add the "Distribute Earnings" button**

In `templates/admin/dashboard.html`, in the button row at the top (around line 8-16), add a new button before the Sync Wallet form:

```html
        <button type="button" class="btn btn-outline-success btn-sm me-2"
                data-bs-toggle="modal" data-bs-target="#distributeModal">
            Distribute Earnings
        </button>
```

**Step 2: Add the Bootstrap modal**

Before the closing `{% endblock %}` tag (before the `<script>` block at line 240), add:

```html
<!-- Distribute Affiliate Earnings Modal -->
<div class="modal fade" id="distributeModal" tabindex="-1" aria-labelledby="distributeModalLabel" aria-hidden="true">
    <div class="modal-dialog">
        <div class="modal-content bg-dark border-secondary">
            <div class="modal-header border-secondary">
                <h5 class="modal-title text-white" id="distributeModalLabel">Distribute Affiliate Earnings</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <form method="POST" action="{{ url_for('admin_distribute_affiliate') }}">
                <div class="modal-body">
                    <div class="mb-3">
                        <label for="dollars" class="form-label">Dollar Amount</label>
                        <div class="input-group">
                            <span class="input-group-text bg-dark text-light border-secondary">$</span>
                            <input type="number" class="form-control bg-dark text-light border-secondary"
                                   id="dollars" name="dollars"
                                   step="0.01" min="0.01" required
                                   oninput="updateIskPreview()">
                        </div>
                    </div>
                    <div id="iskPreview" class="text-secondary small"></div>
                </div>
                <div class="modal-footer border-secondary">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn btn-success"
                            onclick="return confirm('Distribute affiliate earnings to all active accounts?');">
                        Distribute
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>
```

**Step 3: Add the JS preview function**

In the existing `<script>` block at the bottom of the template (around line 240), add the `updateIskPreview` function alongside the existing `toggleClosedOrders`:

```javascript
var iskRatio = {{ affiliate['usd_to_isk_ratio'] | int }};
function updateIskPreview() {
    var dollars = parseFloat(document.getElementById('dollars').value) || 0;
    var totalIsk = dollars * iskRatio;
    var preview = document.getElementById('iskPreview');
    if (dollars > 0) {
        preview.textContent = 'Total ISK to distribute: ' + totalIsk.toLocaleString(undefined, {maximumFractionDigits: 0}) + ' ISK';
    } else {
        preview.textContent = '';
    }
}
```

**Step 4: Pass affiliate settings to the dashboard template**

In `app.py`, in the `admin_dashboard()` route handler, add:

```python
    affiliate = models.get_affiliate_settings()
```

And include it in the `render_template` call:

```python
    return render_template(
        'admin/dashboard.html',
        orders=all_orders,
        withdrawal_requests=withdrawal_requests,
        pending_approvals=pending_approvals,
        balances=balances,
        settings=settings,
        stats=stats,
        affiliate=affiliate,
    )
```

**Step 5: Commit**

```bash
git add templates/admin/dashboard.html app.py
git commit -m "Add Distribute Earnings modal to admin dashboard"
```

---

### Task 5: Add 'affiliate' source badge to deposit history

**Files:**
- Modify: `templates/admin/order_detail.html:111-116` (source badge display)
- Modify: `templates/order_detail.html:137-142` (member source badge display)

**Step 1: Update admin order detail source badge**

In `templates/admin/order_detail.html`, replace the source badge block (lines 112-116):

```html
                                    {% if dep['source'] == 'wallet' %}
                                    <span class="badge bg-primary">Wallet</span>
                                    {% elif dep['source'] == 'affiliate' %}
                                    <span class="badge bg-success">Affiliate</span>
                                    {% else %}
                                    <span class="badge bg-secondary">Manual</span>
                                    {% endif %}
```

**Step 2: Update member order detail source badge**

In `templates/order_detail.html`, replace the source badge block (lines 138-142):

```html
                                    {% if dep['source'] == 'wallet' %}
                                    <span class="badge bg-primary">Wallet</span>
                                    {% elif dep['source'] == 'affiliate' %}
                                    <span class="badge bg-success">Affiliate</span>
                                    {% else %}
                                    <span class="badge bg-secondary">Manual</span>
                                    {% endif %}
```

**Step 3: Commit**

```bash
git add templates/admin/order_detail.html templates/order_detail.html
git commit -m "Add affiliate source badge to deposit history"
```

---

### Task 6: Update CONTEXT.md

**Files:**
- Modify: `CONTEXT.md`

**Step 1: Update documentation**

Add these items to CONTEXT.md:
- In "Key Business Rules" section: add bullet about affiliate distribution (admin enters dollar amount, converts via configurable ratio, distributes proportionally to active accounts as regular deposits)
- In `models.py` description: add `get_affiliate_settings()`
- In `admin/dashboard.html` description: mention Distribute Earnings modal
- In `admin/settings.html` description: mention affiliate ratio config
- In "Database Schema" section 7 (settings): note `usd_to_isk_ratio` key

**Step 2: Commit**

```bash
git add CONTEXT.md
git commit -m "Document affiliate earnings distribution in CONTEXT.md"
```
