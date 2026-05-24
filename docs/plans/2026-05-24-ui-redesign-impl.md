# Bank-style UI Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Shift the visual aesthetic from Bootstrap 5 dark to a bank-website light theme (Phase 1), then add a public product surface at `/`, `/savings`, `/loans`, `/credit-lines` that doubles as the deferred Terms-of-Service home (Phase 2).

**Architecture:** CSS-variable design system layered on top of Bootstrap. `static/style.css` defines `--sl-*` tokens on `:root` and overrides Bootstrap component colors. `base.html` drops `bg-dark text-light` and `navbar-dark`, adds Google Fonts. Per-template work is mechanical class-swap and color-class swap; no Python code changes in Phase 1. Phase 2 adds four small GET routes and three product page templates that read rates from a new `models.get_current_rates()`.

**Tech Stack:** Flask + Jinja2, Bootstrap 5 (kept for grid/spacing/JS), vanilla CSS variables, Google Fonts CDN (Inter + Source Serif 4).

**Reference:** Design doc at [docs/plans/2026-05-24-ui-redesign-design.md](docs/plans/2026-05-24-ui-redesign-design.md). Token + component preview at [docs/plans/2026-05-24-ui-redesign-preview.html](docs/plans/2026-05-24-ui-redesign-preview.html) — open this in a browser before starting to anchor on the target look.

**Notes for the executor:**
- **No test suite.** This project verifies by booting the Flask dev server and walking the UI in a browser. Each task ends with a manual-verification step describing what to look at, not `pytest` invocations.
- **Commit policy.** The user prefers bundled commits and only commits when asked ([feedback_commit_policy.md](../../../../.claude/projects/C--Users-Neeraj-Documents-Sihcom-Savings-and-Loans/memory/feedback_commit_policy.md)). The plan suggests one bundled commit per phase. **Do not run `git commit` without confirming first.**
- **Reskin only in Phase 1.** Do NOT touch `app.py`, `models.py`, `interest.py`, `wallet.py`, or `database.py`. Templates and `static/style.css` only.
- **Preserve features.** Leaderboard glow, completion badges, time-to-ship card on order detail, `bernie_link` macro, clipboard `<script>` block, Bootstrap utilities (grid/spacing/display). When in doubt, retint rather than restructure.

---

## Phase 1 — Foundation (reskin)

### Task 1: Rewrite `static/style.css` with the design system

**Files:**
- Modify: `static/style.css` (full rewrite — current 70 lines → ~350 lines)

**Step 1: Replace the entire contents** of `static/style.css` with the block below. This sets `:root` tokens, overrides Bootstrap card/button/table/alert/progress/nav/form colors via CSS variables and selectors, and preserves the leaderboard `.progress-glow` and `.completion-badge` rules (retinted).

