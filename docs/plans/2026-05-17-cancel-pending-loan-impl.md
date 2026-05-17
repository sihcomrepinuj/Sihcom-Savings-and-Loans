# Cancel Pending Loan Draws — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an admin-only action to cancel a member's pending credit-line draw request, so a mistaken amount can be rejected and the member can re-request.

**Architecture:** Soft-cancel via new `cancelled` value of the existing `loans.status` field. One new model function, one new POST route, one new template button, plus a borrower notification. No schema migration.

**Tech Stack:** Flask + Jinja2, raw `sqlite3` (no ORM), Bootstrap 5. Project has NO test suite — verification uses the Flask test client smoke-test pattern (see commit `a06e102` referenced in `CLAUDE.md`).

**Design doc:** [docs/plans/2026-05-17-cancel-pending-loan-design.md](2026-05-17-cancel-pending-loan-design.md)

**Commit strategy:** Per user preference (`feedback_commit_policy`), bundle all changes into a single commit at the end — do NOT commit between tasks. Wait for the user to ask before committing.

---

## Task 1: Add `cancel_pending_loan` model function

**Files:**
- Modify: `models.py` (add new function after `mark_loan_disbursed` at line ~594)

**Step 1: Add the function**

Insert this immediately after `mark_loan_disbursed`:

```python
def cancel_pending_loan(loan_id):
    """Cancel a pending_disbursement loan. Returns rowcount.

    Guarded with status check so a race with mark_loan_disbursed cannot
    cancel an already-active loan."""
    db = database.get_db()
    cur = db.execute(
        "UPDATE loans SET status = 'cancelled', closed_at = datetime('now') "
        "WHERE id = ? AND status = 'pending_disbursement'",
        (loan_id,)
    )
    db.commit()
    return cur.rowcount
```

**Step 2: Quick syntax check**

Run: `python -c "import models; print(models.cancel_pending_loan.__doc__)"`
Expected: prints the docstring with no import error.

---

## Task 2: Add `admin_cancel_pending_loan` route

**Files:**
- Modify: `app.py` (add new route after `admin_disburse_loan` at line ~1172)

**Step 1: Add the route**

Insert immediately after the `admin_disburse_loan` function:

```python
@app.route('/admin/loan/<int:loan_id>/cancel', methods=['POST'])
@admin_required
def admin_cancel_pending_loan(loan_id):
    loan = models.get_loan(loan_id)
    if not loan:
        abort(404)
    if loan['status'] != 'pending_disbursement':
        flash('Only pending draw requests can be cancelled.', 'warning')
        return redirect(url_for('admin_loan_detail', loan_id=loan_id))

    rowcount = models.cancel_pending_loan(loan_id)
    if rowcount == 0:
        flash('Loan status changed before cancel could be applied.', 'warning')
        return redirect(url_for('admin_loan_detail', loan_id=loan_id))

    models.create_notification(
        user_id=loan['user_id'],
        notification_type='loan_request_rejected',
        message=f'Your credit line draw request of {loan["principal"]:,.2f} ISK '
                f'was rejected. Submit a new request if needed.',
    )
    flash(f'Draw request #{loan_id} cancelled.', 'success')
    return redirect(url_for('admin_loans'))
```

**Step 2: Quick syntax check**

Run: `python -c "import app; print([r.rule for r in app.app.url_map.iter_rules() if 'cancel' in r.rule])"`
Expected: prints `['/admin/loan/<int:loan_id>/cancel']`.

---

## Task 3: Add "Reject draw" button to admin loan detail template

**Files:**
- Modify: `templates/admin/loan_detail.html` (extend the `pending_disbursement` block at lines 87-93)

**Step 1: Replace the existing pending-disbursement block**

Find this block at lines 87-93:

```jinja
{% if loan['status'] == 'pending_disbursement' %}
<form method="POST" action="{{ url_for('admin_disburse_loan', loan_id=loan['id']) }}" class="mb-3"
      onsubmit="return confirm('Confirm: ISK has been sent in-game to {{ owner['character_name'] }}?');">
    <button type="submit" class="btn btn-warning">Mark Disbursed</button>
    <small class="text-light ms-2">Confirm after sending ISK to the borrower in EVE.</small>
</form>
{% endif %}
```

Replace with:

