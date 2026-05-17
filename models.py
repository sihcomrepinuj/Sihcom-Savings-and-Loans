from config import Config
import database


# --- Users ---

def get_or_create_user(character_id, character_name, refresh_token):
    db = database.get_db()
    user = db.execute(
        'SELECT * FROM users WHERE character_id = ?', (character_id,)
    ).fetchone()

    if user is None:
        is_admin = 1 if character_id == Config.ADMIN_CHARACTER_ID else 0
        db.execute(
            'INSERT INTO users (character_id, character_name, refresh_token, is_admin) '
            'VALUES (?, ?, ?, ?)',
            (character_id, character_name, refresh_token, is_admin)
        )
        db.commit()
        user = db.execute(
            'SELECT * FROM users WHERE character_id = ?', (character_id,)
        ).fetchone()
    else:
        # Only update refresh_token if a new one was provided (admin login)
        if refresh_token:
            db.execute(
                'UPDATE users SET refresh_token = ?, character_name = ? WHERE character_id = ?',
                (refresh_token, character_name, character_id)
            )
        else:
            db.execute(
                'UPDATE users SET character_name = ? WHERE character_id = ?',
                (character_name, character_id)
            )
        db.commit()
        user = db.execute(
            'SELECT * FROM users WHERE character_id = ?', (character_id,)
        ).fetchone()

    return user


def get_user_by_id(user_id):
    db = database.get_db()
    return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def get_user_by_character_id(character_id):
    db = database.get_db()
    return db.execute(
        'SELECT * FROM users WHERE character_id = ?', (character_id,)
    ).fetchone()


def get_all_users():
    db = database.get_db()
    return db.execute('SELECT * FROM users ORDER BY character_name').fetchall()


def get_admin_user():
    db = database.get_db()
    return db.execute('SELECT * FROM users WHERE is_admin = 1 LIMIT 1').fetchone()


# --- Ship Catalog ---

def get_available_catalog():
    db = database.get_db()
    return db.execute(
        'SELECT * FROM ship_catalog WHERE is_available = 1 ORDER BY category, ship_name'
    ).fetchall()


def get_all_catalog():
    db = database.get_db()
    return db.execute('SELECT * FROM ship_catalog ORDER BY category, ship_name').fetchall()


def get_catalog_categories():
    """Return distinct category names from the catalog."""
    db = database.get_db()
    rows = db.execute(
        'SELECT DISTINCT category FROM ship_catalog ORDER BY category'
    ).fetchall()
    return [r['category'] for r in rows]


def get_catalog_ship(ship_id):
    db = database.get_db()
    return db.execute('SELECT * FROM ship_catalog WHERE id = ?', (ship_id,)).fetchone()


def add_catalog_ship(ship_name, price, description=None, type_id=None, category='Uncategorized'):
    db = database.get_db()
    db.execute(
        'INSERT INTO ship_catalog (ship_name, price, description, type_id, category) VALUES (?, ?, ?, ?, ?)',
        (ship_name, price, description, type_id, category)
    )
    db.commit()


def update_catalog_ship(ship_id, ship_name, price, description, is_available, type_id=None, category='Uncategorized'):
    db = database.get_db()
    db.execute(
        'UPDATE ship_catalog SET ship_name = ?, price = ?, description = ?, is_available = ?, type_id = ?, category = ? '
        'WHERE id = ?',
        (ship_name, price, description, is_available, type_id, category, ship_id)
    )
    db.commit()


def remove_catalog_ship(ship_id):
    db = database.get_db()
    db.execute('DELETE FROM ship_catalog WHERE id = ?', (ship_id,))
    db.commit()


# --- Ship Orders ---

def create_order(user_id, ship_name, goal_price, notes=None, status='pending_approval', type_id=None, category=None):
    db = database.get_db()
    db.execute(
        'INSERT INTO ship_orders (user_id, ship_name, goal_price, notes, status, type_id, category) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (user_id, ship_name, goal_price, notes, status, type_id, category)
    )
    db.commit()
    return db.execute('SELECT last_insert_rowid()').fetchone()[0]


def get_order(order_id):
    db = database.get_db()
    return db.execute('SELECT * FROM ship_orders WHERE id = ?', (order_id,)).fetchone()