```css
/* Sihcom Savings & Loans — design system (2026-05-24) */

:root {
    --sl-bg: #fafaf7;
    --sl-surface: #ffffff;
    --sl-surface-alt: #f4f4f0;
    --sl-ink: #1a1f2c;
    --sl-muted: #5a6472;
    --sl-border: #e3e5e8;
    --sl-navy: #003765;
    --sl-navy-hover: #002a4d;
    --sl-green: #00834a;
    --sl-green-hover: #006d3d;
    --sl-red: #a8232b;
    --sl-warn: #b8770b;
    --sl-progress-track: #eceae3;
    --sl-card-shadow: 0 1px 2px rgba(20, 30, 50, 0.04);
}

/* --- Base / typography --- */
body {
    background: var(--sl-bg) !important;
    color: var(--sl-ink) !important;
    font-family: 'Inter', system-ui, -apple-system, Segoe UI, sans-serif;
    font-variant-numeric: tabular-nums;
}

h1, h2, h3, h4, h5, h6,
.navbar-brand {
    font-family: 'Source Serif 4', Georgia, serif;
    font-weight: 600;
    color: var(--sl-navy);
}

a { color: var(--sl-navy); }
a:hover { color: var(--sl-navy-hover); }

/* --- Nav --- */
.navbar {
    background: var(--sl-surface) !important;
    border-bottom: 1px solid var(--sl-border);
}
.navbar .navbar-brand {
    color: var(--sl-navy) !important;
    font-size: 1.1rem;
}
.navbar .nav-link {
    color: var(--sl-ink) !important;
    font-weight: 500;
}
.navbar .nav-link:hover,
.navbar .nav-link.active { color: var(--sl-navy) !important; }
.navbar .navbar-toggler-icon {
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 30 30' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath stroke='%231a1f2c' stroke-linecap='round' stroke-miterlimit='10' stroke-width='2' d='M4 7h22M4 15h22M4 23h22'/%3E%3Csvg%3E");
}
.dropdown-menu {
    background: var(--sl-surface);
    border: 1px solid var(--sl-border);
}
.dropdown-menu .dropdown-item { color: var(--sl-ink); }
.dropdown-menu .dropdown-item:hover { background: var(--sl-surface-alt); color: var(--sl-navy); }
.dropdown-divider { border-color: var(--sl-border); }

/* --- Cards --- */
.card {
    background: var(--sl-surface) !important;
    border: 1px solid var(--sl-border) !important;
    color: var(--sl-ink);
    box-shadow: var(--sl-card-shadow);
}
.card-header {
    background: var(--sl-surface-alt);
    border-bottom: 1px solid var(--sl-border);
    color: var(--sl-ink);
}
.card-title { color: var(--sl-navy); }

/* --- Buttons --- */
.btn-primary,
.btn-outline-light.btn-sm,    /* legacy "View" buttons -> primary navy */
.btn-info {
    background: var(--sl-navy);
    border-color: var(--sl-navy);
    color: #fff;
}
.btn-primary:hover,
.btn-outline-light.btn-sm:hover,
.btn-info:hover {
    background: var(--sl-navy-hover);
    border-color: var(--sl-navy-hover);
    color: #fff;
}
.btn-outline-primary,
.btn-outline-info,
.btn-outline-light {
    background: var(--sl-surface);
    border-color: var(--sl-navy);
    color: var(--sl-navy);
}
.btn-outline-primary:hover,
.btn-outline-info:hover,
.btn-outline-light:hover {
    background: var(--sl-navy);
    color: #fff;
}
.btn-success {
    background: var(--sl-green);
    border-color: var(--sl-green);
    color: #fff;
}
.btn-success:hover {
    background: var(--sl-green-hover);
    border-color: var(--sl-green-hover);
    color: #fff;
}
.btn-outline-success {
    background: var(--sl-surface);
    border-color: var(--sl-green);
    color: var(--sl-green);
}
.btn-outline-success:hover {
    background: var(--sl-green);
    color: #fff;
}
.btn-warning,
.btn-outline-warning {
    background: var(--sl-surface);
    border-color: var(--sl-warn);
    color: var(--sl-warn);
}
.btn-warning:hover,
.btn-outline-warning:hover {
    background: var(--sl-warn);
    color: #fff;
}
.btn-danger {
    background: var(--sl-red);
    border-color: var(--sl-red);
    color: #fff;
}
.btn-danger:hover { background: #8a1a22; border-color: #8a1a22; }

/* --- Tables --- */
.table {
    --bs-table-bg: var(--sl-surface);
    --bs-table-color: var(--sl-ink);
    --bs-table-border-color: var(--sl-border);
    --bs-table-striped-bg: var(--sl-surface-alt);
    --bs-table-striped-color: var(--sl-ink);
    --bs-table-hover-bg: var(--sl-surface-alt);
    --bs-table-hover-color: var(--sl-ink);
    color: var(--sl-ink);
    border-color: var(--sl-border);
}
.table-dark {
    --bs-table-bg: var(--sl-surface);
    --bs-table-color: var(--sl-ink);
    --bs-table-border-color: var(--sl-border);
    --bs-table-striped-bg: var(--sl-surface-alt);
    --bs-table-striped-color: var(--sl-ink);
    --bs-table-hover-bg: var(--sl-surface-alt);
    --bs-table-hover-color: var(--sl-ink);
    color: var(--sl-ink);
    border-color: var(--sl-border);
}
.table thead th {
    background: var(--sl-surface-alt);
    color: var(--sl-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.75rem;
    font-weight: 600;
    border-bottom: 1px solid var(--sl-border);
}
.num { text-align: right; font-variant-numeric: tabular-nums; }
.pos { color: var(--sl-green); font-weight: 500; }
.neg { color: var(--sl-red); font-weight: 500; }

/* --- Progress bars --- */
.progress {
    background-color: var(--sl-progress-track);
}
.progress-bar {
    background-color: var(--sl-navy);
}
.progress-bar.bg-success { background-color: var(--sl-green) !important; }
.progress-bar.bg-info    { background-color: var(--sl-navy) !important; }
.progress-bar.bg-primary { background-color: var(--sl-navy) !important; }

/* Leaderboard glow — retained, retinted via inline hsl() */
.progress-glow {
    overflow: visible;
    border-radius: 0.375rem;
    background-color: var(--sl-progress-track);
}
.progress-glow .progress-bar {
    border-radius: 0.375rem;
    transition: width 0.4s ease, background-color 0.4s ease, box-shadow 0.4s ease;
}

/* Completion badges */
.completion-badge {
    width: 28px;
    height: 28px;
    object-fit: contain;
    vertical-align: middle;
    opacity: 0.85;
    transition: opacity 0.2s, transform 0.2s;
    cursor: pointer;
    /* subtle halo so transparent PNGs read on cream */
    filter: drop-shadow(0 0 1px rgba(255, 255, 255, 0.9));
}
.completion-badge:hover {
    opacity: 1;
    transform: scale(1.15);
}

/* --- Alerts --- */
.alert-info {
    background: #eaf2fb;
    border-color: #c5d8ee;
    color: #1d4577;
}
.alert-success {
    background: #e6f4ec;
    border-color: #b8dec9;
    color: #0f5532;
}
.alert-warning {
    background: #fef8ea;
    border-color: #ecd9a9;
    color: #6b4509;
}
.alert-danger {
    background: #fbe9eb;
    border-color: #ecbcc0;
    color: #6b1219;
}
.alert-secondary,
.alert-light {
    background: var(--sl-surface-alt);
    border-color: var(--sl-border);
    color: var(--sl-ink);
}

/* --- Badges --- */
.badge.bg-secondary { background: var(--sl-muted) !important; }
.badge.bg-primary   { background: var(--sl-navy) !important; }
.badge.bg-success   { background: var(--sl-green) !important; }
.badge.bg-warning   { background: var(--sl-warn) !important; color: #fff !important; }
.badge.bg-danger    { background: var(--sl-red) !important; }
.badge.bg-info      { background: #2a6cb0 !important; }

/* --- Forms --- */
.form-control,
.form-select {
    background: var(--sl-surface);
    color: var(--sl-ink);
    border-color: var(--sl-border);
}
.form-control:focus,
.form-select:focus {
    background: var(--sl-surface);
    color: var(--sl-ink);
    border-color: var(--sl-navy);
    box-shadow: 0 0 0 0.2rem rgba(0, 55, 101, 0.15);
}
.form-label,
.form-check-label,
.card-header h5 {
    color: var(--sl-ink);
}
.form-text { font-size: 0.8rem; color: var(--sl-muted); }

/* --- Breadcrumbs --- */
.breadcrumb { background: transparent; }
.breadcrumb-item a {
    color: var(--sl-navy);
    text-decoration: none;
}
.breadcrumb-item a:hover { color: var(--sl-navy-hover); }
.breadcrumb-item.active { color: var(--sl-muted); }
.breadcrumb-item + .breadcrumb-item::before { color: var(--sl-muted); }

/* --- Modals --- */
.modal-content {
    background: var(--sl-surface);
    color: var(--sl-ink);
    border: 1px solid var(--sl-border);
}
.modal-header,
.modal-footer { border-color: var(--sl-border); }

/* --- Footer / misc --- */
footer { color: var(--sl-muted); }

/* --- Bernie link macro: re-tint for light bg --- */
.bernie-link {
    color: var(--sl-navy) !important;
    font-weight: 600;
}
.bernie-link sup { color: var(--sl-muted) !important; }
.bernie-copy-btn { color: var(--sl-muted) !important; }
.bernie-copy-btn:hover { color: var(--sl-navy) !important; }

/* --- Utility shims for templates that haven't been migrated yet ---
   These let "text-white" / "text-light" / "text-secondary" classes coexist
   with the light theme during the per-template restyle pass. Remove once
   every template has been migrated off them. */
.text-white, .text-light { color: var(--sl-ink) !important; }
.text-secondary { color: var(--sl-muted) !important; }
.text-info { color: var(--sl-navy) !important; }
.text-success { color: var(--sl-green) !important; }
.text-warning { color: var(--sl-warn) !important; }
.text-danger { color: var(--sl-red) !important; }
.bg-dark, .bg-black { background: var(--sl-bg) !important; }
.bg-secondary.bg-opacity-25,
.bg-secondary.bg-opacity-10 {
    background: var(--sl-surface) !important;
    border-color: var(--sl-border) !important;
}
.border-secondary, .border-info { border-color: var(--sl-border) !important; }
```