```jinja
{% if loan['status'] == 'pending_disbursement' %}
<form method="POST" action="{{ url_for('admin_disburse_loan', loan_id=loan['id']) }}" class="mb-3"
      onsubmit="return confirm('Confirm: ISK has been sent in-game to {{ owner['character_name'] }}?');">
    <button type="submit" class="btn btn-warning">Mark Disbursed</button>
    <small class="text-light ms-2">Confirm after sending ISK to the borrower in EVE.</small>
</form>
<form method="POST" action="{{ url_for('admin_cancel_pending_loan', loan_id=loan['id']) }}" class="mb-3"
      onsubmit="return confirm('Reject {{ '{:,.2f}'.format(loan['principal']) }} ISK draw from {{ owner['character_name'] }}? The member will be notified and can re-request.');">
    <button type="submit" class="btn btn-outline-danger">Reject Draw</button>
    <small class="text-light ms-2">Use when the requested amount is wrong or the draw should not proceed.</small>
</form>
{% endif %}
```

**Step 2: Visual check (manual)**

Run: `python app.py` (Flask debug server)
Visit a pending loan detail page as admin. Confirm the "Reject Draw" button renders below "Mark Disbursed". Don't actually click yet — Task 4 is the end-to-end smoke test.

---

## Task 4: Flask test-client smoke test

**Files:**
- Create: `scripts/smoke_test_cancel_loan.py` (temporary, deleted after verification)

This follows the project convention (no test suite, use Flask test client for one-off smoke tests, then delete the script). Reference: commit `a06e102`.

**Step 1: Create the smoke-test script**

```python
"""Smoke test for admin loan cancellation.

Run from project root: python scripts/smoke_test_cancel_loan.py
Deletes the temp DB on exit; safe to run repeatedly.
"""
import os
import tempfile
import sys

# Use a temp DB so we don't touch the real one
tmp_dir = tempfile.mkdtemp()
os.environ['DATA_DIR'] = tmp_dir
os.environ['FLASK_SECRET_KEY'] = 'test'
os.environ['EVE_CLIENT_ID'] = 'test'
os.environ['EVE_CLIENT_SECRET'] = 'test'
os.environ['EVE_CALLBACK_URL'] = 'http://localhost/callback'
os.environ['ADMIN_CHARACTER_ID'] = '111'

import app as app_module  # noqa: E402
import models  # noqa: E402
import database  # noqa: E402

app = app_module.app
app.config['TESTING'] = True

def fail(msg):
    print(f'FAIL: {msg}')
    sys.exit(1)

with app.app_context():
    database.init_db()
    db = database.get_db()

    # Seed: one admin user, one borrower with savings
    db.execute("INSERT INTO users (id, character_id, character_name, refresh_token) "
               "VALUES (1, 111, 'Admin', 'tok')")
    db.execute("INSERT INTO users (id, character_id, character_name, refresh_token) "
               "VALUES (2, 222, 'Anemone221', 'tok')")
    # Borrower has a savings order so a credit line could collateralise (not strictly
    # needed for cancellation but mirrors real state)
    db.execute("INSERT INTO ship_orders (user_id, ship_name, goal_price, current_balance, status) "
               "VALUES (2, 'Ferox', 100000000, 50000000, 'active')")
    # Pending credit-line draw at the wrong amount
    db.execute("INSERT INTO loans (user_id, product_type, principal, current_balance, status) "
               "VALUES (2, 'credit_line', 3000000000, 3000000000, 'pending_disbursement')")
    db.commit()

    loan_id = db.execute("SELECT id FROM loans WHERE user_id = 2").fetchone()['id']

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['character_id'] = 111
        sess['character_name'] = 'Admin'
        sess['is_admin'] = True

    # Test 1: cancel pending draw → 302 redirect, status flips to cancelled
    resp = client.post(f'/admin/loan/{loan_id}/cancel', follow_redirects=False)
    if resp.status_code != 302:
        fail(f'expected 302 redirect, got {resp.status_code}')

    row = db.execute("SELECT status, closed_at, disbursed_at FROM loans WHERE id = ?",
                     (loan_id,)).fetchone()
    if row['status'] != 'cancelled':
        fail(f"expected status='cancelled', got {row['status']!r}")
    if row['closed_at'] is None:
        fail('expected closed_at to be set')
    if row['disbursed_at'] is not None:
        fail(f"expected disbursed_at to be NULL, got {row['disbursed_at']!r}")
    print('OK: pending draw cancelled, closed_at set, disbursed_at still NULL')

    # Test 2: borrower received a notification
    notif = db.execute("SELECT type, message FROM notifications WHERE user_id = 2 "
                       "ORDER BY id DESC LIMIT 1").fetchone()
    if notif is None or notif['type'] != 'loan_request_rejected':
        fail(f'expected loan_request_rejected notification, got {notif}')
    if '3,000,000,000.00' not in notif['message']:
        fail(f'expected amount in notification message, got: {notif["message"]!r}')
    print('OK: borrower notified with correct amount')

    # Test 3: borrower can immediately submit a new draw request
    open_loan = models.get_open_loan_for_user(2)
    if open_loan is not None:
        fail(f'expected no open loan after cancellation, got loan #{open_loan["id"]}')
    print('OK: borrower is unblocked (get_open_loan_for_user returns None)')

    # Test 4: cancelled loan does NOT appear in pending list
    pending = models.get_pending_disbursement_loans()
    if any(l['id'] == loan_id for l in pending):
        fail('cancelled loan should not appear in pending list')
    print('OK: cancelled loan excluded from pending queue')

    # Test 5: cancelling a non-pending loan is rejected with a flash, not a 500
    db.execute("INSERT INTO loans (user_id, product_type, principal, current_balance, status) "
               "VALUES (2, 'credit_line', 1000000000, 1000000000, 'active')")
    db.commit()
    active_loan_id = db.execute("SELECT id FROM loans WHERE status='active' LIMIT 1").fetchone()['id']

    resp = client.post(f'/admin/loan/{active_loan_id}/cancel', follow_redirects=False)
    if resp.status_code != 302:
        fail(f'expected 302 redirect on active-loan cancel attempt, got {resp.status_code}')
    row = db.execute("SELECT status FROM loans WHERE id = ?", (active_loan_id,)).fetchone()
    if row['status'] != 'active':
        fail(f"active loan should not have been cancelled; got status={row['status']!r}")
    print('OK: cancel on active loan is rejected, loan still active')

print('\nAll smoke tests passed.')
```

