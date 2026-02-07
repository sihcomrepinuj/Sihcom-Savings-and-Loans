"""Wallet journal sync: polls the bank character's ESI wallet journal
and auto-matches player_donation entries to members' active savings goals."""

from preston import Preston
from config import Config
import models
import database


def _get_bank_preston():
    """Build an authenticated Preston instance using the admin's stored refresh token."""
    admin = models.get_admin_user()
    if not admin or not admin['refresh_token']:
        return None

    return Preston(
        user_agent=Config.USER_AGENT,
        client_id=Config.EVE_CLIENT_ID,
        client_secret=Config.EVE_CLIENT_SECRET,
        callback_url=Config.EVE_CALLBACK_URL,
        scope='esi-wallet.read_character_wallet.v1',
        refresh_token=admin['refresh_token'],
    )


def _resolve_character_name(auth, character_id):
    """Resolve a character ID to a name via ESI. Returns 'Unknown' on failure."""
    try:
        result = auth.get_op(
            'get_characters_character_id',
            character_id=character_id,
        )
        return result.get('name', 'Unknown')
    except Exception:
        return 'Unknown'


def fetch_wallet_journal(auth, character_id):
    """Fetch all pages of the wallet journal from ESI."""
    all_entries = []
    page = 1
    while True:
        try:
            entries = auth.get_op(
                'get_characters_character_id_wallet_journal',
                character_id=character_id,
                page=page,
            )
        except Exception:
            break
        if not entries:
            break
        all_entries.extend(entries)
        page += 1
    return all_entries


def sync_wallet():
    """Main sync function. Returns a summary dict or None on error.

    Fetches the bank character's wallet journal, filters for player_donation
    entries (ISK received), and for each new entry:
      - If the sender is a registered user with an active order -> auto-match
      - Otherwise -> mark as unmatched for admin review
    """
    auth = _get_bank_preston()
    if auth is None:
        return None

    admin = models.get_admin_user()
    character_id = admin['character_id']

    journal = fetch_wallet_journal(auth, character_id)

    # Filter: player_donation, positive amount (ISK received), not already processed
    donations = [
        e for e in journal
        if e.get('ref_type') == 'player_donation'
        and e.get('amount', 0) > 0
    ]

    matched_count = 0
    matched_isk = 0.0
    unmatched_count = 0

    for entry in donations:
        journal_id = entry['id']

        # Skip if already processed
        if models.journal_entry_exists(journal_id):
            continue

        sender_id = entry.get('first_party_id')
        amount = entry['amount']
        reason = entry.get('reason', '')
        journal_date = entry.get('date', '')

        # Try to find the sender in our users table
        sender_user = models.get_user_by_character_id(sender_id)

        if sender_user:
            sender_name = sender_user['character_name']
        else:
            sender_name = _resolve_character_name(auth, sender_id)

        # Try to match to an active order
        if sender_user:
            active_order = models.get_active_order_for_user(sender_user['id'])
        else:
            active_order = None

        if active_order:
            # Auto-match: create deposit and mark journal entry
            models.record_deposit(
                order_id=active_order['id'],
                amount=amount,
                recorded_by_user_id=admin['id'],
                note=f'Wallet sync: {reason}' if reason else 'Wallet sync',
                source='wallet',
                journal_id=journal_id,
            )
            models.insert_journal_entry(
                journal_id=journal_id,
                sender_id=sender_id,
                sender_name=sender_name,
                amount=amount,
                reason=reason,
                journal_date=journal_date,
                order_id=active_order['id'],
                status='matched',
            )
            matched_count += 1
            matched_isk += amount
        else:
            # Unmatched: store for admin review
            models.insert_journal_entry(
                journal_id=journal_id,
                sender_id=sender_id,
                sender_name=sender_name,
                amount=amount,
                reason=reason,
                journal_date=journal_date,
                order_id=None,
                status='unmatched',
            )
            unmatched_count += 1

    return {
        'matched_count': matched_count,
        'matched_isk': matched_isk,
        'unmatched_count': unmatched_count,
        'total_processed': matched_count + unmatched_count,
    }