**Step 2: Visual sanity check (no Flask boot yet).** Open [docs/plans/2026-05-24-ui-redesign-preview.html](docs/plans/2026-05-24-ui-redesign-preview.html) in a browser. Confirm you've matched the same token values (cream bg, navy primary, green money, etc.) and the same Source Serif 4 / Inter typography stack. You are not running the app yet — that happens after Task 2.

---

### Task 2: Update `base.html` — fonts, body classes, nav, footer

**Files:**
- Modify: `templates/base.html`

**Step 1: Replace the `<head>` block** to add the Google Fonts `<link>` after the Bootstrap CDN link:

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Sihcom Savings &amp; Loans{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link href="{{ url_for('static', filename='style.css') }}" rel="stylesheet">
</head>
```

**Step 2: Replace the `<body>` opening tag and `<nav>`** to drop dark-theme classes:

```html
<body>
    <nav class="navbar navbar-expand-lg">
        <div class="container">
            <a class="navbar-brand fw-bold" href="{{ url_for('index') }}">Sihcom Savings &amp; Loans</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navContent">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navContent">
                {% if session.get('character_id') %}
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('dashboard') }}">Dashboard</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('catalog') }}">Ship Catalog</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('leaderboard') }}">Leaderboard</a>
                    </li>
                    {% if session.get('is_admin') %}
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
                            Admin
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('admin_catalog') }}">Ship Catalog</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('admin_loans') }}">Loans</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('admin_unmatched') }}">Unmatched Transactions</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('admin_users') }}">Users</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="{{ url_for('admin_settings') }}">Settings</a></li>
                        </ul>
                    </li>
                    {% endif %}
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item">
                        <a class="nav-link position-relative" href="{{ url_for('notifications') }}">
                            &#x1F514;
                            {% if unread_notification_count > 0 %}
                            <span class="badge rounded-pill bg-danger">{{ unread_notification_count }}</span>
                            {% endif %}
                        </a>
                    </li>
                    <li class="nav-item">
                        <span class="nav-link">{{ session.get('character_name', '') }}</span>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('logout') }}">Logout</a>
                    </li>
                </ul>
                {% endif %}
            </div>
        </div>
    </nav>
```

Specifically: dropped `bg-dark text-light` on `<body>`, dropped `navbar-dark bg-black border-bottom border-secondary` on `<nav>`, dropped `dropdown-menu-dark` on the admin dropdown, dropped `text-info` on the character name span, dropped `btn-close-white` from flash alerts (next step covers).

**Step 3: Update the flash-alert close button** (lines around 72):

```html
<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
```

(Already plain `btn-close` — confirm the existing code doesn't have `btn-close-white`. If present, drop the `-white`.)

**Step 4: Update the footer** (line 80):

```html
<footer class="container mt-5 mb-3 text-center">
    <small>Sihcom Savings &amp; Loans &mdash; Fly safe, save smart.</small>
</footer>
```

Drop `text-secondary` — the `footer` selector in CSS now handles it.

**Step 5: Boot the Flask dev server and verify.**

Run:
```
python app.py
```

Open http://localhost:5000/ in a browser. Expected:
- Cream page background.
- White nav bar with navy "Sihcom Savings & Loans" brand in Source Serif 4.
- The index.html splash text is still readable (it'll get its own retheme in Task 3).
- No 500 error.

If fonts haven't loaded yet (briefly serif-less), refresh once — Google Fonts can take a beat on first load. If they never load, check the `<link>` href for typos.

Leave the server running; subsequent tasks reload on edit.

---

### Task 3: Retheme `templates/index.html` (Phase 1 only — Phase 2 rebuilds this)

**Files:**
- Modify: `templates/index.html`

This is a stop-gap retheme. Phase 2 replaces this file entirely with a hero + product grid.

**Step 1: Replace the file body:**

```html
{% extends "base.html" %}
{% block title %}Sihcom Savings &amp; Loans{% endblock %}

{% block content %}
<div class="text-center mt-5">
    <h1 class="display-4 mb-3">Sihcom Savings &amp; Loans</h1>
    <p class="lead mb-4" style="color: var(--sl-muted);">
        Save toward your next ship. Your deposits earn compound interest until you reach your goal.
    </p>
    <a href="{{ url_for('login') }}">
        <img src="https://web.ccpgamescdn.com/eveonlineassets/developers/eve-sso-login-black-large.png"
             alt="Log in with EVE Online" class="mt-3">
    </a>
    <div class="mt-4">
        <small><a href="{{ url_for('login', admin=1) }}">Admin Login</a></small>
    </div>
