/**
 * Shared schedule-pause modal plus Resume / Cancel actions for alarm pauses.
 *
 * Markup, translated strings and endpoint URLs come from templates/partials/pause_modal.html
 * (JSON in #pauseModalConfig). Behaviour is attached with delegated click handlers, so any
 * page element can opt in via data attributes:
 *
 *   data-pause-open                 open the modal; optionally with data-alarm-type,
 *                                   data-rule-id, data-rule-name, data-workflow-id to preselect
 *                                   a rule, and data-scope (rule|flow|flows|all) to preselect scope
 *   data-pause-resume               resume one rule (needs data-alarm-type + data-rule-id); if the
 *                                   rule is covered by a wider pause the server returns 409 and we
 *                                   redirect to that pause on the Alarm Pauses page
 *   data-pause-cancel="<pause_id>"  cancel a scheduled pause / end an active one
 *                                   (data-pause-status selects the confirmation text)
 *
 * Date/time inputs are sent as naive "YYYY-MM-DDTHH:MM" strings; the server interprets them
 * as UK time, so the browser's own timezone never affects when a pause starts or ends.
 */
(function () {
  'use strict';

  const cfgEl = document.getElementById('pauseModalConfig');
  const modalEl = document.getElementById('pauseModal');
  if (!cfgEl || !modalEl) return;

  const cfg = JSON.parse(cfgEl.textContent);
  const t = cfg.i18n;
  // Remembered locally only as a convenience; the dashboard has no user identity.
  const REQUESTED_BY_KEY = 'ihub.pause.requestedBy';

  const $ = (id) => document.getElementById(id);
  /** Replace {name} placeholders in a translated string. */
  const fmt = (s, vars) => s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));

  let options = null;           // {flow_options, rule_options} fetched lazily
  let presetRule = null;        // {alarm_type, rule_id, rule_name, workflow_id} when opened from a row
  let durationMinutes = 60;
  let customDuration = false;

  /** Return the value of the checked radio in group `name`, or null. */
  function radioValue(name) {
    const el = modalEl.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : null;
  }

  /** Check the radio in group `name` whose value is `value`. */
  function setRadio(name, value) {
    modalEl.querySelectorAll('input[name="' + name + '"]').forEach((el) => { el.checked = el.value === value; });
  }

  function show(el, visible) { el.style.display = visible ? '' : 'none'; }

  /** Show or hide the inline error message (empty `msg` hides it). */
  function showError(msg) {
    const err = $('pmError');
    err.textContent = msg;
    show(err, Boolean(msg));
  }

  /** Fetch flow/rule picker options once per page load and cache them. */
  function loadOptions() {
    if (options) return Promise.resolve(options);
    return fetch(cfg.urls.options)
      .then((r) => r.json())
      .then((data) => { options = data; return data; });
  }

  /** Rebuild the rule dropdown, single-flow dropdown and multi-flow checkbox list. */
  function populateOptions() {
    const ruleSel = $('pmRuleSelect');
    ruleSel.innerHTML = '';
    options.rule_options.forEach((o) => {
      const opt = document.createElement('option');
      opt.value = o.alarm_type + '|' + o.rule_id;
      opt.textContent = o.label;
      ruleSel.appendChild(opt);
    });

    const flowSel = $('pmFlowSelect');
    flowSel.innerHTML = '';
    options.flow_options.forEach((o) => {
      const opt = document.createElement('option');
      opt.value = o.id;
      opt.textContent = o.label === o.id ? o.label : o.label + ' (' + o.id + ')';
      flowSel.appendChild(opt);
    });

    const list = $('pmFlowList');
    list.innerHTML = '';
    if (!options.flow_options.length) {
      list.textContent = t.noFlows;
    }
    options.flow_options.forEach((o) => {
      const label = document.createElement('label');
      label.dataset.search = (o.label + ' ' + o.id).toLowerCase();
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = o.id;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(' ' + (o.label === o.id ? o.label : o.label + ' (' + o.id + ')')));
      list.appendChild(label);
    });
  }

  /** Return the display label for a workflow id (falls back to the id). */
  function flowLabel(id) {
    const o = options && options.flow_options.find((f) => f.id === id);
    return o ? o.label : id;
  }

  /** Return the workflow ids ticked in the multi-flow list. */
  function selectedFlows() {
    return Array.from($('pmFlowList').querySelectorAll('input[type=checkbox]:checked')).map((cb) => cb.value);
  }

  /** Highlight a duration pill; `minutes` is a number or 'custom'. */
  function selectDuration(minutes) {
    modalEl.querySelectorAll('.duration-opt').forEach((b) => {
      b.classList.toggle('duration-opt--selected', b.dataset.minutes === String(minutes));
    });
    customDuration = minutes === 'custom';
    show($('pmCustomRow'), customDuration);
    if (!customDuration) durationMinutes = minutes;
  }

  /** Return the chosen duration in minutes (0 when the custom value is invalid). */
  function currentDuration() {
    if (!customDuration) return durationMinutes;
    const v = parseInt($('pmCustomValue').value, 10);
    return v > 0 ? v * parseInt($('pmCustomUnit').value, 10) : 0;
  }

  /** Format minutes as "N min" or "N h" for the summary line. */
  function durationText(mins) {
    return mins < 60 || mins % 60 !== 0 ? fmt(t.minutes, { n: mins }) : fmt(t.hours, { n: mins / 60 });
  }

  /** Show only the inputs relevant to the selected scope / start / end options. */
  function refreshVisibility() {
    const scope = radioValue('pmScope');
    show($('pmRuleRow'), scope === 'rule');
    show($('pmRuleFixed'), scope === 'rule' && Boolean(presetRule));
    show($('pmRuleSelect'), scope === 'rule' && !presetRule);
    show($('pmFlowRow'), scope === 'flow');
    show($('pmFlowsRow'), scope === 'flows');
    show($('pmAllRow'), scope === 'all');

    const start = radioValue('pmStart');
    show($('pmStartAt'), start === 'later');

    const end = radioValue('pmEnd');
    show($('pmDurationRow'), end === 'duration');
    show($('pmCustomRow'), end === 'duration' && customDuration);
    show($('pmEndAt'), end === 'until');
    show($('pmIndefiniteHint'), end === 'indefinite');

    $('pmConfirmLabel').textContent = start === 'later' ? t.schedule : t.pause;
    refreshSummary();
  }

  /** Render a datetime-local value for display (already UK time as entered). */
  function londonDisplay(value) {
    return value ? value.replace('T', ' ') : '';
  }

  /** Update the plain-English "Pause X from Y for Z" confirmation line. */
  function refreshSummary() {
    const scope = radioValue('pmScope');
    const start = radioValue('pmStart') === 'later' ? londonDisplay($('pmStartAt').value) || '…' : t.now;
    const endMode = radioValue('pmEnd');
    let end;
    if (endMode === 'indefinite') end = t.untilCancelled;
    else if (endMode === 'until') end = fmt(t.until, { time: londonDisplay($('pmEndAt').value) || '…' });
    else end = fmt(t.forDuration, { duration: durationText(currentDuration() || 0) });

    let text;
    if (scope === 'all') text = fmt(t.summaryAll, { start: start, end: end });
    else if (scope === 'flows') text = fmt(t.summaryFlows, { count: selectedFlows().length, start: start, end: end });
    else if (scope === 'flow') text = fmt(t.summaryRule, { target: flowLabel($('pmFlowSelect').value), start: start, end: end });
    else {
      const sel = $('pmRuleSelect');
      const target = presetRule ? presetRule.rule_name : (sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : '');
      text = fmt(t.summaryRule, { target: target, start: start, end: end });
    }
    $('pmSummary').textContent = text;
  }

  /** Reset the form to defaults, preselecting the rule/flow/scope described by `opener`'s data attributes. */
  function resetForm(opener) {
    presetRule = opener && opener.dataset.ruleId
      ? {
          alarm_type: opener.dataset.alarmType,
          rule_id: opener.dataset.ruleId,
          rule_name: opener.dataset.ruleName || opener.dataset.ruleId,
          workflow_id: opener.dataset.workflowId || '',
        }
      : null;

    $('pmRuleFixed').textContent = presetRule ? presetRule.rule_name : '';
    setRadio('pmScope', (opener && opener.dataset.scope) || (presetRule ? 'rule' : 'flow'));
    const presetFlow = (opener && opener.dataset.workflowId) || '';
    if (presetFlow) {
      $('pmFlowSelect').value = presetFlow;
    }
    $('pmFlowList').querySelectorAll('input[type=checkbox]').forEach((cb) => {
      cb.checked = Boolean(presetFlow) && cb.value === presetFlow;
    });
    $('pmFlowFilter').value = '';
    $('pmFlowList').querySelectorAll('label').forEach((l) => show(l, true));
    setRadio('pmStart', 'now');
    setRadio('pmEnd', 'duration');
    $('pmStartAt').value = '';
    $('pmEndAt').value = '';
    selectDuration(60);
    $('pmReason').value = '';
    $('pmRequestedBy').value = localStorage.getItem(REQUESTED_BY_KEY) || '';
    showError('');
    refreshVisibility();
  }

  /**
   * Build the POST /api/alarm-pauses body from the form.
   * Returns {payload} on success or {error} with a translated message; the server re-validates everything.
   * "Single flow" is sent as scope "flows" with one target.
   */
  function buildPayload() {
    const scope = radioValue('pmScope');
    const payload = {
      reason: $('pmReason').value.trim(),
      requested_by: $('pmRequestedBy').value.trim(),
    };

    if (scope === 'rule') {
      let alarmType, ruleId;
      if (presetRule) {
        alarmType = presetRule.alarm_type;
        ruleId = presetRule.rule_id;
      } else {
        [alarmType, ruleId] = ($('pmRuleSelect').value || '|').split('|');
      }
      if (!ruleId) return { error: t.noTarget };
      payload.scope_type = 'rule';
      payload.targets = [{ alarm_type: alarmType, rule_id: ruleId }];
    } else if (scope === 'flow') {
      if (!$('pmFlowSelect').value) return { error: t.noTarget };
      payload.scope_type = 'flows';
      payload.targets = [$('pmFlowSelect').value];
    } else if (scope === 'flows') {
      const flows = selectedFlows();
      if (!flows.length) return { error: t.noTarget };
      payload.scope_type = 'flows';
      payload.targets = flows;
    } else {
      payload.scope_type = 'all';
      payload.targets = [];
    }

    if (radioValue('pmStart') === 'later') {
      if (!$('pmStartAt').value) return { error: t.needStart };
      payload.start = $('pmStartAt').value;
    } else {
      payload.start = null;
    }

    const endMode = radioValue('pmEnd');
    payload.end_mode = endMode;
    if (endMode === 'until') {
      if (!$('pmEndAt').value) return { error: t.needEnd };
      payload.end = $('pmEndAt').value;
    } else if (endMode === 'duration') {
      const mins = currentDuration();
      if (!mins || mins < 1) return { error: t.needDuration };
      payload.duration_minutes = mins;
    }

    if (!payload.reason) return { error: t.needReason };
    if (!payload.requested_by) return { error: t.needRequestedBy };
    return { payload: payload };
  }

  /** POST JSON and resolve to {status, data} (data is the parsed JSON response). */
  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    }).then((r) => r.json().then((data) => ({ status: r.status, data: data })));
  }

  /* ── Modal wiring ── */
  document.addEventListener('click', function (e) {
    const opener = e.target.closest('[data-pause-open]');
    if (!opener) return;
    e.preventDefault();
    loadOptions()
      .then(function () {
        populateOptions();
        resetForm(opener);
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
      })
      .catch(function () { window.alert(t.networkError); });
  });

  modalEl.addEventListener('change', refreshVisibility);
  modalEl.addEventListener('input', function (e) {
    if (e.target.id === 'pmFlowFilter') {
      const q = e.target.value.trim().toLowerCase();
      $('pmFlowList').querySelectorAll('label').forEach((l) => show(l, !q || l.dataset.search.includes(q)));
      return;
    }
    refreshSummary();
  });

  $('pmDurationPicker').addEventListener('click', function (e) {
    const btn = e.target.closest('.duration-opt');
    if (!btn) return;
    selectDuration(btn.dataset.minutes === 'custom' ? 'custom' : parseInt(btn.dataset.minutes, 10));
    refreshVisibility();
  });

  $('pmConfirm').addEventListener('click', function () {
    const built = buildPayload();
    if (built.error) { showError(built.error); return; }
    showError('');
    const btn = this;
    btn.disabled = true;
    localStorage.setItem(REQUESTED_BY_KEY, built.payload.requested_by);
    postJson(cfg.urls.create, built.payload)
      .then(function (res) {
        if (res.data.ok) {
          window.location.reload();
        } else {
          showError(res.data.error || t.genericError);
        }
      })
      .catch(function () { showError(t.networkError); })
      .finally(function () { btn.disabled = false; });
  });

  /* ── Resume a single rule ── */
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-pause-resume]');
    if (!btn) return;
    e.preventDefault();
    const url = cfg.urls.unpause[btn.dataset.alarmType];
    if (!url) return;
    btn.disabled = true;
    postJson(url.replace('__ID__', encodeURIComponent(btn.dataset.ruleId)))
      .then(function (res) {
        if (res.data.ok) window.location.reload();
        else if (res.data.manage_url) window.location.href = res.data.manage_url;
        else window.alert(res.data.error || t.genericError);
      })
      .catch(function () { window.alert(t.networkError); })
      .finally(function () { btn.disabled = false; });
  });

  /* ── Cancel a scheduled pause / end an active one ── */
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-pause-cancel]');
    if (!btn) return;
    e.preventDefault();
    if (!window.confirm(btn.dataset.pauseStatus === 'scheduled' ? t.confirmCancel : t.confirmEnd)) return;
    btn.disabled = true;
    postJson(cfg.urls.cancel.replace('__ID__', encodeURIComponent(btn.dataset.pauseCancel)))
      .then(function (res) {
        if (res.data.ok) window.location.reload();
        else window.alert(res.data.error || t.genericError);
      })
      .catch(function () { window.alert(t.networkError); })
      .finally(function () { btn.disabled = false; });
  });
}());
