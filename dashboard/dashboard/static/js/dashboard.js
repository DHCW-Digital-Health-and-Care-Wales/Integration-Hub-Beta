/* static/js/dashboard.js
   Auto-refresh logic and live counter animations for the Integration Hub Dashboard.
*/

(function () {
  "use strict";

  const REFRESH_INTERVAL   = window.REFRESH_INTERVAL   || 30; // seconds
  const WARN_THRESHOLD     = window.QUEUE_WARN_THRESHOLD || 10;
  const CRIT_THRESHOLD     = window.QUEUE_CRIT_THRESHOLD || 50;

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

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
  /* Full rebuild on every poll so rows are added/removed as queues       */
  /* transition between healthy and non-healthy states.                   */
  /* ------------------------------------------------------------------ */
  function queueStatus(q) {
    if (q.active_message_count >= CRIT_THRESHOLD) return "critical";
    if (q.active_message_count >= WARN_THRESHOLD || q.dead_letter_message_count > 0) return "warning";
    return "healthy";
  }

  function updateQueueTable(queues) {
    const table = document.getElementById("queue-table");
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;

    // Filter to only non-healthy queues
    const nonHealthy = queues.filter(q => queueStatus(q) !== "healthy");

    // Sort: critical first, then warning; within each group by active desc
    const statusOrder = { critical: 0, warning: 1 };
    nonHealthy.sort((a, b) => {
      const diff = statusOrder[queueStatus(a)] - statusOrder[queueStatus(b)];
      if (diff !== 0) return diff;
      return b.active_message_count - a.active_message_count;
    });

    const rows = [];
    for (const q of nonHealthy) {
      const status = queueStatus(q);
      const active = q.active_message_count;
      const dlq    = q.dead_letter_message_count;
      const sched  = q.scheduled_message_count || 0;

      const activeClass = status === "critical" ? "critical"
                        : active >= WARN_THRESHOLD ? "warning" : "zero";
      const dlqClass = dlq > 0 ? "dlq-warn" : "zero";

      const tr = document.createElement("tr");
      tr.dataset.queueName = q.name;
      tr.innerHTML =
        `<td class="queue-name-cell" data-col="name">${escapeHtml(q.name)}</td>` +
        `<td class="count-cell text-end ${activeClass}" data-col="active">${active}</td>` +
        `<td class="count-cell text-end ${dlqClass}" data-col="dlq">${dlq}</td>` +
        `<td class="count-cell text-end zero" data-col="sched">${sched}</td>` +
        `<td><span class="status-badge ${status}">${status}</span></td>`;
      rows.push(tr);
    }

    // All-clear row when every queue is healthy
    if (rows.length === 0) {
      const tr = document.createElement("tr");
      const label = window.I18N_ALL_QUEUES_HEALTHY || "All queues healthy";
      tr.innerHTML =
        `<td colspan="5" class="text-center" style="padding:1rem;color:var(--accent-green);">` +
        `<i class="bi bi-check-circle me-1"></i> ${escapeHtml(label)}</td>`;
      rows.push(tr);
    }

    tbody.replaceChildren(...rows);
  }

  /* ------------------------------------------------------------------ */
  /* Alarm summary widgets                                                 */
  /* ------------------------------------------------------------------ */
  function _updateAlarmSummaryCard(prefix, summary) {
    if (!summary) return;
    const card    = document.getElementById(`${prefix}-summary-card`);
    const badge   = document.getElementById(`${prefix}-summary-badge`);
    const critEl  = document.getElementById(`${prefix}-sum-critical`);
    const suppEl  = document.getElementById(`${prefix}-sum-suppressed`);
    const hlthEl  = document.getElementById(`${prefix}-sum-healthy`);
    if (!card) return;

    const { critical = 0, suppressed = 0, healthy = 0, total = 0 } = summary;

    card.classList.remove("alarm-summary--critical", "alarm-summary--suppressed");
    if (critical > 0)        card.classList.add("alarm-summary--critical");
    else if (suppressed > 0) card.classList.add("alarm-summary--suppressed");

    if (badge) {
      badge.className = "status-badge " +
        (critical > 0 ? "critical" : suppressed > 0 ? "suppressed" : total > 0 ? "healthy" : "unknown");
      badge.innerHTML = critical > 0
        ? '<i class="bi bi-exclamation-octagon-fill me-1"></i>In Alarm'
        : suppressed > 0
        ? '<i class="bi bi-bell-slash-fill me-1"></i>Suppressed'
        : total > 0
        ? '<i class="bi bi-check-circle-fill me-1"></i>All OK'
        : '<i class="bi bi-question-circle me-1"></i>Not Configured';
    }

    if (critEl) {
      animateCounter(critEl, critical);
      critEl.className = "alarm-sum-num" + (critical > 0 ? " alarm-sum-red" : "");
    }
    if (suppEl) {
      animateCounter(suppEl, suppressed);
      suppEl.className = "alarm-sum-num" + (suppressed > 0 ? " alarm-sum-amber" : "");
    }
    if (hlthEl) animateCounter(hlthEl, healthy);
  }

  function updateAlarm1Summary(summary) { _updateAlarmSummaryCard("alarm1", summary); }
  function updateAlarm2Summary(summary) { _updateAlarmSummaryCard("alarm2", summary); }
  function updateAlarm3Summary(summary) { _updateAlarmSummaryCard("alarm3", summary); }

  function updateRetryDelays(retryRows, retryKpis) {
    if (!Array.isArray(retryRows)) return;

    const reportingEl = document.getElementById("retry-flows-reporting");
    if (reportingEl && retryKpis && typeof retryKpis.flows_reporting === "number") {
      animateCounter(reportingEl, retryKpis.flows_reporting);
    }

    const over1mEl = document.getElementById("retry-flows-over-1m");
    if (over1mEl && retryKpis && typeof retryKpis.flows_over_1m === "number") {
      animateCounter(over1mEl, retryKpis.flows_over_1m);
    }

    const tbody = document.querySelector("#retry-delay-table tbody");
    if (!tbody) return;

    if (retryRows.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center" style="padding:1rem; color:var(--text-muted);">
            No retry delays over 60 seconds were observed in the last hour.
          </td>
        </tr>
      `;
      return;
    }

    const rowsHtml = retryRows
      .filter((row) => row && row.workflow_id)
      .map((row) => {
        const wid = row.workflow_id;
        const delayClass = row.over_1m ? "critical" : (row.delay_seconds != null ? "warning" : "zero");
        const delayDisplay = row.delay_display || "Metric unavailable";
        const attemptDisplay = row.attempt != null ? String(row.attempt) : "—";
        const queueDisplay = row.queue || "—";
        const seenDisplay = row.timestamp ? String(row.timestamp).replace("T", " ").slice(0, 19) : "—";
        const statusClass = row.status || "unknown";
        const statusText = row.over_1m ? "1 min +" : (row.delay_seconds != null ? "Observed" : "Unavailable");

        return `
          <tr data-retry-workflow-id="${wid}">
            <td style="font-weight:600;">${row.flow_label || wid}</td>
            <td class="text-end count-cell ${delayClass}" id="retry-delay-${wid}">${delayDisplay}</td>
            <td class="text-end" id="retry-attempt-${wid}">${attemptDisplay}</td>
            <td class="font-mono" style="font-size:0.68rem;" id="retry-queue-${wid}">${queueDisplay}</td>
            <td class="font-mono" style="font-size:0.68rem;" id="retry-seen-${wid}">${seenDisplay}</td>
            <td><span class="status-badge ${statusClass}" id="retry-status-${wid}">${statusText}</span></td>
          </tr>
        `;
      })
      .join("");

    tbody.innerHTML = rowsHtml;
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
      updateAlarm1Summary(data.alarm1_summary);
      updateAlarm2Summary(data.alarm2_summary);
      updateAlarm3Summary(data.alarm3_summary);
      updateRetryDelays(data.retry_delays, data.retry_delay_kpis);

      if (lastRefreshedEl) {
        const d = new Date(data.refreshed_at);
        lastRefreshedEl.textContent = d.toLocaleTimeString();
      }

      flashLiveIndicator();
      document.dispatchEvent(new CustomEvent('dataupdated'));
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
