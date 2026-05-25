"""Wallet journal sync: polls the bank character's ESI wallet journal
and auto-matches player_donation entries to members' active savings goals."""

from preston import Preston
from config import Config
import models
import database
import interest


# Wallet-journal ref_types that represent ISK arriving in the bank wallet.
# player_donation is a character-to-character transfer; corporation_account_withdrawal
# is a corp director/CEO moving ISK from a corp wallet to the bank character.
PLAYER_DONATION = 'player_donation'
CORP_WITHDRAWAL = 'corporation_account_withdrawal'
INCOMING_REF_TYPES = (PLAYER_DONATION, CORP_WITHDRAWAL)


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

    # Filter: incoming ISK (player donations + corp wallet transfers), positive
    # amount, not already processed. Corp transfers can't be auto-matched (see
    # the loop below) so they fall through to the unmatched bucket.
    donations = [
        e for e in journal
        if e.get('ref_type') in INCOMING_REF_TYPES
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

        # Corp wallet transfers always go to unmatched for manual allocation:
        # first_party_id is the initiating director/CEO, not the intended
        # beneficiary, so auto-matching would credit the wrong member (or even
        # the director, if they happen to be one). Still resolve the name for
        # display, but don't look up an order/loan to match against.
        is_corp_withdrawal = entry.get('ref_type') == CORP_WITHDRAWAL
        sender_user = None if is_corp_withdrawal else models.get_user_by_character_id(sender_id)

        if sender_user:
            sender_name = sender_user['character_name']
        else:
            sender_name = _resolve_character_name(auth, sender_id)

        # Look up the sender's open loan and active goal
        open_loan = None
        active_order = None
        if sender_user:
            open_loan = models.get_open_loan_for_user(sender_user['id'])
            active_order = models.get_active_order_for_user(sender_user['id'])

        # Only loans that are 'active' (disbursed) can receive payments —
        # 'pending_disbursement' loans still owe nothing.
        loan_for_payment = open_loan if (open_loan and open_loan['status'] == 'active') else None

        remainder = amount
        applied_to_loan = 0.0
        applied_to_goal = 0.0

        if loan_for_payment:
            # Accrue any pending interest first so the borrower pays the
            # up-to-date balance, not a stale one.
            interest.accrue_interest_for_loan(loan_for_payment['id'])
            loan_for_payment = models.get_loan(loan_for_payment['id'])
            if loan_for_payment and loan_for_payment['status'] == 'active':
                result = models.record_loan_payment(
                    loan_id=loan_for_payment['id'],
                    amount=remainder,
                    source='wallet',
                    journal_id=journal_id,
                    recorded_by=admin['id'],
                    note=f'Wallet sync: {reason}' if reason else 'Wallet sync',
                )
                applied_to_loan = result['applied']
                remainder = result['remainder']
                if applied_to_loan > 0:
                    models.create_notification(
                        user_id=loan_for_payment['user_id'],
                        notification_type='loan_payment_recorded',
                        message=f'{applied_to_loan:,.2f} ISK applied to your loan '
                                f'via wallet sync. Remaining balance: '
                                f'{result["new_balance"]:,.2f} ISK.',
                    )
                if result['paid_in_full']:
                    models.create_notification(
                        user_id=loan_for_payment['user_id'],
                        notification_type='loan_paid_in_full',
                        message='Your loan has been paid in full. Frozen savings collateral is released.',
                    )

        if remainder > 0 and active_order:
            models.record_deposit(
                order_id=active_order['id'],
                amount=remainder,
                recorded_by_user_id=admin['id'],
                note=f'Wallet sync: {reason}' if reason else 'Wallet sync',
                source='wallet',
                journal_id=journal_id,
            )
            models.create_notification(
                user_id=active_order['user_id'],
                notification_type='deposit_recorded',
                message=f'{remainder:,.2f} ISK has been deposited to your '
                        f'{active_order["ship_name"]} goal via wallet sync.',
                order_id=active_order['id']
            )
            applied_to_goal = remainder
            remainder = 0

        if applied_to_loan > 0 or applied_to_goal > 0:
            matched_order_id = active_order['id'] if applied_to_goal > 0 else None
            models.insert_journal_entry(
                journal_id=journal_id,
                sender_id=sender_id,
                sender_name=sender_name,
                amount=amount,
                reason=reason,
                journal_date=journal_date,
                order_id=matched_order_id,
                status='matched',
            )
            matched_count += 1
            matched_isk += amount
        else:
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
