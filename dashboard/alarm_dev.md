# Alarm & Dashboard Development Log

Session date: 2026-04-30

---

## 1. Fix: `unsaved-modal-leave` button navigated to wrong page

**Issue:** Button with `id="unsaved-modal-leave"` caused a "Not Found" error instead of returning to the Alarms Summary page.

**Root cause:** `closeModal()` in `base.html` resets `_dest = null`. The leave button handler called `closeModal()` then used `_dest`, so it always navigated to `null`.

**Fix (`base.html`):**
```js
var dest = _dest;
closeModal();
window.location.href = dest;
```

---

## 2. `.gitignore` — Alarm state files

**Change:** Consolidated three individual alarm state file entries into a single glob:
```
dashboard/alarm*_state.json
```
Covers `alarm_state.json`, `alarm2_state.json`, `alarm3_state.json`.

---

## 3. Alarm 2 — Refactored to use `workflow_id`

**Previous behaviour:** Alarm 2 identified flows by `health_board` + `peer_service` pair.

**New behaviour:** Uses `workflow_id` (e.g. `phw-to-mpi`) to identify flows — consistent with Alarms 1 and 3.

**Files changed:**
- `services/alarm2.py` — KQL query now filters `Properties["workflow_id"]`; `generate_rule_id()` now returns `{workflow_id}-outgoing`
- `templates/alarm2_config.html` — Replaced two fields (Health Board + Peer Service) with single Workflow ID field
- `templates/alarm2.html` — Replaced two-column layout with single Workflow ID column
- `app.py` — Updated `alarm2_config_page` POST handler to read `workflow_id_` fields

---

## 4. Fix: Alarm 3 save button colour

**Issue:** Save button on Alarm 3 config page was red; Alarms 1 and 2 use cyan/blue.

**Fix (`alarm3_config.html`):**
```css
.btn-dash--primary { background: var(--accent-cyan); border-color: var(--accent-cyan); }
```

---

## 5. Flows page — Alarm information per flow

**Feature:** Each flow card on the Flows page now shows an **Alarms** section with three chips (Inactivity, Volume, Failures).

**Architecture:**
- `app.py` — Added `_build_alarm_map()` helper. Reads config from all 3 JSON files (fast, no Azure calls) and merges with live status from cache. Returns `{workflow_id → {alarm1, alarm2, alarm3}}`. Passed as `alarm_map` to `flows.html`.
- `flows.html` — Added alarm chips section below container apps. Each chip shows status badge + View link + configured values.
- `style.css` — Added `.flow-alarm-grid`, `.flow-alarm-chip`, `.fac--*` variant classes, `.fac-values`, `.fac-kv`, `.fac-key`, `.fac-val`.

**Chip states:**
| State | Appearance |
|---|---|
| Enabled + healthy | Green left border · ✓ OK badge |
| Enabled + critical | Red left border · ⚠ In Alarm badge |
| Enabled + suppressed | Amber left border · Suppressed badge |
| Disabled | Muted border · "Disabled" label |
| Not configured | Faded · "Not configured" |

**Configured values shown per chip:**

*Alarm 1 (Inactivity):* Day / Evening / Weekend thresholds, Cooldown, Email enabled

*Alarm 2 (Volume):* Window, Threshold (≤ N msgs), Cooldown, Email enabled

*Alarm 3 (Failures):* Window, Threshold (≥ N failures), Cooldown, Email enabled

---

## 6. Fix: Disabled alarms — View button always visible

**Issue:** View button on alarm chips in the Flows page only appeared when the alarm was enabled.

**Fix (`flows.html`):** Moved the View link outside the `{% if a.alarm_enabled %}` block so it renders regardless of enabled state.

---

## 7. Fix: Suppressed status badge — amber/orange colour

**Issue:** `.status-badge.suppressed` was defined locally in each alarm template but not in `style.css`, so it had no amber styling on the Flows page.

**Fix (`style.css`):** Added globally:
```css
.status-badge.suppressed { background: rgba(245,158,11,0.12); color: var(--accent-amber); border-color: rgba(245,158,11,0.35); }
```

---

## 8. Hot reload in VS Code

**Answer:** Two layers:
- **Python changes** — run Flask with `flask --debug run` (auto-reloads on save)
- **HTML/CSS/JS changes** — use the **Live Preview** VS Code extension, or disable browser cache in DevTools (Network → Disable cache) and use `Ctrl+R`