def get_orders_for_user(user_id):
    db = database.get_db()
    return db.execute(
        'SELECT * FROM ship_orders WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()


def get_active_order_for_user(user_id):
    """Get the one active order for a user (one-goal-at-a-time rule)."""
    db = database.get_db()
    return db.execute(
        "SELECT * FROM ship_orders WHERE user_id = ? AND status = 'active' LIMIT 1",
        (user_id,)
    ).fetchone()


def user_has_active_or_pending_order(user_id):
    """Check if user already has an active or pending_approval order."""
    db = database.get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM ship_orders "
        "WHERE user_id = ? AND status IN ('active', 'pending_approval')",
        (user_id,)
    ).fetchone()
    return row['cnt'] > 0


def get_all_orders():
    db = database.get_db()
    return db.execute(
        'SELECT o.*, u.character_name FROM ship_orders o '
        'JOIN users u ON o.user_id = u.id '
        'ORDER BY o.created_at DESC'
    ).fetchall()


def get_active_orders():
    db = database.get_db()
    return db.execute(
        'SELECT o.*, u.character_name FROM ship_orders o '
        'JOIN users u ON o.user_id = u.id '
        "WHERE o.status = 'active' "
        'ORDER BY o.created_at DESC'
    ).fetchall()


def get_leaderboard():
    """Return active savers with character_name, progress, and public goal info.

    Ship name is included but only shown on leaderboard if is_public = 1.
    Sorted by progress descending.
    """
    db = database.get_db()
    rows = db.execute(
        'SELECT u.character_name, '
        '  o.amount_deposited + o.interest_earned AS balance, '
        '  o.goal_price, o.ship_name, o.is_public '
        'FROM ship_orders o '
        'JOIN users u ON o.user_id = u.id '
        "WHERE o.status = 'active' AND o.goal_price > 0 "
        'ORDER BY (o.amount_deposited + o.interest_earned) * 1.0 / o.goal_price DESC'
    ).fetchall()
    result = []
    for r in rows:
        progress = min((r['balance'] / r['goal_price']) * 100, 100) if r['goal_price'] > 0 else 0
        result.append({
            'character_name': r['character_name'],
            'progress': round(progress, 1),
            'ship_name': r['ship_name'] if r['is_public'] else None,
            'is_public': r['is_public'],
        })
    return result


def get_completed_badges_for_active_users():
    """Return completed orders (with type_id) for users who have active goals."""
    db = database.get_db()
    return db.execute(
        'SELECT u.character_name, o.ship_name, o.type_id, o.category '
        'FROM ship_orders o '
        'JOIN users u ON o.user_id = u.id '
        "WHERE o.status = 'completed' AND o.type_id IS NOT NULL "
        '  AND o.user_id IN ('
        '    SELECT user_id FROM ship_orders '
        "    WHERE status = 'active' AND goal_price > 0"
        '  ) '
        'ORDER BY o.updated_at ASC',
    ).fetchall()


def toggle_order_public(order_id, is_public):
    """Toggle whether an order's ship name appears on the leaderboard."""
    db = database.get_db()
    db.execute(
        "UPDATE ship_orders SET is_public = ?, updated_at = datetime('now') WHERE id = ?",
        (1 if is_public else 0, order_id)
    )
    db.commit()


def update_order_details(order_id, ship_name, goal_price, is_public, type_id=None, category=None):
    """Admin: update an order's ship name, goal price, type_id, category, and visibility."""
    db = database.get_db()
    db.execute(
        "UPDATE ship_orders SET ship_name = ?, goal_price = ?, is_public = ?, type_id = ?, category = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (ship_name, goal_price, 1 if is_public else 0, type_id, category, order_id)
    )
    db.commit()


def get_pending_approval_orders():
    db = database.get_db()
    return db.execute(
        'SELECT o.*, u.character_name FROM ship_orders o '
        'JOIN users u ON o.user_id = u.id '
        "WHERE o.status = 'pending_approval' "
        'ORDER BY o.created_at ASC'
    ).fetchall()


