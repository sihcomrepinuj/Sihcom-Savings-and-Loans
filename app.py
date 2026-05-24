import atexit
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
import esi
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# Production settings: trust Railway's proxy headers, secure cookies
import os
if os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RAILWAY_ENVIRONMENT_NAME'):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PREFERRED_URL_SCHEME'] = 'https'

# --- Database lifecycle ---
app.teardown_appcontext(database.close_db)

with app.app_context():
    database.init_db()


# --- Scheduled wallet sync ---

def _scheduled_wallet_sync():
    """Background job: sync wallet with Flask app context."""
    with app.app_context():
        try:
            result = wallet.sync_wallet()
            if result is None:
                logger.warning('Scheduled wallet sync: no admin refresh token')
            elif result['total_processed'] == 0:
                logger.info('Scheduled wallet sync: no new deposits')
            else:
                parts = []
                if result['matched_count']:
                    parts.append(
                        f"{result['matched_count']} deposit(s) matched "
                        f"({result['matched_isk']:,.2f} ISK)"
                    )
                if result['unmatched_count']:
                    parts.append(f"{result['unmatched_count']} unmatched")
                logger.info(f"Scheduled wallet sync: {', '.join(parts)}")
        except Exception:
            logger.exception('Scheduled wallet sync error')


def _scheduled_interest_accrual():
    """Background job: accrue interest on all active orders and loans."""
    with app.app_context():
        try:
            results = interest.accrue_interest_all()
            order_results = results['orders']
            loan_results = results['loans']
            if order_results or loan_results:
                order_total = sum(r['interest_added'] for r in order_results)
                loan_total = sum(r['interest_added'] for r in loan_results)
                logger.info(
                    f"Scheduled interest accrual: "
                    f"{len(order_results)} order(s) +{order_total:,.2f} ISK, "
                    f"{len(loan_results)} loan(s) +{loan_total:,.2f} ISK"
                )
            else:
                logger.info('Scheduled interest accrual: no interest due')
        except Exception:
            logger.exception('Scheduled interest accrual error')


if not app.debug:
    from datetime import datetime as _dt, timedelta as _td

    _scheduler = BackgroundScheduler(daemon=True)

    if Config.WALLET_SYNC_INTERVAL > 0:
        _scheduler.add_job(
            func=_scheduled_wallet_sync,
            trigger='interval',
            minutes=Config.WALLET_SYNC_INTERVAL,
            id='wallet_sync',
            misfire_grace_time=120,
            coalesce=True,
            max_instances=1,
        )
        logger.info(f'Wallet sync scheduled: every {Config.WALLET_SYNC_INTERVAL} min')

    if Config.INTEREST_ACCRUAL_INTERVAL > 0:
        _scheduler.add_job(
            func=_scheduled_interest_accrual,
            trigger='interval',
            hours=Config.INTEREST_ACCRUAL_INTERVAL,
            id='interest_accrual',
            misfire_grace_time=300,
            coalesce=True,
            max_instances=1,
        )
        # Catch-up accrual 30 seconds after startup
        _scheduler.add_job(
            func=_scheduled_interest_accrual,
            trigger='date',
            run_date=_dt.utcnow() + _td(seconds=30),
            id='interest_accrual_startup',
            misfire_grace_time=120,
        )
        logger.info(f'Interest accrual scheduled: every {Config.INTEREST_ACCRUAL_INTERVAL} hr (+ startup catch-up)')

    _scheduler.start()
    atexit.register(_scheduler.shutdown)


# --- Template filters ---

@app.template_filter('isk')
def format_isk(value):
    if value is None:
        return '0.00 ISK'
    return f'{value:,.2f} ISK'


@app.template_filter('isk_short')
def format_isk_short(value):
    """Abbreviated ISK for stat cards: 22B, 1.5T, 500M, 50K."""
    if value is None:
        return '0 ISK'
    v = float(value)
    if v >= 1_000_000_000_000:
        return f'{v / 1_000_000_000_000:,.1f}T ISK'
    if v >= 1_000_000_000:
        return f'{v / 1_000_000_000:,.1f}B ISK'
    if v >= 1_000_000:
        return f'{v / 1_000_000:,.1f}M ISK'
    if v >= 1_000:
        return f'{v / 1_000:,.1f}K ISK'
    return f'{v:,.0f} ISK'


