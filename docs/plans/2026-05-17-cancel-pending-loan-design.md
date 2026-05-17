# Cancel Pending Loan Draws — Design

**Date:** 2026-05-17
**Status:** Approved

## Motivation

Members occasionally request a credit-line draw with the wrong amount (e.g. Anemone221 requested 3B ISK when they meant 30B). Today there is no way to reject or delete such a request — admin can only `Mark disbursed`, and the borrower is blocked from submitting a corrected request because `get_open_loan_for_user` treats `pending_disbursement` as an open loan.

## Scope

In scope:
- Admin-initiated cancellation of loans in `pending_disbursement` status (which today are exclusively member-requested credit-line draws — admin-created general loans skip straight to `active`).

Out of scope:
- Cancelling `active` loans (no clawback math, no ISK reversal accounting).
- Member self-cancel (admin gatekeeper is sufficient; member pings in-game).
- Rejection reason / note field (admin tells the borrower in-game).
- A "rejected loans" admin view (audit lives in the DB).

## Schema

`loans.status` gains a new documented value: `cancelled`. No DDL change needed — `status` is a plain `TEXT` column with no `CHECK` constraint.

A cancelled loan has:
- `status = 'cancelled'`
- `closed_at = datetime('now')` (mirrors `paid_in_full` close pattern)
- `disbursed_at` remains `NULL` (the loan was never disbursed)

## Model layer (`models.py`)

New function:

```python
def cancel_pending_loan(loan_id):
    """Cancel a pending_disbursement loan. Returns rowcount.
    Guarded so a race with mark_loan_disbursed can't clobber an active loan."""
    db = database.get_db()
    cur = db.execute(
        "UPDATE loans SET status='cancelled', closed_at=datetime('now') "
        "WHERE id = ? AND status = 'pending_disbursement'",
        (loan_id,),
    )
    db.commit()
    return cur.rowcount
```

Existing queries are already compatible:
- `get_pending_loans()` filters `WHERE status='pending_disbursement'` — cancelled loans drop out automatically.
- `get_open_loan_for_user()` only checks `pending_disbursement` + `active` — cancellation immediately unblocks the borrower's one-loan-at-a-time guard, so they can re-request with the correct amount.

## Route (`app.py`)

New route, mirrors the shape of `admin_disburse_loan`:

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

## UI (`templates/admin/loan_detail.html`)

When `loan.status == 'pending_disbursement'`, render a "Reject draw" button next to the existing "Mark disbursed" button. The button is a `<form method="POST" action="...">` with a JS `confirm()` that quotes the amount and borrower name to prevent fat-finger:

```html
<form method="POST" action="{{ url_for('admin_cancel_pending_loan', loan_id=loan.id) }}"
      onsubmit="return confirm('Reject {{ '{:,.2f}'.format(loan.principal) }} ISK draw from {{ loan.character_name }}?');">
  <button type="submit" class="btn btn-outline-danger">Reject draw</button>
</form>
```

No changes to the admin loan list view — cancelled loans simply don't appear in the pending queue.

## Notification

A new `loan_request_rejected` notification type. Uses existing `create_notification` infrastructure; no schema change. Member sees it on their dashboard.

## Testing

No test suite exists. Verify manually via Flask test client:
1. Member creates a credit-line draw request → loan in `pending_disbursement`.
2. Admin POSTs to `/admin/loan/<id>/cancel` → loan transitions to `cancelled`, `closed_at` set.
3. Verify member can immediately create a new draw request (no "already has open loan" block).
4. Verify member has a `loan_request_rejected` notification.
5. Verify cancelled loan does NOT appear in `get_pending_loans()` results.
6. Verify cancel on an `active` loan is rejected with a flash message.

## Risks

- **Race with disbursement.** Mitigated by the `AND status='pending_disbursement'` guard in the UPDATE — at most one of `cancel` and `disburse` will affect rows. The route handler reads `rowcount` and flashes a "status changed before cancel could be applied" message if it lost the race.
- **Audit trail.** No `cancelled_by` column. Acceptable for a single-admin app; the soft delete + `closed_at` is enough trail for now.