def get_withdrawal_pending_orders():
    db = database.get_db()
    return db.execute(
        'SELECT o.*, u.character_name FROM ship_orders o '
        'JOIN users u ON o.user_id = u.id '
        "WHERE o.status = 'withdrawal_pending' "
        'ORDER BY o.updated_at DESC'
    ).fetchall()


def update_order_status(order_id, status):
    db = database.get_db()
    db.execute(
        "UPDATE ship_orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, order_id)
    )
    db.commit()


# --- Deposits ---

def record_deposit(order_id, amount, recorded_by_user_id, note=None,
                   source='manual', journal_id=None):
    db = database.get_db()
    db.execute(
        'INSERT INTO deposits (order_id, amount, recorded_by, note, source, journal_id) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (order_id, amount, recorded_by_user_id, note, source, journal_id)
    )
    db.execute(
        "UPDATE ship_orders SET amount_deposited = amount_deposited + ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (amount, order_id)
    )
    db.commit()

    # Check if goal is now completed. Skip auto-completion if the user has an open
    # credit line collateralized by this savings — admin must settle the loan first.
    order = get_order(order_id)
    savings_balance = order['amount_deposited'] + order['interest_earned']
    if savings_balance >= order['goal_price']:
        if get_outstanding_credit_line_balance_for_user(order['user_id']) > 0:
            create_notification(
                user_id=order['user_id'],
                notification_type='goal_funded_pending_loan',
                message=f'Your savings goal for {order["ship_name"]} is fully funded, but an open '
                        f'credit line is still outstanding. Pay it off to release your savings.',
                order_id=order_id
            )
        else:
            update_order_status(order_id, 'completed')
            create_notification(
                user_id=order['user_id'],
                notification_type='goal_completed',
                message=f'Congratulations! Your savings goal for {order["ship_name"]} is complete!',
                order_id=order_id
            )


def get_deposits_for_order(order_id):
    db = database.get_db()
    return db.execute(
        'SELECT d.*, u.character_name as recorded_by_name '
        'FROM deposits d '
        'LEFT JOIN users u ON d.recorded_by = u.id '
        'WHERE d.order_id = ? ORDER BY d.deposit_date DESC',
        (order_id,)
    ).fetchall()


# --- Wallet Journal ---

def journal_entry_exists(journal_id):
    db = database.get_db()
    row = db.execute(
        'SELECT 1 FROM wallet_journal WHERE journal_id = ?', (journal_id,)
    ).fetchone()
    return row is not None


def insert_journal_entry(journal_id, sender_id, sender_name, amount, reason,
                         journal_date, order_id=None, status='unmatched'):
    db = database.get_db()
    db.execute(
        'INSERT OR IGNORE INTO wallet_journal '
        '(journal_id, sender_id, sender_name, amount, reason, journal_date, order_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (journal_id, sender_id, sender_name, amount, reason, journal_date, order_id, status)
    )
    db.commit()


def get_unmatched_entries():
    db = database.get_db()
    return db.execute(
        "SELECT * FROM wallet_journal WHERE status = 'unmatched' ORDER BY journal_date DESC"
    ).fetchall()


def get_journal_entry(journal_id):
    db = database.get_db()
    return db.execute(
        'SELECT * FROM wallet_journal WHERE journal_id = ?', (journal_id,)
    ).fetchone()


def mark_journal_matched(journal_id, order_id):
    db = database.get_db()
    db.execute(
        "UPDATE wallet_journal SET status = 'matched', order_id = ? WHERE journal_id = ?",
        (order_id, journal_id)
    )
    db.commit()


def mark_journal_ignored(journal_id):
    db = database.get_db()
    db.execute(
        "UPDATE wallet_journal SET status = 'ignored' WHERE journal_id = ?",
        (journal_id,)
    )
    db.commit()


# --- Interest Log ---

def get_interest_logs_for_order(order_id):
    db = database.get_db()
    return db.execute(
        'SELECT * FROM interest_log WHERE order_id = ? ORDER BY accrued_at DESC',
        (order_id,)
    ).fetchall()


# --- Settings ---

def get_setting(key):
    db = database.get_db()
    row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else None


def set_setting(key, value):
    db = database.get_db()
    db.execute(
        'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
        (key, value)
    )
    db.commit()