</div>
{% endblock %}
```

**Step 2: Reload http://localhost:5000/ and verify** — splash text reads on cream, EVE login button still visible.

---

### Task 4: Retheme `templates/dashboard.html`

**Files:**
- Modify: `templates/dashboard.html`

The shim rules in `style.css` mean the existing dark-theme classes will already render passably on cream. This task strips the now-redundant classes so the markup is clean.

**Step 1: Find-and-replace inside `templates/dashboard.html`:**
- `text-white` → (remove)
- `text-light` → (remove)
- `text-secondary` → `text-muted`
- `text-info` → (remove on plain spans; keep where it conveys "info" meaning — e.g. the "Goal approved!" copy)
- `bg-secondary bg-opacity-25 border-secondary` → (remove — plain `.card` styling now handles it)
- `bg-secondary bg-opacity-10 border-secondary` → (remove)
- `bg-dark text-light border-secondary` (on the modal) → (remove all three)
- `btn-outline-light` → `btn-outline-primary`
- `btn-outline-success` → keep
- `btn-outline-warning` → keep (used for "Request Credit Line Draw")
- `dropdown-menu-dark` → (remove if it appears anywhere)

**Step 2: Update the deposit-help collapse link** (around the `data-bs-toggle="collapse"`):

Replace `class="text-info text-decoration-none"` with `class="text-decoration-none"` and let the link inherit `var(--sl-navy)`.

**Step 3: Update the frozen-collateral hint** (around line 159):

Replace `<small class="text-secondary">Credit line freezes part of this savings from earning interest</small>` with the same `<small>` but no class — `color` inherits from `body`.

**Step 4: Reload http://localhost:5000/dashboard** (log in first if needed) and verify:
- Cards have white surface, thin border, soft shadow.
- "My Loan" + "My Savings Goals" headings render in Source Serif 4 navy.
- Money amounts are still readable (ISK figures black).
- Outstanding balance / pending interest hints are still legible — the warning color now reads as warm amber rather than yellow-on-yellow.
- "Request Credit Line Draw" modal opens, form fields are visible on white, navy focus ring.
- "Browse Ships" outline-success button reads as green outline.

---

### Task 5: Retheme `templates/order_detail.html`

**Files:**
- Modify: `templates/order_detail.html`

**Critical:** the time-to-ship block (lines ~86-105) was recently shipped — must survive intact. Keep `text-info` on the time-to-ship line; it's semantically info-y and the CSS shim renders it as navy.

**Step 1: Find-and-replace inside `templates/order_detail.html`:**
- `text-white` → (remove)
- `text-light` → (remove)
- `text-secondary` → `text-muted`
- `text-info` → keep only on the time-to-ship `<div class="text-info">` line (~89); drop on `"Goal approved!"` etc.
- `bg-secondary bg-opacity-25 border-secondary` → (remove)
- `border-info` on the "How to Deposit" sidebar card → (remove — light card border looks fine)
- `table-dark` → `table` (already covered by `.table-dark` shim, but cleaner)
- `table-striped` → keep
- `btn-outline-light` → `btn-outline-primary`
- `btn-outline-warning` → keep

**Step 2: Replace the frozen-collateral alert** (lines ~59-64) to use the new `alert-warning` token:

```html
{% if balance['effective_balance'] is defined and balance['effective_balance'] < balance['savings_balance'] %}
<div class="alert alert-warning py-2 mb-3">
    <small>Earning interest on <strong>{{ balance['effective_balance'] | isk }}</strong>
    &mdash; your open credit line freezes the collateralized portion of this savings.</small>
</div>
{% endif %}
```

**Step 3: Reload http://localhost:5000/order/&lt;some-active-id&gt;** and verify:
- Progress bar fills navy on cream track.
- Time-to-ship line reads as navy info, with the muted clarifier line below.
- Deposit history + interest history tables: white surface, uppercase muted column headers, thin row dividers, green interest values.
- Ship image on the sidebar still loads (sidebar card is white).
- "How to Deposit" sidebar card reads (bernie_link should render as navy-bold; if it still looks white, jump to Task 11 early).
- If there's a frozen-collateral alert, it reads as soft amber.

---

### Task 6: Retheme `templates/loan_detail.html`

**Files:**
- Modify: `templates/loan_detail.html`

Same pattern as Task 5.

**Step 1: Find-and-replace:**
- `text-white`, `text-light` → (remove)
- `text-secondary` → `text-muted`
- `text-warning` on the outstanding balance `<strong>` (line ~37) → keep — semantically meaningful
- `text-success` on payment amounts → replace with class `neg` (these are payments *against* the loan; visually we want red/neg or muted) — actually, the design treats loan repayment as money-positive *for the user*. **Keep** `text-success` and let the shim render it green.
- `bg-secondary bg-opacity-25 border-secondary` → (remove)
- `border-info` → (remove)
- `table-dark` → `table`
- `btn-outline-light` → `btn-outline-primary`

**Step 2: Reload http://localhost:5000/loan/&lt;some-active-id&gt;** (or open one from the admin loans page) and verify:
- Status badge ("Active" / "Pending Disbursement") reads on white.
- Outstanding balance amount is visibly warning-amber.
- Payment history table renders, payment amounts are green.
- Interest history table renders, charged interest reads amber/warning.

---

### Task 7: Retheme `templates/leaderboard.html` (preserve glow + badges)

**Files:**
- Modify: `templates/leaderboard.html`

The HSL math driving `.progress-glow` works on any background because it sets background-color/box-shadow inline based on progress. Nothing about the glow has to change — only the surrounding card/table/text classes.

**Step 1: Find-and-replace:**
- `text-white`, `text-light` → (remove)
- `text-secondary` → `text-muted`
- `table-dark` → `table`
- `bg-secondary bg-opacity-25 border-secondary` → (remove)
- `fw-semibold` → keep

**Step 2: Boot http://localhost:5000/leaderboard** and **eyeball-verify the glow.** Specifically:
- Every entry's progress bar has its width and HSL color.
- High-progress entries (60%+) should have a visible cyan-ish halo. The hue is hardcoded `hsl(180, ...)` — that's cyan; on cream it reads as a teal glow rather than dark-mode neon. **This is acceptable.** Do not change the hue without checking with the user.
- Completion badges render with the slight white drop-shadow halo added in Task 1. Hover popover still shows the ship image.
- Pilot names are dark ink, not invisible-on-white.

If the glow looks anemic on cream, note it in the verification report — don't fix it here. Phase 1 verification (Task 13) is where we decide whether a retint is needed.

---

### Task 8: Retheme `templates/catalog.html`

**Files:**
- Modify: `templates/catalog.html`

**Step 1: Find-and-replace:**
- `text-light` → (remove)
- `text-white` → (remove)
- `text-info` on the price line (around `<p class="card-text text-info fs-5">`) → replace with `class="card-text fs-5"` and add inline `style="color: var(--sl-green); font-weight: 600;"` — ship prices read as positive money.
- `bg-secondary bg-opacity-25 border-secondary` → (remove)
- `btn-outline-secondary` → keep (disabled state)

**Step 2: Reload http://localhost:5000/catalog** and verify:
- Category headings render in Source Serif 4 navy.
- Ship cards: white surface, ship image, navy ship name, green price, navy/green Start Saving button.
- Disabled "Start Saving" still renders as muted outline.

---

### Task 9: Retheme `templates/notifications.html`

**Files:**
- Modify: `templates/notifications.html`

**Step 1: Find-and-replace:**
- `text-white` → (remove)
- `text-secondary` → `text-muted`
- `bg-secondary bg-opacity-25 border-secondary` on list-group-items → replace with `border` (Bootstrap's default 1px border + our `--sl-border` override)
- `border-info` (on unread items) → replace with inline `style="border-left: 3px solid var(--sl-navy);"`
- `btn-outline-info` → `btn-outline-primary`

**Step 2: Reload http://localhost:5000/notifications** and verify:
- Unread notifications have a navy left border.
- Read notifications have a plain border on white.
- "View Goal" button is navy outline.

---

### Task 10: Retheme `templates/error.html`

**Files:**
- Modify: `templates/error.html`

**Step 1: Replace contents:**

```html
{% extends "base.html" %}
{% block title %}Error {{ code }}{% endblock %}

