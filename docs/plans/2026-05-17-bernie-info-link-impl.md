# Bernie May Doff Info Link Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn every mention of "Bernie May Doff" in the member UI into a clickable affordance with two actions — open his evewho.com character info in a new tab, and copy his name to clipboard.

**Architecture:** Single source of truth via a Flask context processor (admin name + evewho URL) and a Jinja macro that renders the link+copy unit. JS handler on `base.html` listens globally for `[data-copy-value]` click events.

**Tech Stack:** Flask, Jinja2, vanilla JS (`navigator.clipboard.writeText`), Bootstrap 5 (for any tooltip/styling).

**Design doc:** `docs/plans/2026-05-17-bernie-info-link-design.md`

---

### Task 1: Add context processor injecting admin name + evewho URL

**Files:**
- Modify: `app.py` near the existing `inject_notification_count` context processor (~line 181)

**Step 1: Add the context processor**

```python
@app.context_processor
def inject_admin_link():
    return {
        'admin_character_name': 'Bernie May Doff',
        'admin_evewho_url': f'https://evewho.com/character/{Config.ADMIN_CHARACTER_ID}',
    }
```

**Step 2: Smoke-check**

Run `python -c "from app import app; ctx = app.test_request_context(); ctx.push(); from flask import render_template_string; print(render_template_string('{{ admin_character_name }} -> {{ admin_evewho_url }}'))"`.

Expected: `Bernie May Doff -> https://evewho.com/character/<id>`

---

### Task 2: Create `_macros.html` with `bernie_link()` macro

**Files:**
- Create: `templates/_macros.html`

**Contents:**

```jinja
{% macro bernie_link() -%}
<span class="bernie-link-group">
    <a href="{{ admin_evewho_url }}" target="_blank" rel="noopener"
       class="text-white fw-bold text-decoration-none bernie-link"
       title="Open character info on evewho.com">{{ admin_character_name }}<sup class="ms-1 small text-info">&#x2197;</sup></a>
    <button type="button"
            class="btn btn-link btn-sm p-0 ms-1 text-secondary bernie-copy-btn"
            data-copy-value="{{ admin_character_name }}"
            title="Copy name to clipboard">&#x1F4CB;</button>
</span>
{%- endmacro %}
```

**Verification:** none yet — used in Task 4.

---

### Task 3: Add clipboard JS + minor CSS to `base.html`

**Files:**
- Modify: `templates/base.html` — add JS near the end of `<body>`, before existing script blocks

**Step 1: Add JS handler**

```html
<script>
document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-copy-value]');
    if (!btn) return;
    var value = btn.getAttribute('data-copy-value');
    navigator.clipboard.writeText(value).then(function() {
        var original = btn.innerHTML;
        btn.innerHTML = 'Copied!';
        btn.classList.add('text-success');
        setTimeout(function() {
            btn.innerHTML = original;
            btn.classList.remove('text-success');
        }, 1200);
    }).catch(function() {
        btn.title = 'Copy failed';
    });
});
</script>
```

**Step 2: Optional inline CSS for hover** — in `<style>` block or `static/style.css`:

```css
.bernie-link:hover { text-decoration: underline !important; }
.bernie-copy-btn { vertical-align: baseline; font-size: 0.95em; }
```

---

### Task 4: Replace the 5 hardcoded mentions

**Files:**
- Modify: `templates/dashboard.html:47`, `:167`, `:204`
- Modify: `templates/order_detail.html:271`
- Modify: `templates/loan_detail.html:192`

**Pattern:** at the top of each template that uses it, add `{% from '_macros.html' import bernie_link %}`. Then replace `<strong class="text-white">Bernie May Doff</strong>` with `{{ bernie_link() }}`.

Run a final grep `Grep "Bernie May Doff" templates/` — should return 0 matches (other than the import line, which doesn't match the literal name).

---

### Task 5: Visual verification

**Step 1:** Start the dev server (`python app.py`)
**Step 2:** Log in as the test member account
**Step 3:** Visit `/dashboard`, `/order/<id>` (active goal), `/loan/<id>` (active loan)
**Step 4:** For each:
- Confirm Bernie's name appears with the ↗ glyph and 📋 button
- Click the name — verify evewho opens in a new tab
- Click the copy button — verify "Copied!" feedback flashes, clipboard contains "Bernie May Doff"

---

### Task 6: Commit + push

```bash
git add app.py templates/_macros.html templates/base.html templates/dashboard.html templates/order_detail.html templates/loan_detail.html docs/plans/2026-05-17-bernie-info-link-design.md docs/plans/2026-05-17-bernie-info-link-impl.md
git commit -m "Link Bernie May Doff mentions to evewho + copy-name button"
git push origin main
```

---

## Verification checklist

- [ ] All 5 template mentions use `{{ bernie_link() }}`
- [ ] Anchor opens evewho.com/character/<id> in a new tab
- [ ] Copy button writes "Bernie May Doff" to clipboard with feedback
- [ ] No console errors on click
- [ ] Style matches existing white/bold look; subtle hover underline