def get_interest_settings():
    return {
        'interest_rate': float(get_setting('interest_rate') or '0.05'),
        'interest_period': get_setting('interest_period') or 'monthly',
    }


def get_loan_settings():
    return {
        'general_loan_rate': float(get_setting('general_loan_rate') or '0.125'),
    }


def get_affiliate_settings():
    return {
        'usd_to_isk_ratio': float(get_setting('usd_to_isk_ratio') or '1000000000'),
    }


# --- Notifications ---

def create_notification(user_id, notification_type, message, order_id=None):
    """Create a new notification for a user."""
    db = database.get_db()
    db.execute(
        'INSERT INTO notifications (user_id, order_id, type, message) '
        'VALUES (?, ?, ?, ?)',
        (user_id, order_id, notification_type, message)
    )
    db.commit()


def get_unread_count(user_id):
    """Get count of unread notifications for badge display."""
    db = database.get_db()
    row = db.execute(
        'SELECT COUNT(*) as cnt FROM notifications '
        'WHERE user_id = ? AND is_read = 0',
        (user_id,)
    ).fetchone()
    return row['cnt']


def get_recent_notifications(user_id, limit=20):
    """Get recent notifications (read and unread) for a user."""
    db = database.get_db()
    return db.execute(
        'SELECT * FROM notifications WHERE user_id = ? '
        'ORDER BY created_at DESC LIMIT ?',
        (user_id, limit)
    ).fetchall()


def mark_notifications_read(user_id):
    """Mark all notifications as read for a user."""
    db = database.get_db()
    db.execute(
        'UPDATE notifications SET is_read = 1 '
        'WHERE user_id = ? AND is_read = 0',
        (user_id,)
    )
    db.commit()


# --- User interest pause ---

def set_user_interest_paused(user_id, paused):
    """Pause or unpause both savings and loan interest accrual for a user."""
    db = database.get_db()
    db.execute(
        'UPDATE users SET interest_paused = ? WHERE id = ?',
        (1 if paused else 0, user_id)
    )
    db.commit()


def is_user_interest_paused(user_id):
    db = database.get_db()
    row = db.execute(
        'SELECT interest_paused FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    return bool(row['interest_paused']) if row else False


# --- Savings helpers (used for credit line eligibility / collateral) ---

def get_total_savings_balance_for_user(user_id):
    """Sum of active goals' amount_deposited + interest_earned (recorded only,
    not pending). Used for credit-line draw eligibility and collateral."""
    db = database.get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(amount_deposited + interest_earned), 0) AS total "
        "FROM ship_orders WHERE user_id = ? AND status = 'active'",
        (user_id,)
    ).fetchone()
    return float(row['total'])


# --- Loans ---

def create_loan(user_id, product_type, amount, status='pending_disbursement'):
    """Create a new loan record. Returns the new loan_id.

    product_type is 'credit_line' or 'general'.
    status is 'pending_disbursement' (credit line awaiting admin) or 'active'
    (general loan, originated and disbursed by admin in one step).
    """
    db = database.get_db()
    disbursed_at = "datetime('now')" if status == 'active' else None
    if disbursed_at:
        db.execute(
            "INSERT INTO loans (user_id, product_type, principal, current_balance, "
            "status, disbursed_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (user_id, product_type, amount, amount, status)
        )
    else:
        db.execute(
            "INSERT INTO loans (user_id, product_type, principal, current_balance, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, product_type, amount, amount, status)
        )
    db.commit()
    return db.execute('SELECT last_insert_rowid()').fetchone()[0]


def get_loan(loan_id):
    db = database.get_db()
    return db.execute('SELECT * FROM loans WHERE id = ?', (loan_id,)).fetchone()