@app.template_filter('ship_image')
def ship_image_url(type_id, size=256):
    """Return EVE image server URL for a ship render."""
    return esi.get_ship_image_url(type_id, size) if type_id else None


@app.template_filter('format_days_smart')
def format_days_smart(days):
    """Format a float number of days as a smart-unit estimate string."""
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


@app.template_filter('badge_url')
def badge_url_filter(category):
    """Return URL for a category badge image (supports .png or .svg)."""
    import os
    badge_dir = os.path.join(app.static_folder, 'badges')
    if not category:
        slug = 'placeholder'
    else:
        slug = category.lower().replace(' ', '-')
    # Check for PNG first, then SVG
    for ext in ('png', 'svg'):
        if os.path.exists(os.path.join(badge_dir, f'{slug}.{ext}')):
            return url_for('static', filename=f'badges/{slug}.{ext}')
    # Fallback to placeholder
    for ext in ('png', 'svg'):
        if os.path.exists(os.path.join(badge_dir, f'placeholder.{ext}')):
            return url_for('static', filename=f'badges/placeholder.{ext}')
    return url_for('static', filename='badges/placeholder.png')


# --- Context processors ---

@app.context_processor
def inject_admin_link():
    return {
        'admin_character_name': 'Bernie May Doff',
        'admin_evewho_url': f'https://evewho.com/character/{Config.ADMIN_CHARACTER_ID}',
    }


@app.context_processor
def inject_notification_count():
    if 'user_id' in session:
        return {'unread_notification_count': models.get_unread_count(session['user_id'])}
    return {'unread_notification_count': 0}


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

# Regular members: no ESI scopes needed, just authentication
member_preston = Preston(
    user_agent=Config.USER_AGENT,
    client_id=Config.EVE_CLIENT_ID,
    client_secret=Config.EVE_CLIENT_SECRET,
    callback_url=Config.EVE_CALLBACK_URL,
    scope='',
)

# Admin (Bernie): needs wallet read scope
admin_preston_base = Preston(
    user_agent=Config.USER_AGENT,
    client_id=Config.EVE_CLIENT_ID,
    client_secret=Config.EVE_CLIENT_SECRET,
    callback_url=Config.EVE_CALLBACK_URL,
    scope='esi-wallet.read_character_wallet.v1',
)


# --- Public routes ---

@app.route('/')
def index():
    rates = models.get_current_rates()
    return render_template('index.html', rates=rates)


@app.route('/savings')
def product_savings():
    rates = models.get_current_rates()
    return render_template('products/savings.html', rates=rates)


@app.route('/loans')
def product_loans():
    rates = models.get_current_rates()
    return render_template('products/loans.html', rates=rates)


@app.route('/credit-lines')
def product_credit_lines():
    rates = models.get_current_rates()
    return render_template('products/credit_lines.html', rates=rates)


