import logging
from datetime import datetime, timedelta
import database
import models

logger = logging.getLogger(__name__)

PERIOD_DAYS = {
    'weekly': 7,
    'biweekly': 14,
    'monthly': 30,
}


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


def calculate_current_balance(order):
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
    db = database.get_db()
    total_deposits = order['amount_deposited']
    accrued_interest = order['interest_earned']
    savings_balance = total_deposits + accrued_interest

    # All deposits earn interest, weighted by age (prorated under 30 days)
    effective_deposits = _get_effective_balance(db, order['id'])
    effective_balance = effective_deposits + accrued_interest

    settings = models.get_interest_settings()
    rate = settings['interest_rate']
    period = settings['interest_period']
    period_days = PERIOD_DAYS.get(period, 30)

    # Find the last accrual date
    logs = db.execute(
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

    # Compound interest for each un-recorded period on EFFECTIVE balance only
    pending_interest = 0.0
    temp_balance = effective_balance
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
        'effective_balance': effective_balance,
        'pending_interest': pending_interest,
        'total_balance': total_balance,
        'progress': min(progress, 100),
        'remaining': remaining,
        'periods_due': full_periods,
    }


def accrue_interest_for_order(order_id):
    """Record interest accrual for all due periods on a single order.

    Interest accrues on the effective balance: each deposit is weighted by
    min(age_in_days / 30, 1.0), plus all previously accrued interest at full
    rate. Returns a dict with results or None if order is not active.
    """
    db = database.get_db()
    order = db.execute('SELECT * FROM ship_orders WHERE id = ?', (order_id,)).fetchone()
    if not order or order['status'] != 'active':
        logger.debug('Order %s: skip (status=%s)', order_id, order['status'] if order else 'NOT FOUND')
        return None

    settings = models.get_interest_settings()
    rate = settings['interest_rate']
    period = settings['interest_period']
    period_days = PERIOD_DAYS.get(period, 30)

    # All deposits earn interest, weighted by age (prorated under 30 days)
    effective_deposits = _get_effective_balance(db, order_id)
    effective_balance = effective_deposits + order['interest_earned']

    if effective_balance <= 0:
        logger.info('Order %s (%s): effective_balance=0 (effective_deposits=%.2f, interest_earned=%.2f)',
                     order_id, order['ship_name'], effective_deposits, order['interest_earned'])
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

    logger.info('Order %s (%s): effective=%.2f, last_accrual=%s, days_elapsed=%d, '
                'period=%s(%dd), full_periods=%d',
                order_id, order['ship_name'], effective_balance,
                last_accrual.isoformat(), days_elapsed, period, period_days, full_periods)

    if full_periods == 0:
        return {'periods_accrued': 0, 'interest_added': 0, 'new_balance': effective_balance}

    total_new_interest = 0.0
    balance = effective_balance

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

    # Notify user about interest accrual
    order = db.execute('SELECT * FROM ship_orders WHERE id = ?', (order_id,)).fetchone()
    models.create_notification(
        user_id=order['user_id'],
        notification_type='interest_accrued',
        message=f'{total_new_interest:,.2f} ISK interest accrued on your '
                f'{order["ship_name"]} goal over {full_periods} period(s).',
        order_id=order_id
    )

    # Check if goal is now completed
    new_balance = order['amount_deposited'] + order['interest_earned']
    if new_balance >= order['goal_price']:
        models.update_order_status(order_id, 'completed')
        models.create_notification(
            user_id=order['user_id'],
            notification_type='goal_completed',
            message=f'Congratulations! Your savings goal for {order["ship_name"]} is complete!',
            order_id=order_id
        )

    logger.info('Order %s: accrued %d period(s), +%.2f ISK interest',
                order_id, full_periods, total_new_interest)

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

    logger.info('Interest accrual: %d active order(s) to check', len(active_orders))

    results = []
    for order_row in active_orders:
        result = accrue_interest_for_order(order_row['id'])
        if result and result['periods_accrued'] > 0:
            results.append({'order_id': order_row['id'], **result})

    logger.info('Interest accrual complete: %d order(s) accrued', len(results))
    return results
