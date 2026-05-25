/*
 * Container-App CPU & memory history chart.
 *
 * Clicking an .app-metric-card--clickable expands a panel below the existing
 * gauges containing two small canvas-based line charts (CPU%, Memory MiB).
 *
 * The fetch is lazy: history is only loaded when the card is first opened or
 * when the user changes the time range.  Data is cached per-card per-range
 * for the lifetime of the page to keep re-opens snappy.
 */
(function () {
  'use strict';

  // ----- chart drawing -----------------------------------------------------

  function getCssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function drawLineChart(canvas, points, opts) {
    opts = opts || {};
    var dpr = window.devicePixelRatio || 1;
    var cssW = canvas.clientWidth || canvas.parentElement.clientWidth || 300;
    var cssH = parseInt(canvas.getAttribute('height'), 10) || 90;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    canvas.style.height = cssH + 'px';

    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    var padL = 32, padR = 6, padT = 6, padB = 14;
    var plotW = cssW - padL - padR;
    var plotH = cssH - padT - padB;

    var muted = getCssVar('--text-muted', '#888');
    var border = getCssVar('--border-color', '#333');
    var stroke = opts.color || getCssVar('--accent-blue', '#12A3C9');
    var fill = opts.fill || 'rgba(18,163,201,0.15)';

    if (!points || points.length === 0) {
      ctx.fillStyle = muted;
      ctx.font = '11px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('No data', cssW / 2, cssH / 2);
      return;
    }

    var vals = points.map(function (p) { return p.v; });
    var minV = Math.min.apply(null, vals);
    var maxV = Math.max.apply(null, vals);
    if (opts.yMin !== undefined) minV = Math.min(minV, opts.yMin);
    if (opts.yMax !== undefined) maxV = Math.max(maxV, opts.yMax);
    if (minV === maxV) { maxV = minV + 1; }
    // Snap min down to zero for nicer charts of small positive values.
    if (minV > 0 && minV < (maxV - minV) * 0.5) { minV = 0; }

    function x(i) { return padL + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW); }
    function y(v) { return padT + plotH - ((v - minV) / (maxV - minV)) * plotH; }

    // Axes / gridlines
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.font = '10px system-ui, sans-serif';
    ctx.fillStyle = muted;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    var gridCount = 3;
    for (var g = 0; g <= gridCount; g++) {
      var gy = padT + (plotH * g) / gridCount;
      var gv = maxV - ((maxV - minV) * g) / gridCount;
      ctx.beginPath();
      ctx.moveTo(padL, gy);
      ctx.lineTo(padL + plotW, gy);
      ctx.globalAlpha = 0.35;
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(gv.toFixed(gv >= 100 ? 0 : 1), padL - 4, gy);
    }

    // X-axis labels — first and last timestamps
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    var firstLabel = opts.formatX ? opts.formatX(points[0].t) : '';
    var lastLabel = opts.formatX ? opts.formatX(points[points.length - 1].t) : '';
    ctx.fillText(firstLabel, padL, padT + plotH + 2);
    ctx.textAlign = 'right';
    ctx.fillText(lastLabel, padL + plotW, padT + plotH + 2);

    // Area fill
    ctx.beginPath();
    ctx.moveTo(x(0), y(points[0].v));
    for (var i = 1; i < points.length; i++) { ctx.lineTo(x(i), y(points[i].v)); }
    ctx.lineTo(x(points.length - 1), padT + plotH);
    ctx.lineTo(x(0), padT + plotH);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.moveTo(x(0), y(points[0].v));
    for (var j = 1; j < points.length; j++) { ctx.lineTo(x(j), y(points[j].v)); }
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  function formatTimestamp(iso, hours) {
    try {
      var d = new Date(iso);
      if (hours <= 24) {
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) +
             ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) { return ''; }
  }

  // ----- card behaviour ----------------------------------------------------

  function renderCharts(panel, hours, data) {
    var ts = (data && data.timestamps) || [];
    var canvases = panel.querySelectorAll('canvas.app-history-chart');
    canvases.forEach(function (cv) {
      var series = cv.getAttribute('data-series');
      var vals = (data && data[series]) || [];
      var points = ts.reduce(function (acc, t, i) {
        var v = vals[i];
        if (v != null) { acc.push({ t: t, v: Number(v) }); }
        return acc;
      }, []);
      var isCpu = series === 'cpu';
      drawLineChart(cv, points, {
        color: isCpu
          ? getCssVar('--accent-cyan', '#12A3C9')
          : getCssVar('--accent-purple', '#7e57c2'),
        fill: isCpu ? 'rgba(18,163,201,0.18)' : 'rgba(126,87,194,0.18)',
        yMin: 0,
        yMax: isCpu ? 100 : undefined,
        formatX: function (t) { return formatTimestamp(t, hours); },
      });
    });
  }

  function loadHistory(card, hours) {
    var name = card.getAttribute('data-app-name');
    var panel = card.querySelector('.app-metric-history');
    var status = panel.querySelector('.app-history-status');
    var cacheKey = name + '|' + hours;
    card._historyCache = card._historyCache || {};

    function show(data) {
      renderCharts(panel, hours, data);
      var n = (data && data.timestamps && data.timestamps.length) || 0;
      status.textContent = n ? (n + ' points') : 'no data';
    }

    if (card._historyCache[cacheKey]) {
      show(card._historyCache[cacheKey]);
      return;
    }

    status.textContent = 'Loading…';
    fetch('/api/container-app/' + encodeURIComponent(name) + '/history?hours=' + hours, {
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin',
    })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (data) {
        card._historyCache[cacheKey] = data;
        show(data);
      })
      .catch(function (err) {
        console.error('history fetch failed', err);
        status.textContent = 'error';
        renderCharts(panel, hours, { timestamps: [], cpu: [], memory_mb: [] });
      });
  }

  window.toggleAppHistory = function (card) {
    var panel = card.querySelector('.app-metric-history');
    if (!panel) return;
    var header = card.querySelector('.app-metric-card-header');
    var chev = card.querySelector('.app-metric-chevron');
    var isOpen = !panel.hasAttribute('hidden');

    if (isOpen) {
      panel.setAttribute('hidden', '');
      card.classList.remove('app-metric-card--open');
      if (header) { header.setAttribute('aria-expanded', 'false'); }
      if (chev) { chev.classList.remove('bi-chevron-down'); chev.classList.add('bi-chevron-right'); }
      return;
    }

    panel.removeAttribute('hidden');
    card.classList.add('app-metric-card--open');
    if (header) { header.setAttribute('aria-expanded', 'true'); }
    if (chev) { chev.classList.remove('bi-chevron-right'); chev.classList.add('bi-chevron-down'); }

    // Wire up range buttons once.
    if (!card._historyWired) {
      card._historyWired = true;
      panel.querySelectorAll('.btn-range').forEach(function (btn) {
        btn.addEventListener('click', function (ev) {
          ev.stopPropagation();
          panel.querySelectorAll('.btn-range').forEach(function (b) { b.classList.remove('active'); });
          btn.classList.add('active');
          loadHistory(card, parseInt(btn.getAttribute('data-hours'), 10) || 1);
        });
      });
    }

    var activeBtn = panel.querySelector('.btn-range.active') || panel.querySelector('.btn-range');
    var hours = activeBtn ? parseInt(activeBtn.getAttribute('data-hours'), 10) : 1;
    loadHistory(card, hours || 1);
  };

  // Redraw open charts on resize so they stay crisp.
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      document.querySelectorAll('.app-metric-card--open').forEach(function (card) {
        var panel = card.querySelector('.app-metric-history');
        if (!panel || panel.hasAttribute('hidden')) return;
        var activeBtn = panel.querySelector('.btn-range.active');
        var hours = activeBtn ? parseInt(activeBtn.getAttribute('data-hours'), 10) : 1;
        var name = card.getAttribute('data-app-name');
        var cached = card._historyCache && card._historyCache[name + '|' + hours];
        if (cached) renderCharts(panel, hours, cached);
      });
    }, 150);
  });
})();