{% block content %}
<div class="text-center mt-5">
    <h1 class="display-1" style="color: var(--sl-red);">{{ code }}</h1>
    <p class="lead">{{ message }}</p>
    <a href="{{ url_for('index') }}" class="btn btn-outline-primary mt-3">Go Home</a>
</div>
{% endblock %}
```

**Step 2: Verify** by hitting an undefined route, e.g. http://localhost:5000/nonexistent. Expect a navy "Go Home" button on cream.

---

### Task 11: Verify `_macros.html` (`bernie_link`) on light bg

**Files:**
- Modify (only if needed): `templates/_macros.html`

The CSS already retints `.bernie-link` and `.bernie-copy-btn` in Task 1. The inline classes inside the macro (`text-white`, `text-secondary`, `text-info`) will be overridden by the `.bernie-link` and `.bernie-copy-btn` selectors with `!important`. Read the macro to confirm and only edit if there's a visual issue.

**Step 1: Open** `templates/_macros.html` and skim. It should render OK as-is thanks to Task 1's CSS.

**Step 2: Visit a page that uses the macro** (e.g. http://localhost:5000/dashboard with an active goal, or `/order/<id>` "How to Deposit" sidebar). Confirm:
- Bernie's name renders bold navy.
- The `↗` arrow superscript is muted-grey.
- The clipboard `📋` button is muted-grey and turns navy on hover.
- Clicking the clipboard button copies the name (briefly says "Copied!" in green via `text-success`).

**Step 3: If anything reads as faint white-on-cream**, replace the inline `text-white`/`text-secondary`/`text-info` classes inside the macro with nothing (the dedicated `.bernie-*` selectors already handle color). Do not change the structure.

---

### Task 12: Retheme admin templates (9 files, mechanical)

**Files (modify all):**
- `templates/admin/dashboard.html`
- `templates/admin/users.html`
- `templates/admin/catalog.html`
- `templates/admin/create_order.html`
- `templates/admin/order_detail.html`
- `templates/admin/loans.html`
- `templates/admin/loan_detail.html`
- `templates/admin/unmatched.html`
- `templates/admin/settings.html`

This is the same find-and-replace pass as Tasks 4-9, applied across the admin set. The shim rules in `style.css` make every page already-readable; the goal of this task is to strip redundant dark-theme classes so the markup is clean and consistent.

**Step 1: For each admin template, find-and-replace:**
- `text-white` → (remove)
- `text-light` → (remove)
- `text-secondary` → `text-muted`
- `text-info` on plain text spans → (remove); keep on labels where it semantically means "info"
- `bg-dark`, `bg-black` → (remove — `body` cream now)
- `bg-secondary bg-opacity-25 border-secondary` → (remove)
- `bg-secondary bg-opacity-10 border-secondary` → (remove)
- `dropdown-menu-dark` → (remove)
- `table-dark` → `table`
- `btn-outline-light` → `btn-outline-primary`
- `btn-close-white` → `btn-close`
- `form-control bg-dark text-light border-secondary` → `form-control` (anywhere a form input has these)
- `form-select bg-dark text-light border-secondary` → `form-select`

**Step 2: For the `admin/settings.html` form rows specifically**, double-check that input fields still have visible borders on white. The `.form-control:focus` CSS sets a navy focus ring; the unfocused border is `--sl-border`.

**Step 3: For the `admin/loans.html` and `admin/unmatched.html` tables specifically**, eyeball-verify the "Reject Draw" button (admin loan detail), "Mark Disbursed" button, "Match" / "Ignore" actions. These should all read as proper buttons, not invisible.

**Step 4: Boot http://localhost:5000/admin** (logged in as admin — `ADMIN_CHARACTER_ID`) and walk every admin route:
- `/admin` (dashboard)
- `/admin/users`
- `/admin/catalog`
- `/admin/loans`
- `/admin/unmatched`
- `/admin/settings`
- `/admin/order/<id>` (pick one)
- `/admin/loan/<id>` (pick one)

No route should 500. All tables should render with the new uppercase muted column headers. All form inputs should be visible on white.

---

### Task 13: Phase 1 verification walk

**Files:** none.

**Step 1: With the Flask dev server running**, walk through every member page in order, eyeballing for any leftover dark-mode artifacts (invisible text, dark-on-dark cards, blue-on-blue links):

1. http://localhost:5000/ (logged out)
2. Log in via EVE SSO if not already.
3. http://localhost:5000/dashboard
4. http://localhost:5000/catalog
5. Start a savings goal (or use an existing pending/active goal). Visit http://localhost:5000/order/&lt;id&gt;.
6. http://localhost:5000/leaderboard — **special attention to the glow.** Compare with the design-doc note: glow should still read as "central to leaderboard appeal".
7. http://localhost:5000/notifications
8. Trigger an error: http://localhost:5000/no-such-route. Confirm error.html renders.
9. http://localhost:5000/loan/&lt;id&gt; (if there's an active loan; otherwise skip).

**Step 2: Walk every admin page** (Task 12 covered the smoke test; here you're looking for residual issues across more data):

1. http://localhost:5000/admin
2. http://localhost:5000/admin/users
3. http://localhost:5000/admin/catalog
4. http://localhost:5000/admin/order/new
5. http://localhost:5000/admin/loans
6. http://localhost:5000/admin/unmatched
7. http://localhost:5000/admin/settings

**Step 3: Report findings to the user.** Specifically flag:
- The leaderboard glow's read on cream (does it still feel alive, or does it need a hue tweak?).
- Any badge PNGs that look harsh on the cream background despite the drop-shadow halo.
- Any page that has unreadable text or invisible buttons.

**If everything passes, ask the user if they'd like to bundle Phase 1 into a single commit** (per their bundle-by-default preference). Suggested commit message:

```
Reskin to bank-style light theme (Phase 1)

