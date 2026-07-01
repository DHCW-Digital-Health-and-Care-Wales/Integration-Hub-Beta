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

  var COLORS = {
    // Background gradient
    bgGradientStart: 'rgba(30,41,59,0.55)',
    bgGradientEnd:   'rgba(15,23,42,0.25)',
    // Grid & Axes
    gridLine:        'rgba(51,65,85,0.45)',
    axisText:        '#94a3b8',
    // Series
    incomingLine:    '#12A3C9',
    incomingFill:    'rgba(18,163,201,0.18)',
    outgoingLine:    '#F8CA4D',
    outgoingFill:    'rgba(248,202,77,0.16)',
    // Tooltip
    tooltipBg:       'rgba(15,23,42,0.96)',
    tooltipBorder:   'rgba(59,130,246,0.45)',
    tooltipText:     '#f1f5f9',
    // Interaction
    crosshair:       'rgba(148,163,184,0.35)',
  };

  var PAD = { top: 22, right: 24, bottom: 44, left: 56 };

  // ═══════════════════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════════════════

  var canvas, ctx, dpr;
  var chartData = null;
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
    dpr = window.devicePixelRatio || 1;

    sizeCanvas();
    window.addEventListener('resize', onResize);

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
  }

  function cssWidth() { return canvas.width / dpr; }
  function cssHeight() { return canvas.height / dpr; }

  function onResize() {
    sizeCanvas();
    draw();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DATA FETCHING
  // ═══════════════════════════════════════════════════════════════════════════

  function fetchData(hours) {
    var loader = document.getElementById('hl7-chart-loading');
    if (loader) loader.style.display = 'block';

    var url = '/api/hl7-throughput?hours=' + hours;
    if (currentHealthBoard) {
      url += '&health_board=' + encodeURIComponent(currentHealthBoard);
    }
    if (currentService) {
      url += '&service=' + encodeURIComponent(currentService);
    }

    fetch(url)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        chartData = data;
        if (loader) loader.style.display = 'none';
        updateLegend();
        draw();
      })
      .catch(function (err) {
        console.error('HL7 chart data fetch failed:', err);
        chartData = null;
        if (loader) loader.style.display = 'none';
        drawEmpty('Failed to load metrics');
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

  function draw() {
    var w = cssWidth();
    var h = cssHeight();

    ctx.fillStyle = 'rgba(15, 23, 42, 1)';
    ctx.fillRect(0, 0, w, h);

    var incoming = (chartData && chartData.incoming) || [];
    var outgoing = (chartData && chartData.outgoing) || [];

    if (incoming.length === 0 && outgoing.length === 0) {
      drawEmpty('No data available');
      return;
    }

    // Compute layout
    chartMetrics.width = w - PAD.left - PAD.right;
    chartMetrics.height = h - PAD.top - PAD.bottom;

    // Time domain spans whichever series has data.
    var times = [];
    if (incoming.length > 0) {
      times.push(parseISO(incoming[0].time), parseISO(incoming[incoming.length - 1].time));
    }
    if (outgoing.length > 0) {
      times.push(parseISO(outgoing[0].time), parseISO(outgoing[outgoing.length - 1].time));
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

    // Draw background
    drawBackground();

    // Draw axes
    drawAxes();

    // Draw series (outgoing first so the larger incoming line sits on top)
    drawSeries(outgoing, COLORS.outgoingLine, COLORS.outgoingFill);
    drawSeries(incoming, COLORS.incomingLine, COLORS.incomingFill);

    // Draw crosshair on hover
    if (hoverPos) {
      drawCrosshair(hoverPos);
      drawTooltip(hoverPos);
    }
  }

  function drawBackground() {
    var w = cssWidth();
    var h = cssHeight();

    // Gradient
    var grad = ctx.createLinearGradient(0, PAD.top, 0, h - PAD.bottom);
    grad.addColorStop(0, COLORS.bgGradientStart);
    grad.addColorStop(1, COLORS.bgGradientEnd);
    ctx.fillStyle = grad;
    ctx.fillRect(PAD.left, PAD.top, chartMetrics.width, chartMetrics.height);
  }

  function drawAxes() {
    var w = cssWidth();
    var h = cssHeight();
    var x0 = PAD.left;
    var y0 = h - PAD.bottom;

    // Frame
    ctx.strokeStyle = COLORS.gridLine;
    ctx.lineWidth = 1;
    ctx.strokeRect(x0, PAD.top, chartMetrics.width, chartMetrics.height);

    // Y-axis label
    ctx.save();
    ctx.translate(8, h / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = COLORS.axisText;
    ctx.font = '0.7rem system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('Messages', 0, 0);
    ctx.restore();

    // Y-axis gridlines and labels
    ctx.fillStyle = COLORS.axisText;
    ctx.font = '0.65rem system-ui';
    ctx.textAlign = 'right';
    var yTicks = [0, 0.25, 0.5, 0.75, 1.0];
    yTicks.forEach(function (tick) {
      var y = y0 - tick * chartMetrics.height;
      var val = Math.round(tick * chartMetrics.maxValue);

      // Gridline
      ctx.strokeStyle = COLORS.gridLine;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x0 + chartMetrics.width, y);
      ctx.stroke();

      // Label
      ctx.fillText(formatNumber(val), x0 - 8, y + 3);
    });

    // X-axis labels (sample timestamps)
    ctx.textAlign = 'center';
    var spanMs = chartMetrics.maxTime - chartMetrics.minTime;
    var multiDay = spanMs > 24 * 60 * 60 * 1000;
    var xTicks = [0, 0.25, 0.5, 0.75, 1.0];
    xTicks.forEach(function (tick) {
      var x = x0 + tick * chartMetrics.width;
      var t = chartMetrics.minTime + tick * (chartMetrics.maxTime - chartMetrics.minTime);
      var label = multiDay ? formatDateShort(t) : formatTime(t);
      ctx.fillText(label, x, y0 + 16);
    });
  }

  function drawSeries(series, lineColor, fillColor) {
    if (series.length === 0) return;

    var x0 = PAD.left;
    var y0 = cssHeight() - PAD.bottom;

    // Points
    var points = series.map(function (pt) {
      var t = parseISO(pt.time);
      var v = pt.value || 0;
      var x = x0 + ((t - chartMetrics.minTime) / (chartMetrics.maxTime - chartMetrics.minTime)) * chartMetrics.width;
      var y = y0 - (v / chartMetrics.maxValue) * chartMetrics.height;
      return { x: x, y: y, value: v, time: t };
    });

    if (points.length < 2) {
      // Just draw points
      ctx.fillStyle = lineColor;
      points.forEach(function (pt) {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 2, 0, 2 * Math.PI);
        ctx.fill();
      });
      return;
    }

    // Draw filled area
    ctx.fillStyle = fillColor;
    ctx.beginPath();
    ctx.moveTo(points[0].x, y0);

    // Curve through points
    var cp = {};
    for (var i = 0; i < points.length; i++) {
      catmullRomControlPoints(points, i, cp);
      if (i === 0) {
        ctx.quadraticCurveTo(cp.c1x, cp.c1y, points[i + 1].x, points[i + 1].y);
      } else if (i < points.length - 1) {
        ctx.bezierCurveTo(cp.c1x, cp.c1y, cp.c2x, cp.c2y, points[i + 1].x, points[i + 1].y);
      }
    }

    ctx.lineTo(points[points.length - 1].x, y0);
    ctx.closePath();
    ctx.fill();

    // Draw line
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);

    for (var i = 0; i < points.length; i++) {
      catmullRomControlPoints(points, i, cp);
      if (i === 0) {
        ctx.quadraticCurveTo(cp.c1x, cp.c1y, points[i + 1].x, points[i + 1].y);
      } else if (i < points.length - 1) {
        ctx.bezierCurveTo(cp.c1x, cp.c1y, cp.c2x, cp.c2y, points[i + 1].x, points[i + 1].y);
      }
    }

    ctx.stroke();

    // Draw data points
    ctx.fillStyle = lineColor;
    points.forEach(function (pt) {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 2.5, 0, 2 * Math.PI);
      ctx.fill();
    });
  }

  function drawCrosshair(pos) {
    var x0 = PAD.left;
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
    if (!chartData) return;

    var incoming = chartData.incoming || [];
    var outgoing = chartData.outgoing || [];
    var ref = incoming.length >= outgoing.length ? incoming : outgoing;
    if (ref.length === 0) return;

    var x0 = PAD.left;
    var span = chartMetrics.maxTime - chartMetrics.minTime;

    // Find nearest bin index by screen X using the reference series.
    var nearestIdx = -1;
    var nearestX = 0;
    var minDist = Infinity;
    for (var i = 0; i < ref.length; i++) {
      var t = parseISO(ref[i].time);
      var x = x0 + ((t - chartMetrics.minTime) / span) * chartMetrics.width;
      var dist = Math.abs(x - pos.x);
      if (dist < minDist) {
        minDist = dist;
        nearestIdx = i;
        nearestX = x;
      }
    }

    if (nearestIdx < 0 || minDist > 30) return;

    var binTime = parseISO(ref[nearestIdx].time);
    var inVal = valueAtTime(incoming, binTime);
    var outVal = valueAtTime(outgoing, binTime);

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
    ctx.shadowColor = 'rgba(0, 0, 0, 0.4)';
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
      x: (e.clientX - rect.left) * dpr,
      y: (e.clientY - rect.top) * dpr
    };
    draw();
  }

  function onCanvasMouseLeave() {
    hoverPos = null;
    draw();
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

  function valueAtTime(series, ms) {
    if (!series) return 0;
    for (var i = 0; i < series.length; i++) {
      if (parseISO(series[i].time) === ms) {
        return series[i].value || 0;
      }
    }
    return 0;
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