**Step 2: Run the smoke test**

Run: `python scripts/smoke_test_cancel_loan.py`
Expected output:
```
OK: pending draw cancelled, closed_at set, disbursed_at still NULL
OK: borrower notified with correct amount
OK: borrower is unblocked (get_open_loan_for_user returns None)
OK: cancelled loan excluded from pending queue
OK: cancel on active loan is rejected, loan still active

All smoke tests passed.
```

If any assertion fails, fix the code and re-run before proceeding.

**Step 3: Delete the smoke-test script**

Run: `Remove-Item scripts/smoke_test_cancel_loan.py`
Then check `Test-Path scripts` — if empty, delete the directory too: `Remove-Item scripts`.

The script is a one-shot verification artifact, not part of the codebase.

---

## Task 5: Update CLAUDE.md "Resolved gaps" section

**Files:**
- Modify: `CLAUDE.md` (extend `## Resolved gaps`)

**Step 1: Add a new bullet at the end of "Resolved gaps"**

Append to the `## Resolved gaps` section:

```markdown
- **2026-05-17 — Admin can cancel/reject a pending credit-line draw.** `admin_cancel_pending_loan` route + `cancel_pending_loan` model function add `cancelled` as a new `loans.status` value (no schema migration — TEXT column with no CHECK constraint). Sets `closed_at` and leaves `disbursed_at` NULL. Borrower gets a `loan_request_rejected` notification and is immediately unblocked to re-request (since `get_open_loan_for_user` only matches `pending_disbursement` + `active`). UI: "Reject Draw" button on the admin loan detail page, alongside "Mark Disbursed".
```

---

## Task 6: Wait for commit instruction

Do NOT commit. User policy is bundle-and-wait. When the user says "commit", create one commit covering all four modified files:
- `models.py`
- `app.py`
- `templates/admin/loan_detail.html`
- `CLAUDE.md`

Suggested commit message:
```
Add admin reject action for pending credit-line draws

Fixes the case where a member requests the wrong draw amount (e.g.
3B instead of 30B): admin can now reject the pending request from
the loan detail page. Soft-cancel via new 'cancelled' status; the
borrower is notified and immediately unblocked to re-request.
```

---

## Verification summary

After all tasks:
- `models.cancel_pending_loan` exists and uses a status-guarded UPDATE.
- `POST /admin/loan/<id>/cancel` route exists, admin-required, creates notification.
- Admin loan detail page shows "Reject Draw" alongside "Mark Disbursed" for pending loans only.
- Smoke test confirms: status flips, `closed_at` set, `disbursed_at` stays NULL, notification created, borrower unblocked, query hygiene, and active loans cannot be cancelled.
- Smoke test script is deleted.
- CLAUDE.md "Resolved gaps" reflects the new capability.
- No commit yet — waiting for user.