Design system in CSS variables (--sl-*); Bootstrap kept for grid + components.
Drops dark-mode classes from all 19 templates. No Python changes.
```

**Do not run `git commit` without confirming first.**

---

## Phase 2 — Public product surface

**Phase boundary:** stop here for user review. The design doc explicitly phases this; the user may want to ship Phase 1 to production before Phase 2 lands. Ask before proceeding.

---

### Task 14: Add `models.get_current_rates()`

**Files:**
- Modify: `models.py:410-420` area

**Step 1: Add the function** to `models.py` directly below `get_loan_settings()` (around line 420):

```python
def get_current_rates():
    """Snapshot of the rates shown on public product pages."""
    return {
        'interest_rate': float(get_setting('interest_rate') or '0.05'),
        'general_loan_rate': float(get_setting('general_loan_rate') or '0.125'),
        'interest_period': get_setting('interest_period') or 'monthly',
    }
```

**Step 2: Smoke-test from the Python REPL** (Flask app context not required for a read-only function):

```
python -c "from app import app; ctx = app.app_context(); ctx.push(); import models; print(models.get_current_rates())"
```

Expected: a dict like `{'interest_rate': 0.05, 'general_loan_rate': 0.125, 'interest_period': 'monthly'}`. Exact values depend on `settings` rows.

---

### Task 15: Add four GET routes, rewire `/`, and add product page skeletons

**Files:**
- Modify: `app.py:263-267` (the existing `index` route)
- Add: `templates/products/savings.html`
- Add: `templates/products/loans.html`
- Add: `templates/products/credit_lines.html`

**Step 1: Replace the existing `index` route** in `app.py` (currently lines 263-267):

```python
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
```

Note: the previous `index` redirected logged-in users to `/dashboard`. The design doc explicitly says **no redirect** — logged-in users see the landing too, with a swapped CTA. The new route honors that.

**Step 2: Create `templates/products/savings.html`** (skeleton — content lands in Task 16):

```html
{% extends "base.html" %}
{% block title %}Savings — Sihcom S&amp;L{% endblock %}
{% block content %}
<h1>Savings</h1>
<p class="lead">Coming soon — product content in Task 16.</p>
{% endblock %}
```

**Step 3: Create `templates/products/loans.html` and `templates/products/credit_lines.html`** with the same skeleton (swap the `<h1>` text).

**Step 4: Boot Flask** and visit:
- http://localhost:5000/savings — should render the skeleton without 500.
- http://localhost:5000/loans — same.
- http://localhost:5000/credit-lines — same.
- http://localhost:5000/ — should still render `index.html` (still the old splash for now).

Verify both logged-out and logged-in (the routes don't gate on session).

---

### Task 16: Build `templates/products/savings.html` content

**Files:**
- Modify: `templates/products/savings.html`

**Step 1: Replace the skeleton with the full product page:**

```html
{% extends "base.html" %}
{% block title %}Savings — Sihcom S&amp;L{% endblock %}
{% block content %}

<div class="row align-items-center mb-5">
    <div class="col-lg-8">
        <h1 class="mb-3">Savings</h1>
        <p class="lead" style="color: var(--sl-muted);">
            Save toward a specific ship. Earn compounding interest while you wait.
        </p>
    </div>
    <div class="col-lg-4 text-end">
        {% set period = rates['interest_period'] %}
        <div style="color: var(--sl-green); font-weight: 600; font-size: 1.25rem;">
            {{ "%.2f"|format(rates['interest_rate'] * 100) }}% / {{ period }}
        </div>
        <small class="text-muted">Current rate</small>
    </div>
</div>

<div class="row g-4 mb-5">
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>How it works</h3>
                <ol class="mb-0">
                    <li>Pick a ship from the catalog.</li>
                    <li>Send ISK in-game to Bernie May Doff.</li>
                    <li>Wallet sync books each deposit to your goal automatically.</li>
                    <li>Interest accrues every period on your full balance.</li>
                    <li>When the goal is funded, the admin delivers your ship in-game.</li>
                </ol>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>Rate</h3>
                <p>
                    <strong style="color: var(--sl-green);">
                        {{ "%.2f"|format(rates['interest_rate'] * 100) }}% per {{ period }}
                    </strong>
                </p>
                <p class="mb-0 text-muted">
                    Compounds at the end of each {{ period }} period. New deposits
                    earn full interest on the next period boundary &mdash; no proration.
                </p>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>Rules</h3>
                <ul class="mb-0">
                    <li>One active savings goal per pilot.</li>
                    <li>Savings boosts only apply to accounts with in-game activity in the previous month.</li>
                    <li>The bank reserves the right to close an account by paying out balance plus accrued interest.</li>
                    <li>Withdrawals require admin approval and are blocked while a credit line is open against this savings.</li>
                </ul>
            </div>
        </div>
    </div>
</div>

<div class="text-center mb-5">
    {% if session.get('character_id') %}
    <a href="{{ url_for('catalog') }}" class="btn btn-primary btn-lg">Open a savings goal</a>
    {% else %}
    <a href="{{ url_for('login') }}" class="btn btn-primary btn-lg">Log in with EVE</a>
    {% endif %}
</div>

