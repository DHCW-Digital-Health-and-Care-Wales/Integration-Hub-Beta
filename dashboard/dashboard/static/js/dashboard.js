/* static/js/dashboard.js
   Auto-refresh logic and live counter animations for the Integration Hub Dashboard.
*/

(function () {
  "use strict";

  const REFRESH_INTERVAL = window.REFRESH_INTERVAL || 30; // seconds

  /* ------------------------------------------------------------------ */
  /* Countdown timer                                                      */
  /* ------------------------------------------------------------------ */
  let secondsLeft = REFRESH_INTERVAL;
  const countdownEl = document.getElementById("countdown-num");
  const refreshIconEl = document.getElementById("refresh-icon");
  const lastRefreshedEl = document.getElementById("last-refreshed");
  const liveIndicator = document.getElementById("live-indicator");

  function updateCountdown() {
    if (countdownEl) countdownEl.textContent = secondsLeft;
  }

  function flashLiveIndicator() {
    if (!liveIndicator) return;
    liveIndicator.classList.add("show");
    setTimeout(() => liveIndicator.classList.remove("show"), 2000);
  }

  /* ------------------------------------------------------------------ */
  /* Number transitions                                                    */
  /* ------------------------------------------------------------------ */
  function animateCounter(el, newVal) {
    const oldVal = parseInt(el.textContent, 10);
    if (isNaN(oldVal) || oldVal === newVal) {
      el.textContent = newVal;
      return;
    }
    el.classList.add("counter-pop");
    el.textContent = newVal;
    el.addEventListener("animationend", () => el.classList.remove("counter-pop"), { once: true });
  }

  /* ------------------------------------------------------------------ */
  /* Update KPI strip                                                      */
  /* ------------------------------------------------------------------ */
  function updateKPIs(kpis) {
    const map = {
      "kpi-total-active":    kpis.total_active_messages,
      "kpi-total-dlq":       kpis.total_dlq_messages,
      "kpi-exceptions-1h":   kpis.exception_count_1h,
      "kpi-flows-healthy":   kpis.flows_healthy,
      "kpi-flows-warning":   kpis.flows_warning,
      "kpi-flows-critical":  kpis.flows_critical,
    };
    for (const [id, val] of Object.entries(map)) {
      const el = document.getElementById(id);
      if (el) animateCounter(el, val);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Update flow cards                                                     */
  /* ------------------------------------------------------------------ */
  function healthClass(health) {
    return health || "unknown";
  }

  function updateFlowCards(flows) {
    for (const flow of flows) {
      const card = document.querySelector(`[data-flow-id="${flow.id}"]`);
      if (!card) continue;

      // Health class on card (works for both table rows and detail cards)
      card.classList.remove("healthy", "warning", "critical", "unknown");
      card.classList.add(healthClass(flow.health));
      card.dataset.health = flow.health;

      // Status dot
      const dot = card.querySelector(".flow-status-dot");
      if (dot) {
        dot.classList.remove("healthy", "warning", "critical", "unknown");
        dot.classList.add(healthClass(flow.health));
      }

      // Status badge
      const badge = card.querySelector(".flow-health-badge");
      if (badge) {
        badge.className = `status-badge ${healthClass(flow.health)}`;
        badge.textContent = flow.health.toUpperCase();
      }

      // Compact table — update active/dlq totals
      const rowActive = card.querySelector(`[data-flow-active="${flow.id}"]`);
      if (rowActive) {
        const pre = flow.pre_queue || {};
        const post = flow.post_queue || {};
        const subActive = (flow.subscriptions || []).reduce((s, q) => s + (q.active || 0), 0);
        const total = (pre.active || 0) + (post.active || 0) + subActive;
        animateCounter(rowActive, total);
        rowActive.className = "text-end count-cell " +
          (total >= 50 ? "critical" : total >= 10 ? "warning" : "zero");
      }
      const rowDlq = card.querySelector(`[data-flow-dlq="${flow.id}"]`);
      if (rowDlq) {
        const pre = flow.pre_queue || {};
        const post = flow.post_queue || {};
        const subDlq = (flow.subscriptions || []).reduce((s, q) => s + (q.dlq || 0), 0);
        const total = (pre.dlq || 0) + (post.dlq || 0) + subDlq;
        animateCounter(rowDlq, total);
        rowDlq.className = "text-end count-cell " + (total > 0 ? "dlq-warn" : "zero");
      }

      // Detail card pipeline nodes (only present on flows page)
      updateQueueNode(card, "pre", flow.pre_queue);
      updateQueueNode(card, "post", flow.post_queue);
    }
  }

  function updateQueueNode(card, prefix, queueData) {
    if (!queueData || !queueData.name) return;

    const nodeBox = card.querySelector(`.pipeline-node-box[data-queue="${prefix}"]`);
    if (nodeBox) {
      nodeBox.classList.remove("healthy", "warning", "critical", "neutral", "unknown");
      nodeBox.classList.add(queueData.health || "neutral");
    }

    const activeEl = card.querySelector(`[data-queue-active="${prefix}"]`);
    if (activeEl) animateCounter(activeEl, queueData.active);

    const dlqEl = card.querySelector(`[data-queue-dlq="${prefix}"]`);
    if (dlqEl) {
      animateCounter(dlqEl, queueData.dlq);
      const pill = card.querySelector(`[data-dlq-pill="${prefix}"]`);
      if (pill) pill.style.display = queueData.dlq > 0 ? "" : "none";
    }

    // Arrow
    const arrow = card.querySelector(`.pipeline-arrow-line[data-arrow="${prefix}"]`);
    if (arrow) {
      arrow.classList.remove("healthy", "warning", "critical");
      if (queueData.health && queueData.health !== "unknown") {
        arrow.classList.add(queueData.health);
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* Update system health badge in header / navbar                        */
  /* ------------------------------------------------------------------ */
  function updateSystemHealth(health) {
    const els = document.querySelectorAll("[data-system-health]");
    for (const el of els) {
      el.className = el.className.replace(/\b(healthy|warning|critical|unknown)\b/g, "");
      el.classList.add(health);
      el.textContent = health === "healthy" ? "ALL HEALTHY"
                     : health === "warning"  ? "WARNINGS"
                     : health === "critical" ? "CRITICAL"
                     : "UNKNOWN";
    }
  }

  /* ------------------------------------------------------------------ */
  /* Update queue table                                                    */
  /* ------------------------------------------------------------------ */
  function updateQueueTable(queues) {
    for (const q of queues) {
      const row = document.querySelector(`tr[data-queue-name="${q.name}"]`);
      if (!row) continue;

      const activeEl = row.querySelector("[data-col='active']");
      const dlqEl    = row.querySelector("[data-col='dlq']");

      if (activeEl) {
        animateCounter(activeEl, q.active_message_count);
        activeEl.className = "count-cell " +
          (q.active_message_count >= 50 ? "critical" :
           q.active_message_count >= 10 ? "warning"  : "zero");
      }
      if (dlqEl) {
        animateCounter(dlqEl, q.dead_letter_message_count);
        dlqEl.className = "count-cell " +
          (q.dead_letter_message_count > 0 ? "dlq-warn" : "zero");
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* Poll /api/status                                                      */
  /* ------------------------------------------------------------------ */
  async function refreshData() {
    if (refreshIconEl) refreshIconEl.classList.add("spin-icon");
    try {
      const resp = await fetch("/api/status");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      updateKPIs(data.kpis);
      updateFlowCards(data.flows);
      updateSystemHealth(data.system_health);
      updateQueueTable(data.queues);

      if (lastRefreshedEl) {
        const d = new Date(data.refreshed_at);
        lastRefreshedEl.textContent = d.toLocaleTimeString();
      }

      flashLiveIndicator();
    } catch (err) {
      console.warn("Dashboard refresh failed:", err);
    } finally {
      if (refreshIconEl) refreshIconEl.classList.remove("spin-icon");
    }
  }

  /* ------------------------------------------------------------------ */
  /* Tick every second, refresh when countdown hits 0                     */
  /* ------------------------------------------------------------------ */
  function tick() {
    secondsLeft--;
    if (secondsLeft <= 0) {
      secondsLeft = REFRESH_INTERVAL;
      refreshData();
    }
    updateCountdown();
  }

  updateCountdown();
  setInterval(tick, 1000);

  /* ------------------------------------------------------------------ */
  /* Manual refresh button                                                 */
  /* ------------------------------------------------------------------ */
  const manualRefreshBtn = document.getElementById("manual-refresh");
  if (manualRefreshBtn) {
    manualRefreshBtn.addEventListener("click", () => {
      secondsLeft = REFRESH_INTERVAL;
      refreshData();
    });
  }

  /* ------------------------------------------------------------------ */
  /* Sortable table                                                        */
  /* ------------------------------------------------------------------ */
  function initSortableTable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const headers = table.querySelectorAll("thead th[data-sort]");
    let currentCol = null;
    let asc = true;

    headers.forEach((th) => {
      th.addEventListener("click", () => {
        const col = th.dataset.sort;
        if (currentCol === col) {
          asc = !asc;
        } else {
          asc = true;
          currentCol = col;
        }
        headers.forEach((h) => {
          h.classList.remove("sorted");
          const icon = h.querySelector(".sort-icon");
          if (icon) icon.textContent = "";
        });
        th.classList.add("sorted");
        const icon = th.querySelector(".sort-icon");
        if (icon) icon.textContent = asc ? " ↑" : " ↓";
        sortTable(table, col, asc);
      });
    });
  }

  function sortTable(table, col, asc) {
    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a, b) => {
      const aCell = a.querySelector(`td[data-col="${col}"]`);
      const bCell = b.querySelector(`td[data-col="${col}"]`);
      if (!aCell || !bCell) return 0;
      const aVal = parseInt(aCell.textContent, 10);
      const bVal = parseInt(bCell.textContent, 10);
      if (!isNaN(aVal) && !isNaN(bVal)) return asc ? aVal - bVal : bVal - aVal;
      return asc
        ? aCell.textContent.localeCompare(bCell.textContent)
        : bCell.textContent.localeCompare(aCell.textContent);
    });
    rows.forEach((r) => tbody.appendChild(r));
  }

  /* ------------------------------------------------------------------ */
  /* Flow search & filter (overview + flows pages)                       */
  /* ------------------------------------------------------------------ */
  let _flowFilter = "all";

  window.setFlowFilter = function (btn, filter) {
    _flowFilter = filter;
    document.querySelectorAll(".flow-filter-btn").forEach((b) => b.classList.remove("active"));
    if (btn) btn.classList.add("active");
    filterFlows();
  };

  window.filterFlows = function () {
    const q = (document.getElementById("flow-search")?.value || "").toLowerCase().trim();

    // ── Compact table rows (Overview page) ──────────────────────────────
    const rows = document.querySelectorAll(".flow-row");
    if (rows.length) {
      let visible = 0;
      rows.forEach((row) => {
        const label = (row.dataset.label || "").toLowerCase();
        const health = row.dataset.health || "unknown";
        const show = (!q || label.includes(q)) && (_flowFilter === "all" || health === _flowFilter);
        row.style.display = show ? "" : "none";
        if (show) visible++;
      });
      const noResults = document.getElementById("flow-no-results");
      if (noResults) noResults.style.display = visible === 0 && rows.length > 0 ? "" : "none";
      return;
    }

    // ── Grouped flow cards (Flows detail page) ──────────────────────────
    const groups = document.querySelectorAll(".flow-group");
    if (groups.length) {
      groups.forEach((group) => {
        const cards = group.querySelectorAll(".flow-detail-card");
        let groupVisible = 0;
        cards.forEach((card) => {
          const label = (card.dataset.label || "").toLowerCase();
          const health = card.dataset.health || "unknown";
          const show = (!q || label.includes(q)) && (_flowFilter === "all" || health === _flowFilter);
          card.style.display = show ? "" : "none";
          if (show) groupVisible++;
        });
        group.style.display = groupVisible > 0 ? "" : "none";
        // Auto-expand groups that have matching results when searching
        if (q && groupVisible > 0) {
          setGroupExpanded(group, true);
        }
      });
      const noResults = document.getElementById("flow-no-results");
      const totalVisible = document.querySelectorAll(".flow-group:not([style*='display: none']) .flow-detail-card:not([style*='display: none'])").length;
      if (noResults) noResults.style.display = totalVisible === 0 ? "" : "none";
      return;
    }

    // ── Flat flow cards fallback ─────────────────────────────────────────
    const cards = document.querySelectorAll(".flow-card, .flow-detail-card");
    let visible = 0;
    cards.forEach((card) => {
      const label = (card.dataset.label || "").toLowerCase();
      const health = card.dataset.health || "unknown";
      const show = (!q || label.includes(q)) && (_flowFilter === "all" || health === _flowFilter);
      card.style.display = show ? "" : "none";
      if (show) visible++;
    });
    const noResults = document.getElementById("flow-no-results");
    if (noResults) noResults.style.display = visible === 0 && cards.length > 0 ? "" : "none";
  };

  /* ------------------------------------------------------------------ */
  /* Flow group collapse / expand (Flows detail page)                   */
  /* ------------------------------------------------------------------ */
  function setGroupExpanded(groupEl, expanded) {
    const body = groupEl.querySelector(".flow-group-body");
    const chevron = groupEl.querySelector(".flow-group-chevron");
    if (!body) return;
    if (expanded) {
      body.classList.add("expanded");
      if (chevron) chevron.style.transform = "rotate(0deg)";
    } else {
      body.classList.remove("expanded");
      if (chevron) chevron.style.transform = "rotate(-90deg)";
    }
    // Persist to sessionStorage
    try {
      const states = JSON.parse(sessionStorage.getItem("flowGroupStates") || "{}");
      states[groupEl.dataset.source] = expanded;
      sessionStorage.setItem("flowGroupStates", JSON.stringify(states));
    } catch (_) { /* ignore */ }
  }

  window.toggleFlowGroup = function (headerEl) {
    const group = headerEl.closest(".flow-group");
    if (!group) return;
    const body = group.querySelector(".flow-group-body");
    setGroupExpanded(group, !body.classList.contains("expanded"));
  };

  // Restore group states from sessionStorage on load
  (function restoreGroupStates() {
    try {
      const states = JSON.parse(sessionStorage.getItem("flowGroupStates") || "{}");
      document.querySelectorAll(".flow-group").forEach((group) => {
        const src = group.dataset.source;
        if (src in states) setGroupExpanded(group, states[src]);
      });
    } catch (_) { /* ignore */ }
  })();

  initSortableTable("queue-table");

})();
