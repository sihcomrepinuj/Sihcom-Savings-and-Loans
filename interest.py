import logging
import math
from datetime import datetime, timedelta
import database
import models

logger = logging.getLogger(__name__)

PERIOD_DAYS = {
    'daily': 1,
    'weekly': 7,
    'biweekly': 14,
    'monthly': 30,
}


def _apply_frozen_collateral(user_id, savings_balance, effective_balance):
    """Reduce the effective (interest-earning) balance by the user's outstanding
    credit-line balance. The collateralized portion of savings is frozen and
    stops accruing. Returns the adjusted effective balance.
    """
    if savings_balance <= 0:
        return 0.0
    frozen = models.get_outstanding_credit_line_balance_for_user(user_id)
    if frozen <= 0:
        return effective_balance
    free_ratio = max(0.0, savings_balance - frozen) / savings_balance
    return effective_balance * free_ratio


def calculate_current_balance(order):
    """Calculate the current savings balance including pending (un-accrued) interest.

    All deposits and previously accrued interest earn at the full rate. If the
    user has an outstanding credit-line balance, that portion of savings is
    frozen (does not accrue).

    Returns a dict with:
      - savings_balance: all deposits + accrued interest
      - effective_balance: savings_balance reduced by any frozen credit-line collateral
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

    # Full savings balance earns interest; frozen credit-line collateral reduces it.
    effective_balance = _apply_frozen_collateral(
        order['user_id'], savings_balance, savings_balance
    )

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


def estimate_time_to_goal(order, balance_info):
    """Estimate how long until compound interest alone funds the savings goal.

    Returns dict with:
      - state: one of 'ok', 'funded', 'paused', 'frozen', 'inactive'
      - days:  float days remaining (only when state == 'ok')

    Math: starting from total_balance (savings + pending interest) and an
    earning base of effective_balance, each period adds effective_balance * r
    to both. Solving total_balance + effective_balance * ((1+r)^n - 1) = goal:
        n_periods = log(1 + (goal - total_balance) / effective_balance) / log(1+r)
    """
    if order['status'] != 'active':
        return {'state': 'inactive', 'days': None}

    if models.is_user_interest_paused(order['user_id']):
        return {'state': 'paused', 'days': None}

    settings = models.get_interest_settings()
    rate = float(settings['interest_rate'])
    if rate <= 0:
        return {'state': 'paused', 'days': None}

    goal = float(order['goal_price'])
    total_balance = balance_info['total_balance']
    effective_balance = balance_info['effective_balance']

    if total_balance >= goal:
        return {'state': 'funded', 'days': None}
    if effective_balance <= 0:
        return {'state': 'frozen', 'days': None}

    period_days = PERIOD_DAYS.get(settings['interest_period'], 30)
    growth_needed = 1 + (goal - total_balance) / effective_balance
    n_periods = math.log(growth_needed) / math.log(1 + rate)
    return {'state': 'ok', 'days': n_periods * period_days}


def accrue_interest_for_order(order_id):
    """Record interest accrual for all due periods on a single order.

    Interest accrues on the full savings balance (deposits + previously accrued
    interest). If the user has paused interest, the order is skipped. If the
    user has an outstanding credit-line balance, that portion of savings is
    frozen and the earning base is reduced accordingly. Returns a dict with
    results or None if order is not active or user is paused.
    """
    db = database.get_db()
    order = db.execute('SELECT * FROM ship_orders WHERE id = ?', (order_id,)).fetchone()
    if not order or order['status'] != 'active':
        logger.debug('Order %s: skip (status=%s)', order_id, order['status'] if order else 'NOT FOUND')
        return None

    if models.is_user_interest_paused(order['user_id']):
        logger.info('Order %s: user_id=%s has paused interest, skipping', order_id, order['user_id'])
        return None

    settings = models.get_interest_settings()
    rate = settings['interest_rate']
    period = settings['interest_period']
    period_days = PERIOD_DAYS.get(period, 30)

    savings_balance = order['amount_deposited'] + order['interest_earned']
    effective_balance = _apply_frozen_collateral(
        order['user_id'], savings_balance, savings_balance
    )

    if effective_balance <= 0:
        logger.info('Order %s (%s): effective_balance=0 (savings_balance=%.2f, interest_earned=%.2f)',
                     order_id, order['ship_name'], savings_balance, order['interest_earned'])
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


def calculate_loan_pending_interest(loan):
    """Estimate interest that will be accrued on a loan at the next scheduled
    run. Mirrors calculate_current_balance for goals.

    Returns a dict with:
      - current_balance: balance as recorded
      - pending_interest: estimated interest since last accrual
      - projected_balance: current_balance + pending_interest
      - periods_due: number of full periods since last accrual
    """
    db = database.get_db()
    settings = models.get_interest_settings()
    loan_settings = models.get_loan_settings()
    period_days = PERIOD_DAYS.get(settings['interest_period'], 30)

    if loan['product_type'] == 'credit_line':
        rate = settings['interest_rate']
    else:
        rate = loan_settings['general_loan_rate']

    last_log = db.execute(
        'SELECT accrued_at FROM loan_interest_log WHERE loan_id = ? '
        'ORDER BY accrued_at DESC LIMIT 1', (loan['id'],)
    ).fetchone()

    if last_log:
        last_accrual = datetime.fromisoformat(last_log['accrued_at'])
    elif loan['disbursed_at']:
        last_accrual = datetime.fromisoformat(loan['disbursed_at'])
    else:
        last_accrual = datetime.fromisoformat(loan['created_at'])

    days_elapsed = (datetime.utcnow() - last_accrual).days
    full_periods = days_elapsed // period_days

    pending = 0.0
    balance = float(loan['current_balance'])
    for _ in range(full_periods):
        period_interest = balance * rate
        pending += period_interest
        balance += period_interest

    return {
        'current_balance': float(loan['current_balance']),
        'pending_interest': pending,
        'projected_balance': float(loan['current_balance']) + pending,
        'periods_due': full_periods,
    }


def accrue_interest_for_loan(loan_id):
    """Record interest accrual for all due periods on a single loan.

    Skips if loan is not active, the loan itself has interest_paused, or the
    user has interest_paused. Credit-line loans use the savings rate;
    general loans use general_loan_rate. Returns a dict with results or None.
    """
    db = database.get_db()
    loan = db.execute('SELECT * FROM loans WHERE id = ?', (loan_id,)).fetchone()
    if not loan or loan['status'] != 'active':
        logger.debug('Loan %s: skip (status=%s)', loan_id,
                     loan['status'] if loan else 'NOT FOUND')
        return None

    if loan['interest_paused']:
        logger.info('Loan %s: interest paused, skipping', loan_id)
        return None

    if models.is_user_interest_paused(loan['user_id']):
        logger.info('Loan %s: user_id=%s has paused interest, skipping',
                    loan_id, loan['user_id'])
        return None

    settings = models.get_interest_settings()
    loan_settings = models.get_loan_settings()
    period_days = PERIOD_DAYS.get(settings['interest_period'], 30)

    if loan['product_type'] == 'credit_line':
        rate = settings['interest_rate']
    else:
        rate = loan_settings['general_loan_rate']

    last_log = db.execute(
        'SELECT accrued_at FROM loan_interest_log WHERE loan_id = ? '
        'ORDER BY accrued_at DESC LIMIT 1', (loan_id,)
    ).fetchone()

    if last_log:
        last_accrual = datetime.fromisoformat(last_log['accrued_at'])
    elif loan['disbursed_at']:
        last_accrual = datetime.fromisoformat(loan['disbursed_at'])
    else:
        last_accrual = datetime.fromisoformat(loan['created_at'])

    now = datetime.utcnow()
    days_elapsed = (now - last_accrual).days
    full_periods = days_elapsed // period_days

    logger.info('Loan %s (%s): balance=%.2f, last_accrual=%s, days_elapsed=%d, '
                'period_days=%d, full_periods=%d',
                loan_id, loan['product_type'], loan['current_balance'],
                last_accrual.isoformat(), days_elapsed, period_days, full_periods)

    if full_periods == 0:
        return {'periods_accrued': 0, 'interest_added': 0,
                'new_balance': float(loan['current_balance'])}

    balance = float(loan['current_balance'])
    total_new_interest = 0.0

    for i in range(full_periods):
        period_interest = balance * rate
        accrual_time = last_accrual + timedelta(days=period_days * (i + 1))

        db.execute(
            'INSERT INTO loan_interest_log (loan_id, amount, balance_before, '
            'balance_after, accrued_at) VALUES (?, ?, ?, ?, ?)',
            (loan_id, period_interest, balance, balance + period_interest,
             accrual_time.isoformat())
        )

        balance += period_interest
        total_new_interest += period_interest

    db.execute(
        'UPDATE loans SET current_balance = ? WHERE id = ?',
        (balance, loan_id)
    )
    db.commit()

    models.create_notification(
        user_id=loan['user_id'],
        notification_type='loan_interest_accrued',
        message=f'{total_new_interest:,.2f} ISK interest accrued on your loan '
                f'over {full_periods} period(s). New balance: {balance:,.2f} ISK.',
    )

    logger.info('Loan %s: accrued %d period(s), +%.2f ISK interest',
                loan_id, full_periods, total_new_interest)

    return {
        'periods_accrued': full_periods,
        'interest_added': total_new_interest,
        'new_balance': balance,
    }


def accrue_interest_all():
    """Accrue interest for all active orders and active loans. Returns a dict
    with 'orders' and 'loans' summary lists."""
    db = database.get_db()
    active_orders = db.execute(
        "SELECT id FROM ship_orders WHERE status = 'active'"
    ).fetchall()
    active_loans = db.execute(
        "SELECT id FROM loans WHERE status = 'active'"
    ).fetchall()

    logger.info('Interest accrual: %d active order(s), %d active loan(s) to check',
                len(active_orders), len(active_loans))

    order_results = []
    for order_row in active_orders:
        result = accrue_interest_for_order(order_row['id'])
        if result and result['periods_accrued'] > 0:
            order_results.append({'order_id': order_row['id'], **result})

    loan_results = []
    for loan_row in active_loans:
        result = accrue_interest_for_loan(loan_row['id'])
        if result and result['periods_accrued'] > 0:
            loan_results.append({'loan_id': loan_row['id'], **result})

    logger.info('Interest accrual complete: %d order(s), %d loan(s) accrued',
                len(order_results), len(loan_results))
    return {'orders': order_results, 'loans': loan_results}