{% endblock %}
```

**Step 2: Reload http://localhost:5000/savings** logged-out and logged-in. Verify:
- Logged-out CTA: "Log in with EVE" (navy primary).
- Logged-in CTA: "Open a savings goal" (navy primary, links to `/catalog`).
- Three product cards render side-by-side on desktop, stacked on mobile.
- Current rate in the header reads in green.
- Period in the rate string matches `admin/settings` (`monthly` by default).

---

### Task 17: Build `templates/products/loans.html` content

**Files:**
- Modify: `templates/products/loans.html`

**Step 1: Replace the skeleton:**

```html
{% extends "base.html" %}
{% from '_macros.html' import bernie_link with context %}
{% block title %}General Loans — Sihcom S&amp;L{% endblock %}
{% block content %}

<div class="row align-items-center mb-5">
    <div class="col-lg-8">
        <h1 class="mb-3">General Loans</h1>
        <p class="lead" style="color: var(--sl-muted);">
            Admin-originated loans for major purchases. Fixed rate, flexible payback.
        </p>
    </div>
    <div class="col-lg-4 text-end">
        {% set period = rates['interest_period'] %}
        <div style="color: var(--sl-red); font-weight: 600; font-size: 1.25rem;">
            {{ "%.2f"|format(rates['general_loan_rate'] * 100) }}% / {{ period }}
        </div>
        <small class="text-muted">Current rate</small>
    </div>
</div>

<div class="row g-4 mb-5">
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>How it works</h3>
                <ol class="mb-0">
                    <li>Talk to Bernie in-game about your needs.</li>
                    <li>Once approved, the loan is disbursed to your wallet.</li>
                    <li>Interest accrues every {{ rates['interest_period'] }} on the outstanding balance.</li>
                    <li>Repay by sending ISK in-game to {{ bernie_link() }}; wallet sync auto-applies it to the loan first.</li>
                </ol>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>Rate</h3>
                <p>
                    <strong style="color: var(--sl-red);">
                        {{ "%.2f"|format(rates['general_loan_rate'] * 100) }}% per {{ rates['interest_period'] }}
                    </strong>
                </p>
                <p class="mb-0 text-muted">
                    Compounds on the outstanding balance at the end of each period.
                    Pay early to save on interest &mdash; no prepayment penalty.
                </p>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>Rules</h3>
                <ul class="mb-0">
                    <li>One active loan per pilot (any product).</li>
                    <li>Loans are invite-only and originated by the admin.</li>
                    <li>Wallet sync is the canonical repayment path.</li>
                    <li>The admin may pause interest at their discretion (e.g. during disputes).</li>
                </ul>
            </div>
        </div>
    </div>
</div>

<div class="text-center mb-5">
    {% if session.get('character_id') %}
    <p class="lead">To request a general loan, contact {{ bernie_link() }} in-game.</p>
    {% else %}
    <a href="{{ url_for('login') }}" class="btn btn-primary btn-lg">Log in with EVE</a>
    {% endif %}
</div>

{% endblock %}
```

**Step 2: Reload http://localhost:5000/loans** logged-out and logged-in. Verify CTA swap, rate format, and that `bernie_link` renders correctly inside the page (the `with context` import is required — already in the template).

---

### Task 18: Build `templates/products/credit_lines.html` content

**Files:**
- Modify: `templates/products/credit_lines.html`

**Step 1: Replace the skeleton:**

```html
{% extends "base.html" %}
{% block title %}Credit Lines — Sihcom S&amp;L{% endblock %}
{% block content %}

<div class="row align-items-center mb-5">
    <div class="col-lg-8">
        <h1 class="mb-3">Credit Lines</h1>
        <p class="lead" style="color: var(--sl-muted);">
            Borrow against your savings. Same rate as your account, no liquidation.
        </p>
    </div>
    <div class="col-lg-4 text-end">
        {% set period = rates['interest_period'] %}
        <div style="color: var(--sl-green); font-weight: 600; font-size: 1.25rem;">
            {{ "%.2f"|format(rates['interest_rate'] * 100) }}% / {{ period }}
        </div>
        <small class="text-muted">Current rate</small>
    </div>
</div>

<div class="row g-4 mb-5">
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>How it works</h3>
                <ol class="mb-0">
                    <li>Build a savings balance first.</li>
                    <li>Request a draw of any amount up to your total savings.</li>
                    <li>Once disbursed, the drawn amount is frozen out of your interest-earning balance.</li>
                    <li>Repay by sending ISK in-game; payments auto-apply to the loan first, then to savings.</li>
                    <li>When the balance hits zero, your full savings starts earning interest again.</li>
                </ol>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>Rate</h3>
                <p>
                    <strong style="color: var(--sl-green);">
                        {{ "%.2f"|format(rates['interest_rate'] * 100) }}% per {{ rates['interest_period'] }}
                    </strong>
                </p>
                <p class="mb-0 text-muted">
                    Matches your savings rate exactly. The frozen-collateral portion of
                    your savings stops earning interest, so the net cost is the spread
                    on the unfrozen portion only.
                </p>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>Rules</h3>
                <ul class="mb-0">
                    <li>Maximum draw is your current total savings balance.</li>
                    <li>One active loan per pilot &mdash; opening a credit line blocks general loans and vice versa.</li>
                    <li>Withdrawal, cancellation, and goal-funding actions are blocked while a credit line is open.</li>
                    <li>No liquidation: your savings stays yours; the draw simply freezes the matching portion.</li>
                </ul>
            </div>
        </div>
    </div>
</div>

<div class="text-center mb-5">
    {% if session.get('character_id') %}
    <a href="{{ url_for('dashboard') }}" class="btn btn-primary btn-lg">Request a draw on the dashboard</a>
    {% else %}
    <a href="{{ url_for('login') }}" class="btn btn-primary btn-lg">Log in with EVE</a>
    {% endif %}
</div>

{% endblock %}
```

**Step 2: Reload http://localhost:5000/credit-lines** logged-out and logged-in. Verify CTA swap, three cards render side-by-side, rate format.

---

### Task 19: Rebuild `templates/index.html` as the new landing

**Files:**
- Modify: `templates/index.html`

This replaces the splash with: hero (navy gradient) + product card grid linking to the three product pages.

**Step 1: Replace contents:**

```html
{% extends "base.html" %}
{% block title %}Sihcom Savings &amp; Loans{% endblock %}
{% block content %}