def get_loans_for_user(user_id):
    db = database.get_db()
    return db.execute(
        'SELECT * FROM loans WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()


def get_open_loan_for_user(user_id):
    """Return the user's currently-open loan (pending_disbursement or active),
    or None. Enforces 'one loan at a time' rule."""
    db = database.get_db()
    return db.execute(
        "SELECT * FROM loans WHERE user_id = ? "
        "AND status IN ('pending_disbursement', 'active') LIMIT 1",
        (user_id,)
    ).fetchone()


def get_active_loans():
    """All loans currently active (excludes pending_disbursement and paid_in_full)."""
    db = database.get_db()
    return db.execute(
        "SELECT l.*, u.character_name FROM loans l "
        "JOIN users u ON l.user_id = u.id "
        "WHERE l.status = 'active' ORDER BY l.created_at DESC"
    ).fetchall()


def get_pending_disbursement_loans():
    db = database.get_db()
    return db.execute(
        "SELECT l.*, u.character_name FROM loans l "
        "JOIN users u ON l.user_id = u.id "
        "WHERE l.status = 'pending_disbursement' ORDER BY l.created_at ASC"
    ).fetchall()


def get_all_loans():
    db = database.get_db()
    return db.execute(
        "SELECT l.*, u.character_name FROM loans l "
        "JOIN users u ON l.user_id = u.id "
        "ORDER BY l.created_at DESC"
    ).fetchall()


def mark_loan_disbursed(loan_id):
    db = database.get_db()
    db.execute(
        "UPDATE loans SET status = 'active', disbursed_at = datetime('now') "
        "WHERE id = ? AND status = 'pending_disbursement'",
        (loan_id,)
    )
    db.commit()


def set_loan_interest_paused(loan_id, paused):
    db = database.get_db()
    db.execute(
        'UPDATE loans SET interest_paused = ? WHERE id = ?',
        (1 if paused else 0, loan_id)
    )
    db.commit()


def get_outstanding_credit_line_balance_for_user(user_id):
    """Sum current_balance across the user's active credit-line loans.
    Used to compute frozen collateral on savings interest accrual."""
    db = database.get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(current_balance), 0) AS total FROM loans "
        "WHERE user_id = ? AND status = 'active' AND product_type = 'credit_line'",
        (user_id,)
    ).fetchone()
    return float(row['total'])


def record_loan_payment(loan_id, amount, source='wallet', journal_id=None,
                        recorded_by=None, note=None):
    """Apply a payment to a loan. Returns a dict with:
      - applied: amount applied to the loan (<= input amount)
      - remainder: amount left over (input minus applied) — caller should
        route this to a savings goal or other product
      - new_balance: loan balance after payment
      - paid_in_full: bool, True if loan flipped to paid_in_full
    """
    db = database.get_db()
    loan = db.execute('SELECT * FROM loans WHERE id = ?', (loan_id,)).fetchone()
    if not loan or loan['status'] != 'active':
        return {'applied': 0.0, 'remainder': amount, 'new_balance': 0.0,
                'paid_in_full': False}

    balance = float(loan['current_balance'])
    applied = min(float(amount), balance)
    remainder = float(amount) - applied
    new_balance = balance - applied

    db.execute(
        'INSERT INTO loan_payments (loan_id, amount, source, journal_id, '
        'recorded_by, note) VALUES (?, ?, ?, ?, ?, ?)',
        (loan_id, applied, source, journal_id, recorded_by, note)
    )

    paid_in_full = new_balance <= 0.0001  # float tolerance
    if paid_in_full:
        db.execute(
            "UPDATE loans SET current_balance = 0, status = 'paid_in_full', "
            "closed_at = datetime('now') WHERE id = ?",
            (loan_id,)
        )
    else:
        db.execute(
            'UPDATE loans SET current_balance = ? WHERE id = ?',
            (new_balance, loan_id)
        )
    db.commit()

    return {
        'applied': applied,
        'remainder': remainder,
        'new_balance': 0.0 if paid_in_full else new_balance,
        'paid_in_full': paid_in_full,
    }


def get_loan_payments(loan_id):
    db = database.get_db()
    return db.execute(
        'SELECT p.*, u.character_name as recorded_by_name '
        'FROM loan_payments p '
        'LEFT JOIN users u ON p.recorded_by = u.id '
        'WHERE p.loan_id = ? ORDER BY p.paid_at DESC',
        (loan_id,)
    ).fetchall()


def get_loan_interest_logs(loan_id):
    db = database.get_db()
    return db.execute(
        'SELECT * FROM loan_interest_log WHERE loan_id = ? ORDER BY accrued_at DESC',
        (loan_id,)
    ).fetchall()
