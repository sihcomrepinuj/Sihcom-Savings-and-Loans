from datetime import datetime, timedelta
import database
import models

PERIOD_DAYS = {
    'weekly': 7,
    'biweekly': 14,
    'monthly': 30,
}


def calculate_current_balance(order):
    """Calculate the current savings balance including pending (un-accrued) interest.

    Returns a dict with:
      - savings_balance: deposits + accrued interest
      - pending_interest: estimated interest since last accrual (not yet recorded)
      - total_balance: savings_balance + pending_interest
      - progress: percentage toward goal_price
      - remaining: ISK still needed to reach goal
      - periods_due: number of full periods since last accrual
    """
    savings_balance = order['amount_deposited'] + order['interest_earned']

    settings = models.get_interest_settings()
    rate = settings['interest_rate']
    period = settings['interest_period']
    period_days = PERIOD_DAYS.get(period, 30)

    # Find the last accrual date
    logs = database.get_db().execute(
        'SELECT accrued_at FROM interest_log WHERE order_id = ? ORDER BY accrued_at DESC LIMIT 1',
        (order['id'],)
    ).fetchone()

    if logs:
        last_accrual = datetime.fromisoformat(logs['accrued_at'])
    else:
        last_accrual = datetime.fromisoformat(order['created_at'])

    now = datetime.utcnow()
    days_elapsed = (now - last_accrual).days
    full_periods = days_elapsed // period_days

    # Compound interest for each un-recorded period
    pending_interest = 0.0
    temp_balance = savings_balance
    for _ in range(full_periods):
        period_interest = temp_balance * rate
        pending_interest += period_interest
        temp_balance += period_interest

    total_balance = savings_balance + pending_interest
    goal = order['goal_price']
    progress = (total_balance / goal * 100) if goal > 0 else 0
    remaining = max(0, goal - total_balance)

    return {
        'savings_balance': savings_balance,
        'pending_interest': pending_interest,
        'total_balance': total_balance,
        'progress': min(progress, 100),
        'remaining': remaining,
        'periods_due': full_periods,
    }


def accrue_interest_for_order(order_id):
    """Record interest accrual for all due periods on a single order.

    Returns a dict with results or None if order is not eligible.
    """
    db = database.get_db()
    order = db.execute('SELECT * FROM ship_orders WHERE id = ?', (order_id,)).fetchone()
    if not order or order['status'] != 'active':
        return None

    settings = models.get_interest_settings()
    rate = settings['interest_rate']
    period = settings['interest_period']
    period_days = PERIOD_DAYS.get(period, 30)

    savings_balance = order['amount_deposited'] + order['interest_earned']
    if savings_balance <= 0:
        return {'periods_accrued': 0, 'interest_added': 0, 'new_balance': 0}

    # Find the last accrual date
    last_log = db.execute(
        'SELECT accrued_at FROM interest_log WHERE order_id = ? ORDER BY accrued_at DESC LIMIT 1',
        (order_id,)
    ).fetchone()

    if last_log:
        last_accrual = datetime.fromisoformat(last_log['accrued_at'])
    else:
        last_accrual = datetime.fromisoformat(order['created_at'])

    now = datetime.utcnow()
    days_elapsed = (now - last_accrual).days
    full_periods = days_elapsed // period_days

    if full_periods == 0:
        return {'periods_accrued': 0, 'interest_added': 0, 'new_balance': savings_balance}

    total_new_interest = 0.0
    balance = savings_balance

    for i in range(full_periods):
        period_interest = balance * rate
        accrual_time = last_accrual + timedelta(days=period_days * (i + 1))

        db.execute(
            'INSERT INTO interest_log (order_id, amount, balance_before, balance_after, accrued_at) '
            'VALUES (?, ?, ?, ?, ?)',
            (order_id, period_interest, balance, balance + period_interest, accrual_time.isoformat())
        )

        balance += period_interest
        total_new_interest += period_interest

    # Update the denormalized interest_earned on the order
    db.execute(
        "UPDATE ship_orders SET interest_earned = interest_earned + ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (total_new_interest, order_id)
    )
    db.commit()

    # Check if goal is now completed
    order = db.execute('SELECT * FROM ship_orders WHERE id = ?', (order_id,)).fetchone()
    new_balance = order['amount_deposited'] + order['interest_earned']
    if new_balance >= order['goal_price']:
        models.update_order_status(order_id, 'completed')

    return {
        'periods_accrued': full_periods,
        'interest_added': total_new_interest,
        'new_balance': balance,
    }


def accrue_interest_all():
    """Accrue interest for all active orders. Returns summary."""
    db = database.get_db()
    active_orders = db.execute(
        "SELECT id FROM ship_orders WHERE status = 'active'"
    ).fetchall()

    results = []
    for order_row in active_orders:
        result = accrue_interest_for_order(order_row['id'])
        if result and result['periods_accrued'] > 0:
            results.append({'order_id': order_row['id'], **result})

    return results
