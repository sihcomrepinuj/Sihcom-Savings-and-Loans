# Loans + Adjacent Admin Tools — Design

## Context

The Sihcom app has shipped savings successfully and users are happy. The next phase delivers the missing half of the app's name — **loans** — plus two small admin quality-of-life features that touch the same code paths. Loans is the marquee feature; the admin tools (Complete Goal, Pause Interest) are folded in to avoid re-touching the same admin pages and interest-accrual code twice.

The bank-website UI redesign, bonds, and leaderboard polish are explicitly deferred to future sessions.

## Loan products

Two products with one important shared rule: **a member can hold at most one loan at a time**, of either type. A savings goal can coexist with a loan.

### Credit line (member-requested, admin-disbursed)

- **Eligibility:** any member with a positive savings balance (sum of active goals' `amount_deposited + interest_earned`).
- **Max draw:** 100% of current savings balance at the moment of the draw.
- **Rate:** equal to the current savings rate (`settings.interest_rate`), compounding on the same period (`settings.interest_period`). No new rate setting.
- **Collateral:** the draw amount is "frozen" — interest stops accruing on that portion of savings. The active (non-frozen) portion keeps growing as normal. As the loan is repaid, collateral is released pro-rata.
- **Flow:**
  1. Member with positive savings clicks **Request Credit Line Draw**, enters an amount.
  2. Loan record created in `pending_disbursement` status; admin notified.
  3. Admin opens the request, sends ISK in EVE, clicks **Mark Disbursed**.
  4. Loan flips to `active`; collateral is frozen on the savings side.

### General loan (admin-originated end-to-end)

- **Eligibility:** invite-only — admin picks who gets one. No member-side request flow.
- **Rate:** 12.5% per period (new `general_loan_rate` setting, default `12.5`), compounding on the same period as savings.
- **No collateral.**
- **Flow:**
  1. Admin opens **Create General Loan** form: picks member, enters amount.
  2. Loan record created in `active` status immediately.
  3. Admin sends ISK in EVE manually.

## Shared mechanics

- **Repayment:** open-ended. No maturity date, no installments. Interest accrues until balance hits zero.
- **Wallet auto-match:** incoming ISK from a borrower applies to the outstanding loan balance first; remainder flows to the active savings goal as it does today.
- **Privacy:** loans are entirely private. They do not appear on the leaderboard. No badges, no public notifications, no "borrower" indicators anywhere.
- **Closure:** when the balance hits zero, status flips to `paid_in_full`. The member can immediately open a new product.

## Admin recourse

Minimal, trust-based:

- **Pause interest accrual** — per loan, also per user (see Admin Tools below; the per-user toggle pauses both savings and loan interest for that member).
- **Apply manual payment** — admin can record an off-wallet payment (PLEX, contract, direct hand-off) against a loan or against a savings goal. The savings-side action is the same mechanic as the new **Complete Goal** button.

No collateral liquidation, no write-off, no admin-initiated cancellation. Recovery beyond a pause is handled out-of-band.

## Admin tools (folded in)

- **Complete Goal (paid directly)** — danger-zone action on a goal's admin detail page. Admin clicks when a member has been paid out their balance directly (outside the wallet). Records the payout and closes the goal as completed. Uses the same manual-payment plumbing as **Apply Manual Payment**.
- **Pause Interest** — **per user**, single boolean on the user record. When set, *both* savings interest accrual *and* loan interest accrual skip this user during the next scheduled run. Simpler than per-goal/per-loan toggles and matches the user's mental model ("this person is on hold").

## Data model

New tables:

- **`loans`** — `id`, `user_id`, `product_type` (`credit_line` | `general`), `principal`, `current_balance`, `status` (`pending_disbursement` | `active` | `paid_in_full`), `interest_paused`, `created_at`, `disbursed_at`, `closed_at`. For credit lines, `principal` doubles as the original draw amount used to compute collateral release.
- **`loan_payments`** — `id`, `loan_id`, `amount`, `source` (`wallet` | `manual`), `paid_at`, `journal_id` (nullable; populated for wallet-matched payments).
- **`loan_interest_log`** — `id`, `loan_id`, `amount`, `balance_before`, `balance_after`, `accrued_at`. Mirrors `interest_log` for savings.

Existing-table changes (via `_try_alter()` migration):

- **`users`** — add `interest_paused` BOOLEAN DEFAULT 0.
- **`settings`** — add `general_loan_rate` row (default `12.5`).

## Interest accrual logic changes

The scheduled accrual job (currently iterates savings goals) gets two extensions:

1. **Skip paused users.** Before processing any goal or loan, check `users.interest_paused`. If true, skip every account for that user.
2. **Frozen-collateral handling on savings.** For each goal, compute the user's outstanding credit-line balance. The accrual base is `max(0, goal_balance - outstanding_credit_line_balance)`, then prorate by deposit age as it does today. If the user holds a general loan instead, no change — only credit lines freeze savings.
3. **Loan accrual.** After savings accrual, iterate active loans. Apply rate to `current_balance` (compounding). Credit lines use `settings.interest_rate`; general loans use `settings.general_loan_rate`. Skip loans with `interest_paused = true`.

## Wallet auto-match changes

The existing matcher (which attributes incoming ISK from a member to that member's active goal) gains a precedence rule:

1. If the sender has an active loan with `current_balance > 0`, apply the deposit to the loan first.
2. Any remainder flows to the active goal as today (recorded as a normal deposit with `source = 'wallet'`).
3. Both legs (loan payment + goal deposit) reference the same `journal_id` for audit traceability.

## New pages / UI changes

Members:

- **Dashboard:** new "Loans" section. Shows active loan (if any) with balance, interest accrued, payment history, and a **Request Credit Line Draw** button if eligible.
- **Request Credit Line Draw modal:** amount input, validation against current savings balance.

Admin:

- **Loans admin page:** lists all active loans, pending credit-line requests, recent payments. Per-loan actions: **Mark Disbursed** (credit-line pending), **Pause Interest**, **Apply Manual Payment**.
- **Create General Loan form:** member picker, amount input, submit.
- **User detail page:** add **Pause Interest** toggle.
- **Goal detail (admin):** add **Complete Goal (paid directly)** action in the danger zone; add **Apply Manual Payment** for off-wallet payments.

## Verification

Manual end-to-end checks once implemented:

1. **General loan flow:** admin creates a general loan for a test member → loan visible on member dashboard → interest accrues on the next scheduled run → member sends ISK in EVE → wallet sync matches and applies to loan → balance reaches zero → status flips to `paid_in_full` → member can open a new loan.
2. **Credit line flow:** member with positive savings requests a draw → admin sees pending request → admin marks disbursed → interest stops on frozen portion of savings, accrues on the loan → repayment via wallet draws down both loan and frozen collateral.
3. **Concurrency rule:** with an active loan, the request-draw button and the create-general-loan form refuse to create a second loan.
4. **Privacy:** confirm loans never appear on the leaderboard or in another member's notifications.
5. **Pause interest:** flip the toggle on a user with both an active goal and an active loan → next scheduled accrual run leaves both balances unchanged.
6. **Complete goal (paid directly):** admin closes a goal via the danger zone → goal status becomes `completed`, payout recorded → leaderboard reflects completion as today.
7. **Manual loan payment:** admin records a manual payment → loan balance decreases → if it hits zero, status flips correctly.

## Deferred (not in this design)

- Bank-website UI redesign (visual/IA overhaul; will inform future feature pages).
- Bonds product.
- Leaderboard enhancements.