<div class="p-5 mb-5 rounded-3" style="
    background: linear-gradient(135deg, var(--sl-navy) 0%, #001f3a 100%);
    color: #fff;
">
    <div class="row align-items-center">
        <div class="col-lg-7">
            <h1 style="color: #fff; font-size: 2.5rem;">Bank of the corp.</h1>
            <p class="lead" style="color: #c8d4e2; max-width: 520px;">
                Save for your next ship. Borrow against your balance. Earn interest while you fly.
            </p>
            {% if session.get('character_id') %}
            <a href="{{ url_for('dashboard') }}" class="btn btn-lg"
               style="background: var(--sl-green); border-color: var(--sl-green); color: #fff;">
                Go to dashboard
            </a>
            {% else %}
            <a href="{{ url_for('login') }}" class="btn btn-lg"
               style="background: var(--sl-green); border-color: var(--sl-green); color: #fff;">
                Log in with EVE
            </a>
            {% endif %}
        </div>
    </div>
</div>

<div class="row g-4 mb-5">
    {% set period = rates['interest_period'] %}
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>Savings</h3>
                <p class="text-muted">
                    Save toward a specific ship. Earn compounding interest while you wait.
                </p>
                <div style="color: var(--sl-green); font-weight: 600;">
                    {{ "%.2f"|format(rates['interest_rate'] * 100) }}% / {{ period }}
                </div>
                <a href="{{ url_for('product_savings') }}" class="d-inline-block mt-3"
                   style="font-weight: 600; text-decoration: none;">
                    Open a goal &rarr;
                </a>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>Credit Lines</h3>
                <p class="text-muted">
                    Borrow against your savings. Same rate as your account, no liquidation.
                </p>
                <div style="color: var(--sl-green); font-weight: 600;">
                    {{ "%.2f"|format(rates['interest_rate'] * 100) }}% / {{ period }}
                </div>
                <a href="{{ url_for('product_credit_lines') }}" class="d-inline-block mt-3"
                   style="font-weight: 600; text-decoration: none;">
                    Request a draw &rarr;
                </a>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card h-100">
            <div class="card-body">
                <h3>General Loans</h3>
                <p class="text-muted">
                    Admin-originated loans for major purchases. Fixed rate, flexible payback.
                </p>
                <div style="color: var(--sl-red); font-weight: 600;">
                    {{ "%.2f"|format(rates['general_loan_rate'] * 100) }}% / {{ period }}
                </div>
                <a href="{{ url_for('product_loans') }}" class="d-inline-block mt-3"
                   style="font-weight: 600; text-decoration: none;">
                    Speak to Bernie &rarr;
                </a>
            </div>
        </div>
    </div>
</div>

{% if not session.get('character_id') %}
<div class="text-center mb-5">
    <small><a href="{{ url_for('login', admin=1) }}" class="text-muted">Admin Login</a></small>
</div>
{% endif %}

{% endblock %}
```

**Step 2: Reload http://localhost:5000/** in both states:
- Logged-out: navy hero with green "Log in with EVE" CTA. Three product cards below. Tiny admin-login link at the bottom.
- Logged-in: same hero with green "Go to dashboard" CTA. Product cards still visible. No admin-login link.

Click each product card's link — should land on `/savings`, `/credit-lines`, `/loans` respectively.

**Step 3: Confirm no redirect.** Visit http://localhost:5000/ while logged in — the page should render, not redirect to `/dashboard`. The old `if 'character_id' in session: return redirect(...)` is gone (Task 15 removed it).

---

### Task 20: Phase 2 verification walk

**Files:** none.

**Step 1: Logged-out walk:**
1. Log out via `/logout` (or clear session).
2. http://localhost:5000/ — hero + product cards render. CTAs say "Log in with EVE".
3. http://localhost:5000/savings — page renders, CTA says "Log in with EVE".
4. http://localhost:5000/loans — same.
5. http://localhost:5000/credit-lines — same.
6. Click "Log in with EVE" on any of them — should hit `/login` and trigger SSO redirect.

**Step 2: Logged-in walk:**
1. Log in via EVE SSO.
2. http://localhost:5000/ — hero CTA is "Go to dashboard". Click it — should hit `/dashboard`.
3. Use the navbar brand to come back to `/`. Page should render without redirecting.
4. http://localhost:5000/savings — CTA says "Open a savings goal" and links to `/catalog`.
5. http://localhost:5000/credit-lines — CTA says "Request a draw on the dashboard" and links to `/dashboard`.
6. http://localhost:5000/loans — paragraph mentions contacting Bernie in-game (no CTA button).

**Step 3: Rate validation.** Visit http://localhost:5000/admin/settings. Note the current `interest_rate` and `general_loan_rate` values. Then visit each product page and confirm the displayed rate matches what `admin/settings` shows. (Sanity-check that `get_current_rates()` is reading the right keys.)

**Step 4: Report findings to the user.** Specifically flag:
- Anything that looks wrong on mobile (`col-md-4` stacks at <768px; cards should be full-width below that).
- Whether the navy hero gradient reads well on the cream page.
- Whether the rules sections feel like the right level of detail for a v1 ToS replacement (the user has flagged adding rules over time).

**If everything passes, ask the user if they'd like to bundle Phase 2 into a commit.** Suggested commit message:

```
Add public product surface (Phase 2)

New routes /, /savings, /loans, /credit-lines render the bank-style hero
and product pages. Per-product Rules sections fold in the deferred ToS.
Rates sourced from new models.get_current_rates().
```

---

## Phase 3 — Dashboard product cards (deferred)

Per the design doc, Phase 3 is **deferred pending Phase 2 results.** The user wants to evaluate whether the dashboard already feels cohesive after Phase 2 ships before committing to more redesign work.

When (if) Phase 3 starts, it will:
- Restyle `templates/dashboard.html`'s "My Loan" and "My Savings Goals" sections to use the same `.card` patterns as the product pages.
- Likely add a small Savings/Credit-Line/Loan card grid above the current detail blocks.

Open as a separate plan when the user signals to proceed.

---

## Open follow-ups (post-Phase 2)

Out of scope for this plan but tracked in [docs/plans/2026-05-24-ui-redesign-design.md](docs/plans/2026-05-24-ui-redesign-design.md):
- Boost-activity ESI signal (need a `last_active_at` derived from ESI character endpoint).
- Admin forced-close action (distinct from `admin_complete_paid_directly`).
- `/bonds` page (deferred product entirely).
