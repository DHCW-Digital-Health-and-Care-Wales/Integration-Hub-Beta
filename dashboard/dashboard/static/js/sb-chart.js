/**
 * Service Bus Messages chart — Canvas 2D line chart.
 * Replicates the Azure portal "Messages" graph.
 * No external chart libraries — pure Canvas 2D.
 */
(function () {
  'use strict';

  // ── Theme tokens (match style.css dark theme) ────────────────────────────
  var COLORS = {
    bg:          '#1e293b',
    gridLine:    'rgba(51,65,85,0.5)',
    axisText:    '#94a3b8',
    incoming:    '#3b82f6',  // accent-blue
    outgoing:    '#d946ef',  // magenta / pink
    tooltip:     '#0f172a',
    tooltipText: '#f1f5f9',
  };

  var canvas, ctx, chartData, tooltip, dpr;
  var currentHours = 1;

  // ── Initialise on DOM ready ──────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    canvas = document.getElementById('messages-chart');
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    dpr = window.devicePixelRatio || 1;

    sizeCanvas();
    window.addEventListener('resize', function () { sizeCanvas(); draw(); });
    canvas.addEventListener('mousemove', onHover);
    canvas.addEventListener('mouseleave', function () { tooltip = null; draw(); });

    // Timespan buttons
    document.querySelectorAll('.metrics-ts-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.metrics-ts-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        currentHours = parseInt(btn.dataset.hours, 10);
        fetchMetrics(currentHours);
      });
    });

    fetchMetrics(currentHours);
  });

  // ── Canvas sizing (retina-aware) ─────────────────────────────────────────
  function sizeCanvas() {
    var rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    ctx.scale(dpr, dpr);
  }

  // ── Fetch metrics from API ───────────────────────────────────────────────
  function fetchMetrics(hours) {
    var loader = document.getElementById('messages-chart-loading');
    if (loader) loader.style.display = 'block';

    var url = '/api/servicebus-metrics?hours=' + hours;
    if (window.__chartQueueFilter) url += '&queue=' + encodeURIComponent(window.__chartQueueFilter);
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        chartData = data;
        if (loader) loader.style.display = 'none';
        updateLegend();
        draw();
      })
      .catch(function () {
        chartData = null;
        if (loader) loader.style.display = 'none';
        drawEmpty('Failed to load metrics');
      });
  }

  // ── Legend ────────────────────────────────────────────────────────────────
  function updateLegend() {
    var el = document.getElementById('messages-chart-legend');
    if (!el || !chartData) return;

    var inTotal = chartData.incoming.reduce(function (s, p) { return s + p.value; }, 0);
    var outTotal = chartData.outgoing.reduce(function (s, p) { return s + p.value; }, 0);

    el.innerHTML =
      '<span style="display:flex;align-items:center;gap:5px;">' +
        '<span style="width:12px;height:3px;background:' + COLORS.incoming + ';border-radius:2px;"></span>' +
        'Incoming Messages&ensp;<strong>' + inTotal + '</strong></span>' +
      '<span style="display:flex;align-items:center;gap:5px;">' +
        '<span style="width:12px;height:3px;background:' + COLORS.outgoing + ';border-radius:2px;"></span>' +
        'Outgoing Messages&ensp;<strong>' + outTotal + '</strong></span>';
  }

  // ── Draw empty state ─────────────────────────────────────────────────────
  function drawEmpty(msg) {
    var w = canvas.width / dpr, h = canvas.height / dpr;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = COLORS.axisText;
    ctx.font = '13px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(msg || 'No data', w / 2, h / 2);
  }

  // ── Main draw ────────────────────────────────────────────────────────────
  function draw() {
    if (!chartData) return;

    var w = canvas.width / dpr;
    var h = canvas.height / dpr;
    ctx.clearRect(0, 0, w, h);

    var incoming = chartData.incoming || [];
    var outgoing = chartData.outgoing || [];
    if (incoming.length === 0 && outgoing.length === 0) {
      drawEmpty('No message data for this period');
      return;
    }

    // Chart area padding
    var pad = { top: 16, right: 20, bottom: 40, left: 52 };
    var cw = w - pad.left - pad.right;
    var ch = h - pad.top - pad.bottom;

    // Build unified time axis
    var allPoints = incoming.concat(outgoing);
    var times = allPoints.map(function (p) { return new Date(p.time).getTime(); });
    var minT = Math.min.apply(null, times);
    var maxT = Math.max.apply(null, times);
    if (minT === maxT) maxT = minT + 60000;

    // Y axis max
    var allVals = allPoints.map(function (p) { return p.value; });
    var maxVal = Math.max.apply(null, allVals.concat([1]));
    // Round up to a nice number
    var yStep = niceStep(maxVal);
    var yMax = Math.ceil(maxVal / yStep) * yStep;
    if (yMax === 0) yMax = 1;

    // ── Grid lines and Y labels ──
    ctx.strokeStyle = COLORS.gridLine;
    ctx.lineWidth = 1;
    ctx.fillStyle = COLORS.axisText;
    ctx.font = '11px ' + (getComputedStyle(document.body).getPropertyValue('--font-mono') || 'monospace');
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    var yTicks = Math.min(6, Math.ceil(yMax / yStep));
    for (var i = 0; i <= yTicks; i++) {
      var yVal = i * yStep;
      var y = pad.top + ch - (yVal / yMax) * ch;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
      ctx.fillText(formatNum(yVal), pad.left - 8, y);
    }

    // ── X axis time labels ──
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    var xLabelCount = Math.min(8, incoming.length);
    var xInterval = Math.max(1, Math.floor(incoming.length / xLabelCount));
    for (var xi = 0; xi < incoming.length; xi += xInterval) {
      var t = new Date(incoming[xi].time);
      var x = pad.left + ((t.getTime() - minT) / (maxT - minT)) * cw;
      ctx.fillStyle = COLORS.gridLine;
      ctx.beginPath();
      ctx.moveTo(x, pad.top);
      ctx.lineTo(x, pad.top + ch);
      ctx.stroke();
      ctx.fillStyle = COLORS.axisText;
      ctx.fillText(formatTime(t, currentHours), x, pad.top + ch + 6);
    }

    // ── Draw lines ──
    drawLine(incoming, COLORS.incoming, minT, maxT, yMax, pad, cw, ch);
    drawLine(outgoing, COLORS.outgoing, minT, maxT, yMax, pad, cw, ch);

    // ── Tooltip ──
    if (tooltip) drawTooltip(incoming, outgoing, minT, maxT, yMax, pad, cw, ch);
  }

  function drawLine(points, color, minT, maxT, yMax, pad, cw, ch) {
    if (points.length === 0) return;

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.beginPath();

    var coords = [];
    for (var i = 0; i < points.length; i++) {
      var t = new Date(points[i].time).getTime();
      var x = pad.left + ((t - minT) / (maxT - minT)) * cw;
      var y = pad.top + ch - (points[i].value / yMax) * ch;
      coords.push({ x: x, y: y });
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Dots at each point
    ctx.fillStyle = color;
    for (var k = 0; k < coords.length; k++) {
      ctx.beginPath();
      ctx.arc(coords[k].x, coords[k].y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // ── Tooltip on hover ─────────────────────────────────────────────────────
  function onHover(e) {
    var rect = canvas.getBoundingClientRect();
    tooltip = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    draw();
  }

  function drawTooltip(incoming, outgoing, minT, maxT, yMax, pad, cw, ch) {
    if (!tooltip || incoming.length === 0) return;

    var mx = tooltip.x;
    // Find nearest incoming point by x
    var closest = null;
    var closestDist = Infinity;
    for (var i = 0; i < incoming.length; i++) {
      var t = new Date(incoming[i].time).getTime();
      var px = pad.left + ((t - minT) / (maxT - minT)) * cw;
      var d = Math.abs(px - mx);
      if (d < closestDist) { closestDist = d; closest = i; }
    }
    if (closest === null || closestDist > 30) return;

    var pt = new Date(incoming[closest].time);
    var inVal = incoming[closest].value;
    var outVal = (outgoing[closest] || {}).value || 0;
    var px = pad.left + ((pt.getTime() - minT) / (maxT - minT)) * cw;

    // Vertical guide
    ctx.strokeStyle = 'rgba(148,163,184,0.3)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(px, pad.top);
    ctx.lineTo(px, pad.top + ch);
    ctx.stroke();
    ctx.setLineDash([]);

    // Tooltip box
    var timeStr = formatTime(pt, currentHours, true);
    var lines = [timeStr, 'In: ' + inVal, 'Out: ' + outVal];
    ctx.font = '11px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif';
    var tw = Math.max.apply(null, lines.map(function (l) { return ctx.measureText(l).width; })) + 16;
    var th = lines.length * 18 + 12;
    var tx = Math.min(px + 10, (canvas.width / dpr) - tw - 8);
    var ty = Math.max(pad.top, tooltip.y - th / 2);

    ctx.fillStyle = COLORS.tooltip;
    ctx.strokeStyle = 'rgba(51,65,85,0.8)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(tx, ty, tw, th, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = COLORS.tooltipText;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    for (var li = 0; li < lines.length; li++) {
      if (li === 1) ctx.fillStyle = COLORS.incoming;
      if (li === 2) ctx.fillStyle = COLORS.outgoing;
      ctx.fillText(lines[li], tx + 8, ty + 6 + li * 18);
    }
    ctx.textAlign = 'center'; // reset
  }

  // ── Helpers ──────────────────────────────────────────────────────────────
  function niceStep(max) {
    if (max <= 5) return 1;
    if (max <= 10) return 2;
    if (max <= 25) return 5;
    if (max <= 50) return 10;
    if (max <= 100) return 20;
    if (max <= 500) return 100;
    return Math.pow(10, Math.floor(Math.log10(max)));
  }

  function formatNum(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
  }

  function formatTime(d, hours, full) {
    var hh = String(d.getHours()).padStart(2, '0');
    var mm = String(d.getMinutes()).padStart(2, '0');
    if (hours <= 24) {
      return hh + ':' + mm;
    }
    var dd = String(d.getDate()).padStart(2, '0');
    var mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()];
    if (full) return dd + ' ' + mon + ' ' + hh + ':' + mm;
    return dd + ' ' + mon;
  }

}());
