import sqlite3
from flask import g
from config import Config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id    INTEGER UNIQUE NOT NULL,
    character_name  TEXT NOT NULL,
    refresh_token   TEXT,
    is_admin        INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ship_catalog (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ship_name       TEXT NOT NULL,
    price           REAL NOT NULL,
    description     TEXT,
    is_available    INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ship_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    ship_name       TEXT NOT NULL,
    goal_price      REAL NOT NULL,
    amount_deposited REAL NOT NULL DEFAULT 0.0,
    interest_earned REAL NOT NULL DEFAULT 0.0,
    status          TEXT NOT NULL DEFAULT 'pending_approval',
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS deposits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL,
    amount          REAL NOT NULL,
    recorded_by     INTEGER,
    note            TEXT,
    source          TEXT NOT NULL DEFAULT 'manual',
    journal_id      INTEGER,
    deposit_date    TEXT DEFAULT (datetime('now')),
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (order_id) REFERENCES ship_orders(id),
    FOREIGN KEY (recorded_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS interest_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL,
    amount          REAL NOT NULL,
    balance_before  REAL NOT NULL,
    balance_after   REAL NOT NULL,
    accrued_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (order_id) REFERENCES ship_orders(id)
);

CREATE TABLE IF NOT EXISTS wallet_journal (
    journal_id      INTEGER PRIMARY KEY,
    sender_id       INTEGER NOT NULL,
    sender_name     TEXT NOT NULL,
    amount          REAL NOT NULL,
    reason          TEXT,
    journal_date    TEXT NOT NULL,
    order_id        INTEGER,
    status          TEXT NOT NULL DEFAULT 'unmatched',
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (order_id) REFERENCES ship_orders(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    order_id    INTEGER,
    type        TEXT NOT NULL,
    message     TEXT NOT NULL,
    is_read     INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (order_id) REFERENCES ship_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_read);

CREATE INDEX IF NOT EXISTS idx_orders_user_id ON ship_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON ship_orders(status);
CREATE INDEX IF NOT EXISTS idx_deposits_order_id ON deposits(order_id);
CREATE INDEX IF NOT EXISTS idx_interest_log_order_id ON interest_log(order_id);
CREATE INDEX IF NOT EXISTS idx_wallet_journal_status ON wallet_journal(status);
CREATE INDEX IF NOT EXISTS idx_wallet_journal_sender ON wallet_journal(sender_id);
CREATE INDEX IF NOT EXISTS idx_catalog_available ON ship_catalog(is_available);
"""

# Migration SQL for existing databases that don't have the new columns/tables
MIGRATION_SQL = """
-- Add source and journal_id columns to deposits if they don't exist
-- SQLite doesn't support IF NOT EXISTS for ALTER TABLE, so we handle errors in code
"""

DEFAULT_SETTINGS = {
    'interest_rate': '0.05',
    'interest_period': 'monthly',
    'usd_to_isk_ratio': '1000000000',
}


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(Config.DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _try_alter(db, sql):
    """Try to run an ALTER TABLE statement, ignoring 'duplicate column' errors."""
    try:
        db.execute(sql)
    except sqlite3.OperationalError as e:
        if 'duplicate column' not in str(e).lower():
            raise


def init_db():
    db = sqlite3.connect(Config.DATABASE_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA_SQL)

    # Migrate existing deposits table if needed
    _try_alter(db, "ALTER TABLE deposits ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
    _try_alter(db, "ALTER TABLE deposits ADD COLUMN journal_id INTEGER")

    # Add type_id to ship_catalog and ship_orders for ship images
    _try_alter(db, "ALTER TABLE ship_catalog ADD COLUMN type_id INTEGER")
    _try_alter(db, "ALTER TABLE ship_orders ADD COLUMN type_id INTEGER")

    # Add category to ship_catalog for organizing ships (Titans, Supers, etc.)
    _try_alter(db, "ALTER TABLE ship_catalog ADD COLUMN category TEXT DEFAULT 'Uncategorized'")

    # Add is_public to ship_orders for leaderboard visibility toggle
    _try_alter(db, "ALTER TABLE ship_orders ADD COLUMN is_public INTEGER DEFAULT 0")

    for key, value in DEFAULT_SETTINGS.items():
        db.execute(
            'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
            (key, value)
        )
    db.commit()
    db.close()