---

## 9. Feature: Gear (⚙) config button on Alarm rows

Added to **Alarm 1**, **Alarm 2**, and **Alarm 3** view pages.

**Changes per alarm:**

*View templates (`alarm.html`, `alarm2.html`, `alarm3.html`):*
- Added empty `<th style="width:2.5rem;">` to table header
- Added gear button `<td>` to each row linking to `{alarm_config_page}#rule-{row.id}`

*Config templates (`alarm_config.html`, `alarm2_config.html`, `alarm3_config.html`):*
- Added `id="rule-{{ r.id }}"` (or `s.id` for Alarm 1) to each rule card `<div>`

---

## 10. Feature: Highlight config card on fragment navigation

When navigating to a config page via `#rule-{id}` fragment (e.g. from the gear button), the target card is highlighted and centred on screen.

**CSS added to all three `_config.html` templates:**
```css
@keyframes rule-card-highlight {
  0%   { box-shadow: 0 0 0 2px var(--accent-cyan), 0 0 20px rgba(6,182,212,0.2); background: rgba(6,182,212,0.06); }
  65%  { box-shadow: 0 0 0 2px var(--accent-cyan), 0 0 20px rgba(6,182,212,0.2); background: rgba(6,182,212,0.06); }
  100% { box-shadow: none; background: transparent; }
}
.rule-card--highlighted { animation: rule-card-highlight 2.8s ease-out forwards; }
```

**JS added to all three `_config.html` templates:**
```js
(function () {
  var hash = window.location.hash;
  if (!hash) return;
  var card = document.querySelector(hash + '.dash-card');
  if (!card) return;
  card.classList.add('rule-card--highlighted');
  setTimeout(function () {
    var rect      = card.getBoundingClientRect();
    var cardMid   = rect.top + window.scrollY + rect.height / 2;
    var targetTop = cardMid - window.innerHeight / 2;
    window.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });
  }, 50);
})();
```

The 50ms delay lets the browser's native fragment scroll settle before overriding it to centre the card.

---

## 11. Fix: Stale toast removed

**Issue:** The `#stale-toast` div was misaligned and persisted for too long (up to 35 seconds).

**Resolution:** Removed entirely from `base.html` (HTML + JS) and `style.css`. Pages that need a refresh indicator use their own `refresh-bar` pattern (as seen on the Flows page) with a countdown timer and manual refresh button.

---

## 12. Feature: Themed number input spinners

Styled `input[type=number]` spinner controls on all alarm config pages to match the dark dashboard theme.

**Applies to:** `.dash-input` and `.cfg-num` classes

**CSS in `style.css`:**
- Spinner background: `var(--bg-secondary)`
- Arrows: cyan (`#06b6d4`) filled SVG triangles
- Width: `26px` with `border-radius: 6px` (all corners rounded)
- `margin-left: 6px` gap between input text and spinner
- `margin-right: 3px` gap between spinner and input border
- Hover: faint cyan tint on spinner area
- Firefox: default spinner hidden (`-moz-appearance: textfield`)

---

## Files Modified (full session)

| File | Changes |
|---|---|
| `dashboard/templates/base.html` | Fixed unsaved-modal leave bug; removed stale-toast HTML + JS |
| `.gitignore` | Consolidated alarm state file glob |
| `dashboard/services/alarm2.py` | Full refactor to workflow_id |
| `dashboard/templates/alarm2_config.html` | workflow_id field; rule card IDs; highlight animation + JS |
| `dashboard/templates/alarm2.html` | workflow_id column; gear button column |
| `dashboard/templates/alarm_config.html` | Rule card IDs; highlight animation + JS |
| `dashboard/templates/alarm.html` | Gear button column |
| `dashboard/templates/alarm3_config.html` | Fixed save button colour; rule card IDs; highlight animation + JS |
| `dashboard/templates/alarm3.html` | Gear button column |
| `dashboard/templates/flows.html` | Alarm chips section per flow card |
| `dashboard/app.py` | `_build_alarm_map()` helper; alarm2 workflow_id POST handler; flows_page alarm_map |
| `dashboard/static/css/style.css` | `.status-badge.suppressed`; flow alarm chip styles; spinner styles; stale-toast removed |
