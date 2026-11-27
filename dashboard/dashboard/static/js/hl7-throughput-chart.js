/**
 * HL7 Throughput Chart — Canvas 2D Implementation
 * NHS Wales Integration Hub Dashboard
 *
 * Features:
 *   - Smooth Catmull-Rom spline curves with gradient fills
 *   - Two series: messages received (in) and messages sent (out)
 *   - Filtering by health board and service
 *   - Time range selection (24h, 3d, 7d, 14d, 30d)
 *   - Retina-aware canvas sizing
 *   - No external dependencies
 */
(function () {
  'use strict';

  // ═══════════════════════════════════════════════════════════════════════════
  // CONFIGURATION
  // ═══════════════════════════════════════════════════════════════════════════

  function isLightTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light';
  }

  function getThemeColors() {
    if (isLightTheme()) {
      return {
        canvasBg:        '#ffffff',
        bgGradientStart: 'rgba(241,245,249,0.85)',
        bgGradientEnd:   'rgba(255,255,255,0.45)',
        gridLine:        'rgba(148,163,184,0.35)',
        axisText:        '#475569',
        incomingLine:    '#0891b2',
        incomingFill:    'rgba(8,145,178,0.14)',
        outgoingLine:    '#d97706',
        outgoingFill:    'rgba(217,119,6,0.14)',
        tooltipBg:       'rgba(255,255,255,0.97)',
        tooltipBorder:   '#cbd5e1',
        tooltipText:     '#0f172a',
        tooltipShadow:   'rgba(15,23,42,0.14)',
        crosshair:       'rgba(71,85,105,0.35)',
      };
    }
    return {
      canvasBg:        'rgba(15,23,42,1)',
      bgGradientStart: 'rgba(30,41,59,0.55)',
      bgGradientEnd:   'rgba(15,23,42,0.25)',
      gridLine:        'rgba(51,65,85,0.45)',
      axisText:        '#94a3b8',
      incomingLine:    '#12A3C9',
      incomingFill:    'rgba(18,163,201,0.18)',
      outgoingLine:    '#F8CA4D',
      outgoingFill:    'rgba(248,202,77,0.16)',
      tooltipBg:       'rgba(15,23,42,0.96)',
      tooltipBorder:   'rgba(59,130,246,0.45)',
      tooltipText:     '#f1f5f9',
      tooltipShadow:   'rgba(0,0,0,0.4)',
      crosshair:       'rgba(148,163,184,0.35)',
    };
  }

  var COLORS = getThemeColors();

  var PAD = { top: 22, right: 24, bottom: 44, left: 56 };

  // ═══════════════════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════════════════

  var canvas, ctx, dpr;
  var baseCanvas, baseCtx;
  var baseDirty = true;
  var rafId = null;
  var chartData = null;
  var preparedData = null;
  var cachedRefBins = [];
  var fetchState = 'idle'; // 'idle' | 'loading' | 'loaded' | 'error'
  var errorMessage = '';
  var currentHours = 24; // Default to last 24 hours
  var currentHealthBoard = null;
  var currentService = null;

  // Hover state
  var hoverPos = null;

  // Computed chart metrics
  var chartMetrics = {
    width: 0,
    height: 0,
    minTime: 0,
    maxTime: 0,
    maxValue: 0
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // INITIALIZATION
  // ═══════════════════════════════════════════════════════════════════════════

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    canvas = document.getElementById('hl7-throughput-chart');
    if (!canvas) return;

    ctx = canvas.getContext('2d');
    baseCanvas = document.createElement('canvas');
    baseCtx = baseCanvas.getContext('2d');
    dpr = window.devicePixelRatio || 1;

    COLORS = getThemeColors();
    sizeCanvas();
    window.addEventListener('resize', onResize);
    window.addEventListener('ih-theme-change', function () {
      COLORS = getThemeColors();
      baseDirty = true;
      updateLegend();
      draw();
    });

    // Canvas event listeners
    canvas.addEventListener('mousemove', onCanvasMouseMove);
    canvas.addEventListener('mouseleave', onCanvasMouseLeave);

    // Set default active button
    document.querySelectorAll('.hl7-ts-btn').forEach(function (btn) {
      if (parseInt(btn.dataset.hours, 10) === currentHours) {
        btn.classList.add('active');
      }
    });

    // Initial data fetch
    fetchData(currentHours);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CANVAS SIZING (Retina-aware)
  // ═══════════════════════════════════════════════════════════════════════════

  function sizeCanvas() {
    var rect = canvas.parentElement.getBoundingClientRect();
    var w = Math.round(rect.width);
    var h = Math.round(rect.height);

    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);

    baseCanvas.width = w * dpr;
    baseCanvas.height = h * dpr;
    baseCtx.setTransform(1, 0, 0, 1, 0, 0);
    baseCtx.scale(dpr, dpr);
    baseDirty = true;
  }

  function cssWidth() { return canvas.width / dpr; }
  function cssHeight() { return canvas.height / dpr; }

  function onResize() {
    sizeCanvas();
    draw();
  }

  function scheduleDraw() {
    if (rafId !== null) return;
    rafId = requestAnimationFrame(function () {
      rafId = null;
      draw();
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DATA FETCHING
  // ═══════════════════════════════════════════════════════════════════════════

  function prepareSeries(series) {
    return (series || []).map(function (pt) {
      return { ms: parseISO(pt.time), value: pt.value || 0 };
    });
  }

  function prepareData(data) {
    var incoming = prepareSeries(data && data.incoming);
    var outgoing = prepareSeries(data && data.outgoing);
    var inByMs = Object.create(null);
    var outByMs = Object.create(null);
    for (var i = 0; i < incoming.length; i++) inByMs[incoming[i].ms] = incoming[i].value;
    for (var j = 0; j < outgoing.length; j++) outByMs[outgoing[j].ms] = outgoing[j].value;
    return {
      incoming: incoming,
      outgoing: outgoing,
      inByMs: inByMs,
      outByMs: outByMs
    };
  }

  function fetchData(hours) {
    var loader = document.getElementById('hl7-chart-loading');
    if (loader) loader.style.display = 'block';
    fetchState = 'loading';
    errorMessage = '';

    var url = '/api/hl7-throughput?hours=' + hours;
    if (currentHealthBoard) {
      url += '&health_board=' + encodeURIComponent(currentHealthBoard);
    }
    if (currentService) {
      url += '&service=' + encodeURIComponent(currentService);
    }

    fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        chartData = data;
        preparedData = prepareData(data);
        fetchState = 'loaded';
        errorMessage = '';
        baseDirty = true;
        if (loader) loader.style.display = 'none';
        updateLegend();
        draw();
      })
      .catch(function (err) {
        console.error('HL7 chart data fetch failed:', err);
        chartData = null;
        preparedData = null;
        cachedRefBins = [];
        fetchState = 'error';
        errorMessage = 'Failed to load metrics';
        baseDirty = true;
        if (loader) loader.style.display = 'none';
        draw();
      });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LEGEND
  // ═══════════════════════════════════════════════════════════════════════════

  function updateLegend() {
    var el = document.getElementById('hl7-chart-legend');
    if (!el || !chartData) return;

    var inTotal = sumValues(chartData.incoming);
    var outTotal = sumValues(chartData.outgoing);

    el.innerHTML =
      legendDot(COLORS.incomingLine) +
      'Received&ensp;<strong style="color:' + COLORS.incomingLine + '">' + formatNumber(inTotal) + '</strong>' +
      '<span style="margin:0 0.75rem"></span>' +
      legendDot(COLORS.outgoingLine) +
      'Sent&ensp;<strong style="color:' + COLORS.outgoingLine + '">' + formatNumber(outTotal) + '</strong>';
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DRAWING
  // ═══════════════════════════════════════════════════════════════════════════

  function renderBaseLayer() {
    var w = cssWidth();
    var h = cssHeight();

    baseCtx.fillStyle = COLORS.canvasBg;
    baseCtx.fillRect(0, 0, w, h);

    var incoming = (preparedData && preparedData.incoming) || [];
    var outgoing = (preparedData && preparedData.outgoing) || [];

    if (incoming.length === 0 && outgoing.length === 0) {
      cachedRefBins = [];
      baseDirty = false;
      return false;
    }

    // Compute layout
    chartMetrics.width = w - PAD.left - PAD.right;
    chartMetrics.height = h - PAD.top - PAD.bottom;

    // Time domain spans whichever series has data.
    var times = [];
    if (incoming.length > 0) {
      times.push(incoming[0].ms, incoming[incoming.length - 1].ms);
    }
    if (outgoing.length > 0) {
      times.push(outgoing[0].ms, outgoing[outgoing.length - 1].ms);
    }
    chartMetrics.minTime = Math.min.apply(null, times);
    chartMetrics.maxTime = Math.max.apply(null, times);
    if (chartMetrics.minTime === chartMetrics.maxTime) {
      chartMetrics.maxTime = chartMetrics.minTime + 1;
    }
    chartMetrics.maxValue = Math.max(
      maxOfSeries(incoming),
      maxOfSeries(outgoing),
      1
    );

    // Precompute reference bin screen X and O(1) values for hover tooltips.
    var ref = incoming.length >= outgoing.length ? incoming : outgoing;
    var span = chartMetrics.maxTime - chartMetrics.minTime;
    cachedRefBins = ref.map(function (pt) {
      return {
        x: PAD.left + ((pt.ms - chartMetrics.minTime) / span) * chartMetrics.width,
        ms: pt.ms,
        inVal: preparedData.inByMs[pt.ms] || 0,
        outVal: preparedData.outByMs[pt.ms] || 0
      };
    });

    // Render static layers onto offscreen canvas
    drawBackground(baseCtx);
    drawAxes(baseCtx);
    drawSeries(baseCtx, outgoing, COLORS.outgoingLine, COLORS.outgoingFill);
    drawSeries(baseCtx, incoming, COLORS.incomingLine, COLORS.incomingFill);

    baseDirty = false;
    return true;
  }

  function draw() {
    var w = cssWidth();
    var h = cssHeight();

    if (fetchState === 'idle' || fetchState === 'loading') {
      return;
    }

    if (fetchState === 'error') {
      ctx.fillStyle = COLORS.canvasBg;
      ctx.fillRect(0, 0, w, h);
      drawEmpty(errorMessage || 'Failed to load metrics');
      return;
    }

    var incoming = (preparedData && preparedData.incoming) || [];
    var outgoing = (preparedData && preparedData.outgoing) || [];
    if (incoming.length === 0 && outgoing.length === 0) {
      ctx.fillStyle = COLORS.canvasBg;
      ctx.fillRect(0, 0, w, h);
      drawEmpty('No data available');
      return;
    }

    if (baseDirty) {
      renderBaseLayer();
    }

    // Blit cached static chart layer, then paint only the hover overlay.
    ctx.drawImage(baseCanvas, 0, 0, w, h);

    if (hoverPos) {
      drawCrosshair(hoverPos);
      drawTooltip(hoverPos);
    }
  }

  function drawBackground(targetCtx) {
    var h = cssHeight();

    // Gradient
    var grad = targetCtx.createLinearGradient(0, PAD.top, 0, h - PAD.bottom);
    grad.addColorStop(0, COLORS.bgGradientStart);
    grad.addColorStop(1, COLORS.bgGradientEnd);
    targetCtx.fillStyle = grad;
    targetCtx.fillRect(PAD.left, PAD.top, chartMetrics.width, chartMetrics.height);
  }

  function drawAxes(targetCtx) {
    var h = cssHeight();
    var x0 = PAD.left;
    var y0 = h - PAD.bottom;

    // Frame
    targetCtx.strokeStyle = COLORS.gridLine;
    targetCtx.lineWidth = 1;
    targetCtx.strokeRect(x0, PAD.top, chartMetrics.width, chartMetrics.height);

    // Y-axis label
    targetCtx.save();
    targetCtx.translate(8, h / 2);
    targetCtx.rotate(-Math.PI / 2);
    targetCtx.fillStyle = COLORS.axisText;
    targetCtx.font = '0.7rem system-ui';
    targetCtx.textAlign = 'center';
    targetCtx.fillText('Messages', 0, 0);
    targetCtx.restore();

    // Y-axis gridlines and labels
    targetCtx.fillStyle = COLORS.axisText;
    targetCtx.font = '0.65rem system-ui';
    targetCtx.textAlign = 'right';
    var yTicks = [0, 0.25, 0.5, 0.75, 1.0];
    yTicks.forEach(function (tick) {
      var y = y0 - tick * chartMetrics.height;
      var val = Math.round(tick * chartMetrics.maxValue);

      // Gridline
      targetCtx.strokeStyle = COLORS.gridLine;
      targetCtx.lineWidth = 0.5;
      targetCtx.beginPath();
      targetCtx.moveTo(x0, y);
      targetCtx.lineTo(x0 + chartMetrics.width, y);
      targetCtx.stroke();

      // Label
      targetCtx.fillText(formatNumber(val), x0 - 8, y + 3);
    });

    // X-axis labels (sample timestamps)
    targetCtx.textAlign = 'center';
    var spanMs = chartMetrics.maxTime - chartMetrics.minTime;
    var multiDay = spanMs > 24 * 60 * 60 * 1000;
    var xTicks = [0, 0.25, 0.5, 0.75, 1.0];
    xTicks.forEach(function (tick) {
      var x = x0 + tick * chartMetrics.width;
      var t = chartMetrics.minTime + tick * (chartMetrics.maxTime - chartMetrics.minTime);
      var label = multiDay ? formatDateShort(t) : formatTime(t);
      targetCtx.fillText(label, x, y0 + 16);
    });
  }

  function drawSeries(targetCtx, series, lineColor, fillColor) {
    if (series.length === 0) return;

    var x0 = PAD.left;
    var y0 = cssHeight() - PAD.bottom;
    var span = chartMetrics.maxTime - chartMetrics.minTime;

    // Points
    var points = series.map(function (pt) {
      var t = pt.ms;
      var v = pt.value || 0;
      var x = x0 + ((t - chartMetrics.minTime) / span) * chartMetrics.width;
      var y = y0 - (v / chartMetrics.maxValue) * chartMetrics.height;
      return { x: x, y: y, value: v, time: t };
    });

    if (points.length < 2) {
      // Just draw points
      targetCtx.fillStyle = lineColor;
      points.forEach(function (pt) {
        targetCtx.beginPath();
        targetCtx.arc(pt.x, pt.y, 2, 0, 2 * Math.PI);
        targetCtx.fill();
      });
      return;
    }

    // Draw filled area
    targetCtx.fillStyle = fillColor;
    targetCtx.beginPath();
    targetCtx.moveTo(points[0].x, y0);

    // Curve through points
    var cp = {};
    for (var i = 0; i < points.length; i++) {
      catmullRomControlPoints(points, i, cp);
      if (i === 0) {
        targetCtx.quadraticCurveTo(cp.c1x, cp.c1y, points[i + 1].x, points[i + 1].y);
      } else if (i < points.length - 1) {
        targetCtx.bezierCurveTo(cp.c1x, cp.c1y, cp.c2x, cp.c2y, points[i + 1].x, points[i + 1].y);
      }
    }

    targetCtx.lineTo(points[points.length - 1].x, y0);
    targetCtx.closePath();
    targetCtx.fill();

    // Draw line
    targetCtx.strokeStyle = lineColor;
    targetCtx.lineWidth = 2;
    targetCtx.lineJoin = 'round';
    targetCtx.lineCap = 'round';
    targetCtx.beginPath();
    targetCtx.moveTo(points[0].x, points[0].y);

    for (var j = 0; j < points.length; j++) {
      catmullRomControlPoints(points, j, cp);
      if (j === 0) {
        targetCtx.quadraticCurveTo(cp.c1x, cp.c1y, points[j + 1].x, points[j + 1].y);
      } else if (j < points.length - 1) {
        targetCtx.bezierCurveTo(cp.c1x, cp.c1y, cp.c2x, cp.c2y, points[j + 1].x, points[j + 1].y);
      }
    }

    targetCtx.stroke();

    // Draw data points
    targetCtx.fillStyle = lineColor;
    points.forEach(function (pt) {
      targetCtx.beginPath();
      targetCtx.arc(pt.x, pt.y, 2.5, 0, 2 * Math.PI);
      targetCtx.fill();
    });
  }

  function findNearestBin(bins, targetX) {
    var lo = 0;
    var hi = bins.length - 1;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (bins[mid].x < targetX) lo = mid + 1;
      else hi = mid;
    }
    var best = lo;
    if (lo > 0 && Math.abs(bins[lo - 1].x - targetX) < Math.abs(bins[lo].x - targetX)) {
      best = lo - 1;
    }
    return best;
  }

  function drawCrosshair(pos) {
    var y0 = cssHeight() - PAD.bottom;

    ctx.strokeStyle = COLORS.crosshair;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);

    // Vertical line
    ctx.beginPath();
    ctx.moveTo(pos.x, PAD.top);
    ctx.lineTo(pos.x, y0);
    ctx.stroke();

    ctx.setLineDash([]);
  }

  function drawTooltip(pos) {
    if (!cachedRefBins.length) return;

    var nearestIdx = findNearestBin(cachedRefBins, pos.x);
    var bin = cachedRefBins[nearestIdx];
    if (Math.abs(bin.x - pos.x) > 30) return;

    var nearestX = bin.x;
    var binTime = bin.ms;
    var inVal = bin.inVal;
    var outVal = bin.outVal;

    var line1 = formatDateTime(binTime);
    var line2 = 'Received: ' + formatNumber(inVal);
    var line3 = 'Sent: ' + formatNumber(outVal);

    // Measure widest line
    ctx.font = '0.72rem system-ui';
    var tw = Math.max(
      ctx.measureText(line1).width,
      ctx.measureText(line2).width,
      ctx.measureText(line3).width
    ) + 20;
    var th = 56;

    var tx = Math.max(PAD.left + 8, Math.min(nearestX - tw / 2, cssWidth() - PAD.right - 8 - tw));
    var ty = PAD.top + 8;

    // Draw tooltip box with shadow
    ctx.shadowColor = COLORS.tooltipShadow;
    ctx.shadowBlur = 8;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 2;

    ctx.fillStyle = COLORS.tooltipBg;
    ctx.fillRect(tx, ty, tw, th);

    ctx.shadowColor = 'transparent';

    ctx.strokeStyle = COLORS.tooltipBorder;
    ctx.lineWidth = 1;
    ctx.strokeRect(tx, ty, tw, th);

    // Text
    ctx.textAlign = 'left';
    var lx = tx + 10;
    ctx.fillStyle = COLORS.tooltipText;
    ctx.font = '600 0.72rem system-ui';
    ctx.fillText(line1, lx, ty + 16);
    ctx.font = '0.72rem system-ui';
    ctx.fillStyle = COLORS.incomingLine;
    ctx.fillText(line2, lx, ty + 34);
    ctx.fillStyle = COLORS.outgoingLine;
    ctx.fillText(line3, lx, ty + 50);
  }

  function drawEmpty(msg) {
    var w = cssWidth();
    var h = cssHeight();
    ctx.fillStyle = COLORS.axisText;
    ctx.font = '0.8rem system-ui';
    ctx.textAlign = 'center';
    ctx.fillText(msg, w / 2, h / 2);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // MOUSE EVENTS
  // ═══════════════════════════════════════════════════════════════════════════

  function onCanvasMouseMove(e) {
    if (!canvas) return;
    var rect = canvas.getBoundingClientRect();
    hoverPos = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    };
    scheduleDraw();
  }

  function onCanvasMouseLeave() {
    hoverPos = null;
    scheduleDraw();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GLOBAL FUNCTIONS (called from HTML)
  // ═══════════════════════════════════════════════════════════════════════════

  window.changeHL7Timespan = function (hours) {
    document.querySelectorAll('.hl7-ts-btn').forEach(function (btn) {
      btn.classList.remove('active');
    });
    document.querySelector('[data-hours="' + hours + '"].hl7-ts-btn').classList.add('active');
    currentHours = hours;
    fetchData(currentHours);
  };

  window.applyHL7Filters = function () {
    currentHealthBoard = document.getElementById('hl7-hb-filter')?.value || null;
    currentService = document.getElementById('hl7-service-filter')?.value || null;
    fetchData(currentHours);
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // UTILITIES
  // ═══════════════════════════════════════════════════════════════════════════

  function parseISO(isoString) {
    return new Date(isoString).getTime();
  }

  function maxOfSeries(series) {
    var max = 0;
    series.forEach(function (pt) {
      if (pt.value > max) max = pt.value;
    });
    return max;
  }

  function sumValues(series) {
    var sum = 0;
    series.forEach(function (pt) {
      sum += pt.value || 0;
    });
    return sum;
  }

  function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
  }

  function formatTime(ms) {
    var d = new Date(ms);
    var hours = d.getHours().toString().padStart(2, '0');
    var mins = d.getMinutes().toString().padStart(2, '0');
    return hours + ':' + mins;
  }

  function formatDateTime(ms) {
    var d = new Date(ms);
    var date = d.getDate().toString().padStart(2, '0');
    var month = (d.getMonth() + 1).toString().padStart(2, '0');
    var hours = d.getHours().toString().padStart(2, '0');
    var mins = d.getMinutes().toString().padStart(2, '0');
    return date + '/' + month + ' ' + hours + ':' + mins;
  }

  function formatDateShort(ms) {
    var d = new Date(ms);
    var date = d.getDate().toString().padStart(2, '0');
    var month = (d.getMonth() + 1).toString().padStart(2, '0');
    return date + '/' + month;
  }

  function legendDot(color) {
    return '<span style="display:inline-block; width:12px; height:12px; background:' + color + '; border-radius:2px; margin-right:6px; vertical-align:middle;"></span>';
  }

  function catmullRomControlPoints(points, i, out) {
    var p0 = points[Math.max(0, i - 1)];
    var p1 = points[i];
    var p2 = points[Math.min(points.length - 1, i + 1)];
    var p3 = points[Math.min(points.length - 1, i + 2)];

    var t = 0.5;

    out.c1x = p1.x + t * (p2.x - p0.x) / 2;
    out.c1y = p1.y + t * (p2.y - p0.y) / 2;

    out.c2x = p2.x - t * (p3.x - p1.x) / 2;
    out.c2y = p2.y - t * (p3.y - p1.y) / 2;
  }
})();
