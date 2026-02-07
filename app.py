import logging
import secrets
from functools import wraps
from flask import (
    Flask, session, redirect, url_for, render_template,
    request, flash, abort, g
)
from preston import Preston
from config import Config
import database
import models
import interest
import wallet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# --- Database lifecycle ---
app.teardown_appcontext(database.close_db)

with app.app_context():
    database.init_db()


# --- Template filters ---

@app.template_filter('isk')
def format_isk(value):
    if value is None:
        return '0.00 ISK'
    return f'{value:,.2f} ISK'


# --- Auth decorators ---

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'character_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'character_id' not in session:
            return redirect(url_for('index'))
        if not session.get('is_admin'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


# --- Preston SSO setup ---

base_preston = Preston(
    user_agent=Config.USER_AGENT,
    client_id=Config.EVE_CLIENT_ID,
    client_secret=Config.EVE_CLIENT_SECRET,
    callback_url=Config.EVE_CALLBACK_URL,
    scope='esi-wallet.read_character_wallet.v1',
)


# --- Public routes ---

@app.route('/')
def index():
    if 'character_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login')
def login():
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    auth_url = base_preston.get_authorize_url(state=state)
    return redirect(auth_url)


@app.route('/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')
    logger.info(f'Callback hit: code={bool(code)}, state={state}, session_state={session.get("oauth_state")}')

    if not code or state != session.pop('oauth_state', None):
        logger.warning('State mismatch or no code — authentication failed')
        flash('Authentication failed. Please try again.', 'danger')
        return redirect(url_for('index'))

    try:
        auth_preston = base_preston.authenticate(code)
    except Exception as e:
        logger.error(f'Preston authenticate error: {e}')
        flash('SSO authentication error. Please try again.', 'danger')
        return redirect(url_for('index'))

    try:
        whoami = auth_preston.whoami()
        logger.info(f'whoami result: {whoami}')
        character_id = int(whoami['character_id'])
        character_name = whoami['character_name']
    except Exception as e:
        logger.error(f'whoami error: {e}')
        flash('Failed to retrieve character info. Please try again.', 'danger')
        return redirect(url_for('index'))

    user = models.get_or_create_user(
        character_id=character_id,
        character_name=character_name,
        refresh_token=auth_preston.refresh_token,
    )

    session['character_id'] = character_id
    session['character_name'] = character_name
    session['user_id'] = user['id']
    session['is_admin'] = bool(user['is_admin'])

    flash(f'Welcome, {character_name}!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


# --- Member routes ---

@app.route('/dashboard')
@login_required
def dashboard():
    orders = models.get_orders_for_user(session['user_id'])
    balances = {}
    for order in orders:
        if order['status'] in ('active', 'withdrawal_pending'):
            balances[order['id']] = interest.calculate_current_balance(order)
    return render_template('dashboard.html', orders=orders, balances=balances)


@app.route('/catalog')
@login_required
def catalog():
    ships = models.get_available_catalog()
    has_active = models.user_has_active_or_pending_order(session['user_id'])
    return render_template('catalog.html', ships=ships, has_active=has_active)


@app.route('/catalog/<int:ship_id>/request', methods=['POST'])
@login_required
def request_ship(ship_id):
    if models.user_has_active_or_pending_order(session['user_id']):
        flash('You already have an active or pending savings goal. '
              'Complete or withdraw it before starting a new one.', 'warning')
        return redirect(url_for('catalog'))

    ship = models.get_catalog_ship(ship_id)
    if not ship or not ship['is_available']:
        abort(404)

    order_id = models.create_order(
        user_id=session['user_id'],
        ship_name=ship['ship_name'],
        goal_price=ship['price'],
        status='pending_approval',
    )
    flash(f'Savings goal for {ship["ship_name"]} submitted for approval!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['user_id'] != session['user_id'] and not session.get('is_admin'):
        abort(403)

    balance_info = interest.calculate_current_balance(order)
    deposits = models.get_deposits_for_order(order_id)
    interest_logs = models.get_interest_logs_for_order(order_id)
    user = models.get_user_by_id(order['user_id'])

    return render_template(
        'order_detail.html',
        order=order,
        balance=balance_info,
        deposits=deposits,
        interest_logs=interest_logs,
        owner=user,
    )


@app.route('/order/<int:order_id>/withdraw', methods=['POST'])
@login_required
def request_withdrawal(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['user_id'] != session['user_id']:
        abort(403)
    if order['status'] != 'active':
        flash('Only active savings goals can be withdrawn.', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))

    models.update_order_status(order_id, 'withdrawal_pending')
    flash('Withdrawal request submitted. Waiting for admin approval.', 'info')
    return redirect(url_for('order_detail', order_id=order_id))


# --- Admin routes ---

@app.route('/admin')
@admin_required
def admin_dashboard():
    all_orders = models.get_all_orders()
    withdrawal_requests = models.get_withdrawal_pending_orders()
    pending_approvals = models.get_pending_approval_orders()
    unmatched = models.get_unmatched_entries()

    balances = {}
    for order in all_orders:
        if order['status'] in ('active', 'withdrawal_pending'):
            balances[order['id']] = interest.calculate_current_balance(order)

    settings = models.get_interest_settings()

    active_orders = [o for o in all_orders if o['status'] == 'active']
    total_deposited = sum(o['amount_deposited'] for o in active_orders)
    total_interest = sum(o['interest_earned'] for o in active_orders)
    total_goal = sum(o['goal_price'] for o in active_orders)

    stats = {
        'active_count': len(active_orders),
        'total_deposited': total_deposited,
        'total_interest': total_interest,
        'total_goal': total_goal,
        'withdrawal_count': len(withdrawal_requests),
        'pending_approval_count': len(pending_approvals),
        'unmatched_count': len(unmatched),
    }

    return render_template(
        'admin/dashboard.html',
        orders=all_orders,
        withdrawal_requests=withdrawal_requests,
        pending_approvals=pending_approvals,
        balances=balances,
        settings=settings,
        stats=stats,
    )


@app.route('/admin/users')
@admin_required
def admin_users():
    users = models.get_all_users()
    return render_template('admin/users.html', users=users)


# --- Admin: Ship Catalog ---

@app.route('/admin/catalog', methods=['GET'])
@admin_required
def admin_catalog():
    ships = models.get_all_catalog()
    return render_template('admin/catalog.html', ships=ships)


@app.route('/admin/catalog/add', methods=['POST'])
@admin_required
def admin_catalog_add():
    ship_name = request.form.get('ship_name', '').strip()
    price = request.form.get('price', type=float)
    description = request.form.get('description', '').strip() or None

    if not ship_name or not price or price <= 0:
        flash('Please provide a valid ship name and price.', 'danger')
        return redirect(url_for('admin_catalog'))

    models.add_catalog_ship(ship_name, price, description)
    flash(f'{ship_name} added to catalog.', 'success')
    return redirect(url_for('admin_catalog'))


@app.route('/admin/catalog/<int:ship_id>/edit', methods=['POST'])
@admin_required
def admin_catalog_edit(ship_id):
    ship = models.get_catalog_ship(ship_id)
    if not ship:
        abort(404)

    ship_name = request.form.get('ship_name', '').strip()
    price = request.form.get('price', type=float)
    description = request.form.get('description', '').strip() or None
    is_available = 1 if request.form.get('is_available') else 0

    if not ship_name or not price or price <= 0:
        flash('Please provide a valid ship name and price.', 'danger')
        return redirect(url_for('admin_catalog'))

    models.update_catalog_ship(ship_id, ship_name, price, description, is_available)
    flash(f'{ship_name} updated.', 'success')
    return redirect(url_for('admin_catalog'))


@app.route('/admin/catalog/<int:ship_id>/remove', methods=['POST'])
@admin_required
def admin_catalog_remove(ship_id):
    ship = models.get_catalog_ship(ship_id)
    if not ship:
        abort(404)
    models.remove_catalog_ship(ship_id)
    flash(f'{ship["ship_name"]} removed from catalog.', 'info')
    return redirect(url_for('admin_catalog'))


# --- Admin: Order Management ---

@app.route('/admin/order/new', methods=['GET', 'POST'])
@admin_required
def admin_create_order():
    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        ship_name = request.form.get('ship_name', '').strip()
        goal_price = request.form.get('goal_price', type=float)
        notes = request.form.get('notes', '').strip() or None

        if not user_id or not ship_name or not goal_price or goal_price <= 0:
            flash('Please fill in all required fields with valid values.', 'danger')
            users = models.get_all_users()
            return render_template('admin/create_order.html', users=users)

        # Admin-created orders go straight to active
        order_id = models.create_order(user_id, ship_name, goal_price, notes, status='active')
        flash(f'Savings goal created for {ship_name}.', 'success')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    users = models.get_all_users()
    return render_template('admin/create_order.html', users=users)


@app.route('/admin/order/<int:order_id>')
@admin_required
def admin_order_detail(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)

    balance_info = interest.calculate_current_balance(order)
    deposits = models.get_deposits_for_order(order_id)
    interest_logs = models.get_interest_logs_for_order(order_id)
    user = models.get_user_by_id(order['user_id'])

    return render_template(
        'admin/order_detail.html',
        order=order,
        balance=balance_info,
        deposits=deposits,
        interest_logs=interest_logs,
        owner=user,
    )


@app.route('/admin/order/<int:order_id>/approve', methods=['POST'])
@admin_required
def admin_approve_order(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['status'] != 'pending_approval':
        flash('This order is not pending approval.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.update_order_status(order_id, 'active')
    user = models.get_user_by_id(order['user_id'])
    flash(f"Savings goal approved for {user['character_name']} - {order['ship_name']}.", 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/order/<int:order_id>/reject', methods=['POST'])
@admin_required
def admin_reject_order(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['status'] != 'pending_approval':
        flash('This order is not pending approval.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.update_order_status(order_id, 'cancelled')
    flash('Savings goal request rejected.', 'info')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/order/<int:order_id>/deposit', methods=['POST'])
@admin_required
def admin_record_deposit(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['status'] != 'active':
        flash('Can only record deposits on active savings goals.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    amount = request.form.get('amount', type=float)
    note = request.form.get('note', '').strip() or None

    if not amount or amount <= 0:
        flash('Please enter a valid deposit amount.', 'danger')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.record_deposit(order_id, amount, session['user_id'], note, source='manual')
    flash(f'Deposit of {amount:,.2f} ISK recorded.', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/order/<int:order_id>/accrue', methods=['POST'])
@admin_required
def admin_accrue_interest(order_id):
    result = interest.accrue_interest_for_order(order_id)
    if result is None:
        flash('Order is not eligible for interest accrual.', 'warning')
    elif result['periods_accrued'] == 0:
        flash('No interest periods are due yet.', 'info')
    else:
        flash(
            f"Accrued {result['interest_added']:,.2f} ISK interest "
            f"over {result['periods_accrued']} period(s).",
            'success'
        )
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/accrue-all', methods=['POST'])
@admin_required
def admin_accrue_all():
    results = interest.accrue_interest_all()
    if not results:
        flash('No interest was due on any active orders.', 'info')
    else:
        total = sum(r['interest_added'] for r in results)
        flash(
            f"Accrued interest on {len(results)} order(s), "
            f"totaling {total:,.2f} ISK.",
            'success'
        )
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/order/<int:order_id>/cancel', methods=['POST'])
@admin_required
def admin_cancel_order(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['status'] not in ('active', 'withdrawal_pending', 'pending_approval'):
        flash('This order cannot be cancelled.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.update_order_status(order_id, 'cancelled')
    flash('Savings goal has been cancelled.', 'info')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/order/<int:order_id>/approve-withdrawal', methods=['POST'])
@admin_required
def admin_approve_withdrawal(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['status'] != 'withdrawal_pending':
        flash('This order does not have a pending withdrawal request.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.update_order_status(order_id, 'withdrawn')
    balance = order['amount_deposited'] + order['interest_earned']
    user = models.get_user_by_id(order['user_id'])
    flash(
        f"Withdrawal approved for {user['character_name']}. "
        f"Please send {balance:,.2f} ISK in-game.",
        'success'
    )
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/order/<int:order_id>/deny-withdrawal', methods=['POST'])
@admin_required
def admin_deny_withdrawal(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['status'] != 'withdrawal_pending':
        flash('This order does not have a pending withdrawal request.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.update_order_status(order_id, 'active')
    flash('Withdrawal request denied. Savings goal is active again.', 'info')
    return redirect(url_for('admin_dashboard'))


# --- Admin: Wallet Sync ---

@app.route('/admin/sync-wallet', methods=['POST'])
@admin_required
def admin_sync_wallet():
    result = wallet.sync_wallet()
    if result is None:
        flash('Could not sync wallet. Make sure the admin account has logged in '
              'and granted wallet access.', 'danger')
    elif result['total_processed'] == 0:
        flash('Wallet synced. No new deposits found.', 'info')
    else:
        parts = []
        if result['matched_count']:
            parts.append(
                f"{result['matched_count']} deposit(s) matched "
                f"({result['matched_isk']:,.2f} ISK)"
            )
        if result['unmatched_count']:
            parts.append(f"{result['unmatched_count']} unmatched transaction(s)")
        flash(f"Wallet synced: {', '.join(parts)}.", 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/unmatched')
@admin_required
def admin_unmatched():
    entries = models.get_unmatched_entries()
    active_orders = models.get_active_orders()
    return render_template('admin/unmatched.html', entries=entries, orders=active_orders)


@app.route('/admin/unmatched/<int:journal_id>/assign', methods=['POST'])
@admin_required
def admin_assign_unmatched(journal_id):
    entry = models.get_journal_entry(journal_id)
    if not entry or entry['status'] != 'unmatched':
        flash('Transaction not found or already processed.', 'warning')
        return redirect(url_for('admin_unmatched'))

    order_id = request.form.get('order_id', type=int)
    order = models.get_order(order_id) if order_id else None
    if not order or order['status'] != 'active':
        flash('Please select a valid active order.', 'danger')
        return redirect(url_for('admin_unmatched'))

    # Record the deposit
    admin = models.get_admin_user()
    models.record_deposit(
        order_id=order_id,
        amount=entry['amount'],
        recorded_by_user_id=admin['id'] if admin else None,
        note=f'Wallet (manual assign): {entry["reason"]}' if entry['reason'] else 'Wallet (manual assign)',
        source='wallet',
        journal_id=journal_id,
    )
    models.mark_journal_matched(journal_id, order_id)
    flash(f"Assigned {entry['amount']:,.2f} ISK from {entry['sender_name']} to order #{order_id}.", 'success')
    return redirect(url_for('admin_unmatched'))


@app.route('/admin/unmatched/<int:journal_id>/ignore', methods=['POST'])
@admin_required
def admin_ignore_unmatched(journal_id):
    entry = models.get_journal_entry(journal_id)
    if not entry or entry['status'] != 'unmatched':
        flash('Transaction not found or already processed.', 'warning')
        return redirect(url_for('admin_unmatched'))

    models.mark_journal_ignored(journal_id)
    flash(f"Transaction from {entry['sender_name']} marked as ignored.", 'info')
    return redirect(url_for('admin_unmatched'))


# --- Admin: Settings ---

@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        rate = request.form.get('interest_rate', type=float)
        period = request.form.get('interest_period', '')

        if rate is None or rate < 0 or rate > 1:
            flash('Interest rate must be between 0 and 1 (e.g. 0.05 for 5%).', 'danger')
        elif period not in ('weekly', 'biweekly', 'monthly'):
            flash('Invalid interest period.', 'danger')
        else:
            models.set_setting('interest_rate', str(rate))
            models.set_setting('interest_period', period)
            flash('Settings updated.', 'success')

        return redirect(url_for('admin_settings'))

    settings = models.get_interest_settings()
    return render_template('admin/settings.html', settings=settings)


# --- Error handlers ---

@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', code=403, message='Access denied.'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Page not found.'), 404


if __name__ == '__main__':
    app.run(debug=True)