@app.route('/login')
def login():
    admin_mode = request.args.get('admin') == '1'
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    session['login_admin_mode'] = admin_mode
    preston = admin_preston_base if admin_mode else member_preston
    auth_url = preston.get_authorize_url(state=state)
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

    admin_mode = session.pop('login_admin_mode', False)
    preston = admin_preston_base if admin_mode else member_preston

    try:
        auth_preston = preston.authenticate(code)
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

    # Only store refresh token for admin (wallet scope) logins
    refresh_token = auth_preston.refresh_token if admin_mode else None

    user = models.get_or_create_user(
        character_id=character_id,
        character_name=character_name,
        refresh_token=refresh_token,
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
    user_id = session['user_id']
    orders = models.get_orders_for_user(user_id)
    balances = {}
    for order in orders:
        if order['status'] in ('active', 'withdrawal_pending'):
            balances[order['id']] = interest.calculate_current_balance(order)

    open_loan = models.get_open_loan_for_user(user_id)
    loan_pending = None
    if open_loan and open_loan['status'] == 'active':
        loan_pending = interest.calculate_loan_pending_interest(open_loan)

    total_savings = models.get_total_savings_balance_for_user(user_id)
    can_request_credit_line = (open_loan is None) and (total_savings > 0)

    return render_template(
        'dashboard.html',
        orders=orders,
        balances=balances,
        open_loan=open_loan,
        loan_pending=loan_pending,
        total_savings=total_savings,
        can_request_credit_line=can_request_credit_line,
    )


@app.route('/catalog')
@login_required
def catalog():
    ships = models.get_available_catalog()
    has_active = models.user_has_active_or_pending_order(session['user_id'])
    # Group ships by category for display
    from collections import OrderedDict
    ships_by_category = OrderedDict()
    for ship in ships:
        cat = ship['category'] or 'Uncategorized'
        ships_by_category.setdefault(cat, []).append(ship)
    return render_template('catalog.html', ships_by_category=ships_by_category, has_active=has_active)


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
        type_id=ship['type_id'],
        category=ship['category'],
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
    outstanding_credit_line = models.get_outstanding_credit_line_balance_for_user(order['user_id'])

    time_to_goal = interest.estimate_time_to_goal(order, balance_info)
    if time_to_goal.get('days') is not None:
        from datetime import date, timedelta
        target = date.today() + timedelta(days=int(round(time_to_goal['days'])))
        time_to_goal['target_date'] = target.strftime('%b %d, %Y')

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

    outstanding = models.get_outstanding_credit_line_balance_for_user(order['user_id'])
    if outstanding > 0:
        flash(
            f'You have {outstanding:,.2f} ISK outstanding on a credit line collateralized '
            f'by your savings. Pay off the credit line before requesting a withdrawal.',
            'warning'
        )
        return redirect(url_for('order_detail', order_id=order_id))

    models.update_order_status(order_id, 'withdrawal_pending')
    flash('Withdrawal request submitted. Waiting for admin approval.', 'info')
    return redirect(url_for('order_detail', order_id=order_id))


@app.route('/order/<int:order_id>/toggle-public', methods=['POST'])
@login_required
def toggle_order_public(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['user_id'] != session['user_id']:
        abort(403)
    if order['status'] != 'active':
        flash('Only active savings goals can be toggled.', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))

    is_public = request.form.get('is_public') == '1'
    models.toggle_order_public(order_id, is_public)

    if is_public:
        flash('Your ship goal is now visible on the leaderboard.', 'info')
    else:
        flash('Your ship goal is now hidden from the leaderboard.', 'info')
    return redirect(url_for('order_detail', order_id=order_id))


@app.route('/leaderboard')
@login_required
def leaderboard():
    entries = models.get_leaderboard()
    badge_rows = models.get_completed_badges_for_active_users()
    badges = {}
    for row in badge_rows:
        badges.setdefault(row['character_name'], []).append({
            'ship_name': row['ship_name'],
            'type_id': row['type_id'],
            'category': row['category'],
        })
    return render_template('leaderboard.html', entries=entries, badges=badges)


@app.route('/notifications')
@login_required
def notifications():
    notifs = models.get_recent_notifications(session['user_id'], limit=50)
    models.mark_notifications_read(session['user_id'])
    return render_template('notifications.html', notifications=notifs)


# --- Member: Loans ---

@app.route('/loan/<int:loan_id>')
@login_required
def loan_detail(loan_id):
    loan = models.get_loan(loan_id)
    if not loan:
        abort(404)
    if loan['user_id'] != session['user_id'] and not session.get('is_admin'):
        abort(403)

    pending = None
    if loan['status'] == 'active':
        pending = interest.calculate_loan_pending_interest(loan)

    payments = models.get_loan_payments(loan_id)
    interest_logs = models.get_loan_interest_logs(loan_id)
    owner = models.get_user_by_id(loan['user_id'])

    settings = models.get_interest_settings()
    loan_settings = models.get_loan_settings()
    if loan['product_type'] == 'credit_line':
        rate = settings['interest_rate']
    else:
        rate = loan_settings['general_loan_rate']

    return render_template(
        'loan_detail.html',
        loan=loan,
        pending=pending,
        payments=payments,
        interest_logs=interest_logs,
        owner=owner,
        rate=rate,
        period=settings['interest_period'],
    )


@app.route('/loan/request-draw', methods=['POST'])
@login_required
def request_credit_line_draw():
    user_id = session['user_id']
    if models.get_open_loan_for_user(user_id):
        flash('You already have an open loan. Pay it off before requesting another.', 'warning')
        return redirect(url_for('dashboard'))

    amount = request.form.get('amount', type=float)
    if not amount or amount <= 0:
        flash('Please enter a valid draw amount.', 'danger')
        return redirect(url_for('dashboard'))

    savings_balance = models.get_total_savings_balance_for_user(user_id)
    if savings_balance <= 0:
        flash('You need a positive savings balance to draw a credit line.', 'warning')
        return redirect(url_for('dashboard'))
    if amount > savings_balance:
        flash(f'Draw amount cannot exceed your savings balance of {savings_balance:,.2f} ISK.', 'danger')
        return redirect(url_for('dashboard'))

    loan_id = models.create_loan(
        user_id=user_id,
        product_type='credit_line',
        amount=amount,
        status='pending_disbursement',
    )
    flash(f'Credit line draw of {amount:,.2f} ISK requested. Awaiting admin disbursement.', 'success')
    return redirect(url_for('loan_detail', loan_id=loan_id))


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
    affiliate = models.get_affiliate_settings()

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
        affiliate=affiliate,
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
    categories = models.get_catalog_categories()
    return render_template('admin/catalog.html', ships=ships, categories=categories)


@app.route('/admin/catalog/add', methods=['POST'])
@admin_required
def admin_catalog_add():
    ship_name = request.form.get('ship_name', '').strip()
    price = request.form.get('price', type=float)
    description = request.form.get('description', '').strip() or None
    category = request.form.get('category', '').strip() or 'Uncategorized'

    if not ship_name or not price or price <= 0:
        flash('Please provide a valid ship name and price.', 'danger')
        return redirect(url_for('admin_catalog'))

    # Auto-lookup EVE type ID for ship image
    type_id = esi.search_type_id(ship_name)
    if not type_id:
        flash(f'Could not find "{ship_name}" in EVE database. Ship added without image.', 'warning')

    models.add_catalog_ship(ship_name, price, description, type_id=type_id, category=category)
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
    category = request.form.get('category', '').strip() or 'Uncategorized'

    if not ship_name or not price or price <= 0:
        flash('Please provide a valid ship name and price.', 'danger')
        return redirect(url_for('admin_catalog'))

    # Re-lookup type_id if ship name changed, otherwise keep existing
    type_id = ship['type_id']
    if ship_name.lower() != ship['ship_name'].lower():
        type_id = esi.search_type_id(ship_name)
        if not type_id:
            flash(f'Could not find "{ship_name}" in EVE database. Image removed.', 'warning')

    models.update_catalog_ship(ship_id, ship_name, price, description, is_available, type_id=type_id, category=category)
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


@app.route('/admin/catalog/<int:ship_id>/refresh-image', methods=['POST'])
@admin_required
def admin_catalog_refresh_image(ship_id):
    ship = models.get_catalog_ship(ship_id)
    if not ship:
        abort(404)
    type_id = esi.search_type_id(ship['ship_name'])
    if type_id:
        models.update_catalog_ship(
            ship_id, ship['ship_name'], ship['price'],
            ship['description'], ship['is_available'], type_id=type_id,
            category=ship['category'] or 'Uncategorized'
        )
        flash(f'Image found for {ship["ship_name"]}!', 'success')
    else:
        flash(f'Could not find "{ship["ship_name"]}" in EVE database. Try checking the spelling.', 'warning')
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
        type_id = esi.search_type_id(ship_name)
        # Try to find category from catalog
        catalog_ship = None
        for s in models.get_all_catalog():
            if s['ship_name'].lower() == ship_name.lower():
                catalog_ship = s
                break
        category = catalog_ship['category'] if catalog_ship else None
        order_id = models.create_order(user_id, ship_name, goal_price, notes, status='active', type_id=type_id, category=category)
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
    categories = models.get_catalog_categories()
    outstanding_credit_line = models.get_outstanding_credit_line_balance_for_user(order['user_id'])

    time_to_goal = interest.estimate_time_to_goal(order, balance_info)
    if time_to_goal.get('days') is not None:
        from datetime import date, timedelta
        target = date.today() + timedelta(days=int(round(time_to_goal['days'])))
        time_to_goal['target_date'] = target.strftime('%b %d, %Y')

    return render_template(
        'admin/order_detail.html',
        order=order,
        balance=balance_info,
        deposits=deposits,
        interest_logs=interest_logs,
        owner=user,
        categories=categories,
        outstanding_credit_line=outstanding_credit_line,
        time_to_goal=time_to_goal,
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
    models.create_notification(
        user_id=order['user_id'],
        notification_type='order_approved',
        message=f'Your savings goal for {order["ship_name"]} has been approved! '
                f'Send ISK to Bernie May Doff to start saving.',
        order_id=order_id
    )
    flash(
        f"Savings goal approved for {user['character_name']} - {order['ship_name']}. "
        f"They can now send ISK to Bernie May Doff to start saving.",
        'success'
    )
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
    models.create_notification(
        user_id=order['user_id'],
        notification_type='order_rejected',
        message=f'Your savings goal request for {order["ship_name"]} was not approved.',
        order_id=order_id
    )
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
    models.create_notification(
        user_id=order['user_id'],
        notification_type='deposit_recorded',
        message=f'{amount:,.2f} ISK has been deposited to your {order["ship_name"]} goal.',
        order_id=order_id
    )
    flash(f'Deposit of {amount:,.2f} ISK recorded.', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/order/<int:order_id>/edit', methods=['POST'])
@admin_required
def admin_edit_order(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)

    ship_name = request.form.get('ship_name', '').strip()
    goal_price = request.form.get('goal_price', type=float)
    is_public = request.form.get('is_public') == '1'
    category = request.form.get('category', '').strip() or None

    if not ship_name or not goal_price or goal_price <= 0:
        flash('Please provide a valid ship name and goal price.', 'danger')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    # Re-lookup type_id if ship name changed
    type_id = order['type_id']
    if ship_name.lower() != order['ship_name'].lower():
        type_id = esi.search_type_id(ship_name)
        if not type_id:
            flash(f'Could not find "{ship_name}" in EVE database. Image removed.', 'warning')

    models.update_order_details(order_id, ship_name, goal_price, is_public, type_id=type_id, category=category)
    flash(f'Order updated.', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/order/<int:order_id>/cancel', methods=['POST'])
@admin_required
def admin_cancel_order(order_id):
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['status'] not in ('active', 'withdrawal_pending', 'pending_approval'):
        flash('This order cannot be cancelled.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    if order['status'] in ('active', 'withdrawal_pending'):
        outstanding = models.get_outstanding_credit_line_balance_for_user(order['user_id'])
        if outstanding > 0:
            flash(
                f'Cannot cancel: borrower has {outstanding:,.2f} ISK outstanding on a credit line '
                f'collateralized by this savings. Settle the credit line first.',
                'danger'
            )
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

    outstanding = models.get_outstanding_credit_line_balance_for_user(order['user_id'])
    if outstanding > 0:
        flash(
            f'Cannot approve withdrawal: borrower has {outstanding:,.2f} ISK outstanding on a '
            f'credit line collateralized by this savings. Settle the credit line first.',
            'danger'
        )
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.update_order_status(order_id, 'withdrawn')
    balance = order['amount_deposited'] + order['interest_earned']
    user = models.get_user_by_id(order['user_id'])
    models.create_notification(
        user_id=order['user_id'],
        notification_type='withdrawal_approved',
        message=f'Your withdrawal request for {order["ship_name"]} has been approved. '
                f'{balance:,.2f} ISK will be sent in-game.',
        order_id=order_id
    )
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
    models.create_notification(
        user_id=order['user_id'],
        notification_type='withdrawal_denied',
        message=f'Your withdrawal request for {order["ship_name"]} was denied. '
                f'Your savings goal is still active.',
        order_id=order_id
    )
    flash('Withdrawal request denied. Savings goal is active again.', 'info')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/order/<int:order_id>/refresh-ship-data', methods=['POST'])
@admin_required
def admin_order_refresh_ship_data(order_id):
    """Re-look-up type_id (via Fuzzwork) and fill category from catalog for an order.
    Used to fix older orders that pre-date type_id wiring so their badges render."""
    order = models.get_order(order_id)
    if not order:
        abort(404)

    type_id = esi.search_type_id(order['ship_name'])
    category = order['category']
    if not category:
        catalog_match = database.get_db().execute(
            "SELECT category FROM ship_catalog WHERE ship_name = ? AND category IS NOT NULL LIMIT 1",
            (order['ship_name'],)
        ).fetchone()
        if catalog_match:
            category = catalog_match['category']

    if type_id is None and category == order['category']:
        flash(
            f'Could not refresh ship data for "{order["ship_name"]}" — '
            f'Fuzzwork lookup failed. Check the spelling.',
            'warning'
        )
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.update_order_details(
        order_id,
        order['ship_name'],
        order['goal_price'],
        order['is_public'],
        type_id=type_id if type_id is not None else order['type_id'],
        category=category,
    )
    flash(f'Ship data refreshed for {order["ship_name"]}.', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/order/<int:order_id>/complete-paid-directly', methods=['POST'])
@admin_required
def admin_complete_paid_directly(order_id):
    """Danger zone: admin marks a goal as completed because the user was paid
    out their balance directly (outside the wallet)."""
    order = models.get_order(order_id)
    if not order:
        abort(404)
    if order['status'] not in ('active', 'withdrawal_pending'):
        flash('Only active or withdrawal-pending goals can be marked completed.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))

    outstanding = models.get_outstanding_credit_line_balance_for_user(order['user_id'])
    if outstanding > 0:
        flash(
            f'Cannot mark complete: borrower has {outstanding:,.2f} ISK outstanding on a credit '
            f'line collateralized by this savings. Settle the credit line first.',
            'danger'
        )
        return redirect(url_for('admin_order_detail', order_id=order_id))

    models.update_order_status(order_id, 'completed')
    models.create_notification(
        user_id=order['user_id'],
        notification_type='goal_completed',
        message=f'Your savings goal for {order["ship_name"]} has been marked complete '
                f'by the admin (direct payout).',
        order_id=order_id,
    )
    flash(f'Goal for {order["ship_name"]} marked as completed (direct payout).', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


# --- Admin: User interest pause ---

@app.route('/admin/user/<int:user_id>/toggle-interest-pause', methods=['POST'])
@admin_required
def admin_toggle_user_interest_pause(user_id):
    user = models.get_user_by_id(user_id)
    if not user:
        abort(404)
    paused = request.form.get('paused') == '1'
    models.set_user_interest_paused(user_id, paused)
    if paused:
        flash(f'Interest accrual paused for {user["character_name"]}.', 'info')
    else:
        flash(f'Interest accrual resumed for {user["character_name"]}.', 'success')
    return redirect(request.referrer or url_for('admin_users'))


# --- Admin: Loans ---

@app.route('/admin/loans')
@admin_required
def admin_loans():
    pending_loans = models.get_pending_disbursement_loans()
    active_loans = models.get_active_loans()
    all_loans = models.get_all_loans()
    users = models.get_all_users()
    loan_settings = models.get_loan_settings()
    settings = models.get_interest_settings()
    return render_template(
        'admin/loans.html',
        pending_loans=pending_loans,
        active_loans=active_loans,
        all_loans=all_loans,
        users=users,
        loan_settings=loan_settings,
        settings=settings,
    )


@app.route('/admin/loan/<int:loan_id>')
@admin_required
def admin_loan_detail(loan_id):
    loan = models.get_loan(loan_id)
    if not loan:
        abort(404)
    pending = None
    if loan['status'] == 'active':
        pending = interest.calculate_loan_pending_interest(loan)
    payments = models.get_loan_payments(loan_id)
    interest_logs = models.get_loan_interest_logs(loan_id)
    owner = models.get_user_by_id(loan['user_id'])
    settings = models.get_interest_settings()
    loan_settings = models.get_loan_settings()
    if loan['product_type'] == 'credit_line':
        rate = settings['interest_rate']
    else:
        rate = loan_settings['general_loan_rate']
    return render_template(
        'admin/loan_detail.html',
        loan=loan,
        pending=pending,
        payments=payments,
        interest_logs=interest_logs,
        owner=owner,
        rate=rate,
        period=settings['interest_period'],
    )


@app.route('/admin/loan/new', methods=['POST'])
@admin_required
def admin_create_general_loan():
    user_id = request.form.get('user_id', type=int)
    amount = request.form.get('amount', type=float)
    if not user_id or not amount or amount <= 0:
        flash('Please select a member and enter a valid amount.', 'danger')
        return redirect(url_for('admin_loans'))

    user = models.get_user_by_id(user_id)
    if not user:
        flash('Member not found.', 'danger')
        return redirect(url_for('admin_loans'))

    if models.get_open_loan_for_user(user_id):
        flash(f'{user["character_name"]} already has an open loan. '
              f'They must pay it off first.', 'warning')
        return redirect(url_for('admin_loans'))

    loan_id = models.create_loan(
        user_id=user_id,
        product_type='general',
        amount=amount,
        status='active',
    )
    models.create_notification(
        user_id=user_id,
        notification_type='loan_disbursed',
        message=f'A general loan of {amount:,.2f} ISK has been issued to you. '
                f'Send ISK to the corp wallet to repay.',
    )
    flash(f'General loan of {amount:,.2f} ISK created for {user["character_name"]}. '
          f'Send ISK in-game.', 'success')
    return redirect(url_for('admin_loan_detail', loan_id=loan_id))


@app.route('/admin/loan/<int:loan_id>/disburse', methods=['POST'])
@admin_required
def admin_disburse_loan(loan_id):
    loan = models.get_loan(loan_id)
    if not loan:
        abort(404)
    if loan['status'] != 'pending_disbursement':
        flash('This loan is not pending disbursement.', 'warning')
        return redirect(url_for('admin_loan_detail', loan_id=loan_id))

    models.mark_loan_disbursed(loan_id)
    models.create_notification(
        user_id=loan['user_id'],
        notification_type='loan_disbursed',
        message=f'Your credit line draw of {loan["principal"]:,.2f} ISK has been disbursed. '
                f'Collateral is now frozen on your savings.',
    )
    flash(f'Loan #{loan_id} marked as disbursed.', 'success')
    return redirect(url_for('admin_loan_detail', loan_id=loan_id))


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


@app.route('/admin/loan/<int:loan_id>/toggle-interest-pause', methods=['POST'])
@admin_required
def admin_toggle_loan_interest_pause(loan_id):
    loan = models.get_loan(loan_id)
    if not loan:
        abort(404)
    paused = request.form.get('paused') == '1'
    models.set_loan_interest_paused(loan_id, paused)
    if paused:
        flash(f'Interest accrual paused on loan #{loan_id}.', 'info')
    else:
        flash(f'Interest accrual resumed on loan #{loan_id}.', 'success')
    return redirect(url_for('admin_loan_detail', loan_id=loan_id))


@app.route('/admin/loan/<int:loan_id>/manual-payment', methods=['POST'])
@admin_required
def admin_loan_manual_payment(loan_id):
    loan = models.get_loan(loan_id)
    if not loan:
        abort(404)
    if loan['status'] != 'active':
        flash('Can only record payments on active loans.', 'warning')
        return redirect(url_for('admin_loan_detail', loan_id=loan_id))

    amount = request.form.get('amount', type=float)
    note = request.form.get('note', '').strip() or None
    if not amount or amount <= 0:
        flash('Please enter a valid payment amount.', 'danger')
        return redirect(url_for('admin_loan_detail', loan_id=loan_id))

    # Accrue first so the borrower pays the up-to-date balance
    interest.accrue_interest_for_loan(loan_id)
    loan = models.get_loan(loan_id)
    if loan['status'] != 'active':
        flash('Loan is no longer active after accrual; payment not applied.', 'warning')
        return redirect(url_for('admin_loan_detail', loan_id=loan_id))

    result = models.record_loan_payment(
        loan_id=loan_id,
        amount=amount,
        source='manual',
        recorded_by=session['user_id'],
        note=note,
    )
    models.create_notification(
        user_id=loan['user_id'],
        notification_type='loan_payment_recorded',
        message=f'{result["applied"]:,.2f} ISK applied to your loan (manual). '
                f'Remaining balance: {result["new_balance"]:,.2f} ISK.',
    )
    if result['paid_in_full']:
        models.create_notification(
            user_id=loan['user_id'],
            notification_type='loan_paid_in_full',
            message='Your loan has been paid in full. Frozen savings collateral is released.',
        )
    msg = f'Recorded {result["applied"]:,.2f} ISK manual payment.'
    if result['remainder'] > 0:
        msg += f' {result["remainder"]:,.2f} ISK exceeded balance (no overpayment recorded).'
    flash(msg, 'success')
    return redirect(url_for('admin_loan_detail', loan_id=loan_id))


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
    models.create_notification(
        user_id=order['user_id'],
        notification_type='deposit_recorded',
        message=f'{entry["amount"]:,.2f} ISK has been deposited to your {order["ship_name"]} goal.',
        order_id=order_id
    )
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
        # Interest settings (only when that form is submitted)
        if 'interest_rate' in request.form:
            rate = request.form.get('interest_rate', type=float)
            period = request.form.get('interest_period', '')

            if rate is None or rate < 0 or rate > 1:
                flash('Interest rate must be between 0 and 1 (e.g. 0.05 for 5%).', 'danger')
            elif period not in ('daily', 'weekly', 'biweekly', 'monthly'):
                flash('Invalid interest period.', 'danger')
            else:
                models.set_setting('interest_rate', str(rate))
                models.set_setting('interest_period', period)
                flash('Settings updated.', 'success')

        # Loan settings (only when that form is submitted)
        if 'general_loan_rate' in request.form:
            loan_rate = request.form.get('general_loan_rate', type=float)
            if loan_rate is None or loan_rate < 0 or loan_rate > 1:
                flash('General loan rate must be between 0 and 1 (e.g. 0.125 for 12.5%).', 'danger')
            else:
                models.set_setting('general_loan_rate', str(loan_rate))
                flash('Loan settings updated.', 'success')

        # Affiliate settings (only when that form is submitted)
        if 'usd_to_isk_ratio' in request.form:
            ratio = request.form.get('usd_to_isk_ratio', type=float)
            if ratio is None or ratio <= 0:
                flash('USD to ISK ratio must be greater than 0.', 'danger')
            else:
                models.set_setting('usd_to_isk_ratio', str(ratio))
                flash('Affiliate settings updated.', 'success')

        return redirect(url_for('admin_settings'))

    settings = models.get_interest_settings()
    loan_settings = models.get_loan_settings()
    affiliate = models.get_affiliate_settings()
    return render_template(
        'admin/settings.html',
        settings=settings,
        loan_settings=loan_settings,
        affiliate=affiliate,
    )


# --- Admin: Affiliate Distribution ---

@app.route('/admin/distribute-affiliate', methods=['POST'])
@admin_required
def admin_distribute_affiliate():
    import math

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

    # Give remainder to the largest account
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
            note='Savings Boost',
            source='affiliate',
        )
        models.create_notification(
            user_id=order['user_id'],
            notification_type='deposit_recorded',
            message=f'{share:,.2f} ISK Savings Boost deposited to your {order["ship_name"]} goal.',
            order_id=order['id'],
        )
        count += 1

    flash(
        f'Distributed {total_isk:,.0f} ISK (${dollars:.2f}) across {count} account(s).',
        'success',
    )
    return redirect(url_for('admin_dashboard'))


# --- Error handlers ---

@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', code=403, message='Access denied.'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Page not found.'), 404


if __name__ == '__main__':
    app.run(debug=True)
