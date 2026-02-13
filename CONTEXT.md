# Sihcom Savings and Loans - Project Context

## What This Is
A web app for Eve Online that lets corp members deposit ISK toward buying ships. Deposits earn compound interest in the member's favor (like a savings account). When deposits + interest reach the ship price, the goal is met and the admin delivers the ship.

## Tech Stack
- **Flask** (Python) with Jinja2 templates
- **Preston** library (`pip install preston`) for Eve Online ESI SSO authentication
- **SQLite** via Python's built-in `sqlite3` (no ORM)
- **Bootstrap 5** dark theme via CDN
- **Gunicorn** for production WSGI
- **Railway** for deployment (https://sihcom-savings-and-loans.up.railway.app/)
- **GitHub**: https://github.com/sihcomrepinuj/Sihcom-Savings-and-Loans

## Key Business Rules
- Interest goes IN FAVOR of the member (savings account, not a loan)
- Compound interest, configurable global rate and period (weekly/biweekly/monthly)
- **30-day deposit lag**: New deposits do NOT earn interest until 30 days after deposit date. Interest accrues on "eligible balance" (deposits older than 30 days + all accrued interest). All deposits still count toward goal progress immediately.
- Members can only have ONE active or pending goal at a time
- Members pick ships from an admin-curated catalog; requests require admin approval
- **Ship catalog has categories** (e.g., "Titans", "Supers") - ships grouped by category on both member and admin catalog pages
- Members can request full withdrawal (admin approves/denies, cancels entire goal)
- **Leaderboard visibility**: Members can toggle whether their ship goal name is shown on the leaderboard (default: private). Private goals show a ❓ icon instead of the ship name. Admin can also toggle this via order editing.
- Members see only their own goals (private)
- Admin character is "Bernie May Doff" - also the bank character for wallet sync
- Deposits come in via automatic wallet journal sync OR manual admin entry
- **In-app notifications**: Users receive persistent notifications for key events (goal approved/rejected, deposits, interest accrual, goal completion, withdrawal decisions). Badge count shown in navbar, marked read when viewed.

## Files Overview

### Core Python
- **config.py** - Config class reading from env vars (SECRET_KEY, EVE_CLIENT_ID, EVE_CLIENT_SECRET, EVE_CALLBACK_URL, ADMIN_CHARACTER_ID, DATA_DIR)
- **database.py** - SQLite schema (8 tables: users, ship_catalog, ship_orders, deposits, interest_log, wallet_journal, settings, notifications), Flask g-based connections, Row factory, migration via `_try_alter()`
- **models.py** - All CRUD: users, catalog, orders, deposits, wallet journal, settings, notifications. Key functions: `get_or_create_user()`, `record_deposit()` (auto-checks goal completion), `user_has_active_or_pending_order()`, `get_leaderboard()` (returns ship_name + is_public), `toggle_order_public()`, `update_order_details()`, `create_notification()`, `get_unread_count()`, `mark_notifications_read()`
- **interest.py** - `calculate_current_balance()`, `accrue_interest_for_order()`, `accrue_interest_all()`, `_get_eligible_deposits()`. Uses PERIOD_DAYS dict. Interest accrues only on deposits older than 30 days (eligible balance).
- **wallet.py** - ESI wallet sync: `_get_bank_preston()`, `fetch_wallet_journal()`, `sync_wallet()`. Filters for `player_donation` with `amount > 0`, deduplicates via journal_id, auto-matches to users with active orders
- **esi.py** - Public ESI helper: `search_type_id()` for ship name→type_id lookup, `get_ship_image_url()` for EVE image server URLs
- **app.py** - Flask app with 30+ routes, two Preston instances (member: no scope, admin: wallet scope), ProxyFix for Railway, `isk_short` and `ship_image` template filters, context processor for notification badge count, logging on callback

### Templates (all in templates/)
- **base.html** - Bootstrap 5 dark theme, nav with Ship Catalog, Leaderboard links, notification bell with unread badge, and Admin dropdown
- **index.html** - Landing page with EVE SSO login button
- **error.html** - 403/404 error pages
- **dashboard.html** - Member dashboard showing goals with progress bars, deposit instructions, leaderboard visibility form-switch toggle on active cards, contrast-fixed
- **catalog.html** - Member ship catalog browser grouped by category with "Start Saving" buttons
- **order_detail.html** - Member order detail with deposit history, source badges, "How to Deposit" sidebar card, and leaderboard visibility form-switch toggle
- **leaderboard.html** - Leaderboard showing character names, Goal column (public goals show ship name, private show ❓), and progress bars with teal-to-cyan HSL gradient and progressive glow effect above 60% (no ISK amounts)
- **notifications.html** - Persistent notifications page; unread highlighted with border-info, links to relevant orders
- **admin/dashboard.html** - Admin dashboard with 6 stat cards, pending approvals, withdrawal requests, all orders table
- **admin/catalog.html** - Admin catalog management with inline edit forms, category field, grouped by category
- **admin/create_order.html** - Admin manual order creation
- **admin/order_detail.html** - Admin order detail with deposit form, accrue interest, approve/reject, Edit Order sidebar (ship name, goal price, leaderboard visibility)
- **admin/unmatched.html** - Unmatched wallet transactions with assign/ignore
- **admin/settings.html** - Global interest rate/period config
- **admin/users.html** - Registered users list

### Deployment
- **Procfile** - `web: gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 1` (single worker required for Flask sessions)
- **requirements.txt** - flask>=3.0, preston>=4.12, gunicorn>=22.0
- **runtime.txt** - python-3.13.1
- **.gitattributes** - `* text=auto` for line ending normalization

## Preston Library Notes
- `whoami()` returns **lowercase** keys: `character_id`, `character_name` (NOT `CharacterID`)
- `authenticate(code)` returns a new Preston instance with `.refresh_token` attribute
- `get_authorize_url(state=state)` accepts a state parameter
- ESI scope: `esi-wallet.read_character_wallet.v1` (admin only; regular members get no scope)
- Two Preston instances in app.py: `member_preston` (no scope) and `admin_preston_base` (wallet scope)
- Login route uses `?admin=1` query param to trigger admin login flow
- `get_or_create_user()` only updates refresh_token if one is provided (prevents member login from wiping admin token)

## Railway Deployment Details
- App URL: https://sihcom-savings-and-loans.up.railway.app/
- Persistent volume mounted for SQLite (DATA_DIR=/data)
- ProxyFix enabled via RAILWAY_ENVIRONMENT_NAME auto-detection
- SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE=Lax
- Single gunicorn worker (required - multiple workers break Flask's in-memory sessions)

### Railway Env Vars Required
- FLASK_SECRET_KEY
- EVE_CLIENT_ID
- EVE_CLIENT_SECRET
- EVE_CALLBACK_URL (https://sihcom-savings-and-loans.up.railway.app/callback)
- ADMIN_CHARACTER_ID (Bernie May Doff's character ID)
- DATA_DIR (/data)

## Database Schema (8 tables)
1. **users** - id, character_id (unique), character_name, is_admin, refresh_token, created_at
2. **ship_catalog** - id, ship_name, price, description, is_available, type_id, category, created_at
3. **ship_orders** - id, user_id, ship_name, goal_price, amount_deposited, interest_earned, status, notes, type_id, is_public, created_at, updated_at
4. **deposits** - id, order_id, amount, recorded_by, note, source (manual/wallet), journal_id, deposit_date, created_at
5. **interest_log** - id, order_id, amount, balance_before, balance_after, accrued_at
6. **wallet_journal** - journal_id (PK, from ESI), sender_id, sender_name, amount, reason, journal_date, order_id, status (unmatched/matched/ignored), created_at
7. **settings** - key (PK), value
8. **notifications** - id, user_id, order_id, type, message, is_read, created_at

## Order Statuses
- `pending_approval` - member requested from catalog, awaiting admin
- `active` - approved, accepting deposits
- `withdrawal_pending` - member requested withdrawal, awaiting admin
- `completed` - deposits + interest reached goal_price
- `withdrawn` - admin approved withdrawal
- `cancelled` - admin rejected or cancelled

## Known Issues / Design Decisions
- SQLite doesn't support `ALTER TABLE ADD COLUMN IF NOT EXISTS` - solved with `_try_alter()` helper
- config.py is committed to git (no secrets, reads from env vars) - was previously gitignored which broke Railway deploy
- Dark theme contrast was low on several pages - fixed with white text classes and CSS overrides
- EVE Developer Portal callback URL must exactly match the Railway env var EVE_CALLBACK_URL
- Leaderboard progress bars use Jinja-computed HSL values (hue 180, dynamic saturation/lightness) with CSS `.progress-glow` class for overflow-visible box-shadow glow

## What Could Be Added Next
- Automatic scheduled wallet syncing (currently manual button press)
- Email/Discord notifications (in addition to in-app notifications)
- Multiple goals per member
- Partial withdrawals
- Audit log for admin actions
- Test suite (no tests currently exist)
