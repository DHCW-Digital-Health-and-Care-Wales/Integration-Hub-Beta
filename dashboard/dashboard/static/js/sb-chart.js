/**
 * Service Bus Messages Chart — Canvas 2D Implementation
 * NHS Wales Integration Hub Dashboard
 * 
 * Features:
 *   - Smooth Catmull-Rom spline curves with gradient fills
 *   - Glow effect on lines
 *   - Fancy tooltip with colour indicators and drop shadow
 *   - Crosshair on hover with highlighted data points
 *   - Drag-to-zoom (horizontal selection box)
 *   - Double-click and Reset button to restore full view
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
        bgGradientStart: 'rgba(241,245,249,0.85)',
        bgGradientEnd:   'rgba(255,255,255,0.45)',
        gridLine:        'rgba(148,163,184,0.35)',
        axisText:        '#475569',
        hintText:        'rgba(71,85,105,0.55)',
        incoming:        '#2563eb',
        incomingFill:    'rgba(37,99,235,0.14)',
        outgoing:        '#c026d3',
        outgoingFill:    'rgba(192,38,211,0.10)',
        tooltipBg:       'rgba(255,255,255,0.97)',
        tooltipBorder:   '#cbd5e1',
        tooltipText:     '#0f172a',
        tooltipMuted:    '#64748b',
        tooltipShadow:   'rgba(15,23,42,0.16)',
        zoomedHint:      '#0891b2',
        crosshair:       'rgba(71,85,105,0.35)',
        zoomBoxFill:     'rgba(37,99,235,0.12)',
        zoomBoxBorder:   'rgba(37,99,235,0.65)',
        zoomLabel:       '#2563eb'
      };
    }
    return {
      bgGradientStart: 'rgba(30,41,59,0.55)',
      bgGradientEnd:   'rgba(15,23,42,0.25)',
      gridLine:        'rgba(51,65,85,0.45)',
      axisText:        '#94a3b8',
      hintText:        'rgba(148,163,184,0.28)',
      incoming:        '#3b82f6',
      incomingFill:    'rgba(59,130,246,0.18)',
      outgoing:        '#d946ef',
      outgoingFill:    'rgba(217,70,239,0.12)',
      tooltipBg:       'rgba(15,23,42,0.96)',
      tooltipBorder:   'rgba(59,130,246,0.45)',
      tooltipText:     '#f1f5f9',
      tooltipMuted:    'rgba(148,163,184,0.7)',
      tooltipShadow:   'rgba(0,0,0,0.55)',
      zoomedHint:      '#22d3ee',
      crosshair:       'rgba(148,163,184,0.35)',
      zoomBoxFill:     'rgba(59,130,246,0.12)',
      zoomBoxBorder:   'rgba(59,130,246,0.65)',
      zoomLabel:       'rgba(59,130,246,0.9)'
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
  var cachedLayer = null;
  var currentHours = 1;

  // Hover state
  var hoverPos = null; // {x, y} in CSS pixels

  // Drag-to-zoom state
  var isDragging = false;
  var dragStart = null;   // {x, y} starting position
  var dragCurrent = null; // {x, y} current drag position

  // Zoom state: time range currently displayed
  var zoomedRange = null; // {minT, maxT} or null for full range

  // Computed chart metrics (updated each draw)
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
    canvas = document.getElementById('messages-chart');
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
      if (chartData) { draw(); }
    });

    // Canvas event listeners
    canvas.addEventListener('mousemove', onCanvasMouseMove);
    canvas.addEventListener('mouseleave', onCanvasMouseLeave);
    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('dblclick', onDoubleClick);

    // Prevent text selection during drag
    canvas.addEventListener('selectstart', function (e) {
      if (isDragging) e.preventDefault();
    });

    // Timespan buttons
    document.querySelectorAll('.metrics-ts-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.metrics-ts-btn').forEach(function (b) {
          b.classList.remove('active');
        });
        btn.classList.add('active');
        currentHours = parseInt(btn.dataset.hours, 10) || 1;
        zoomedRange = null;
        baseDirty = true;
        updateResetButton();
        fetchData(currentHours);
      });
    });

    // Reset zoom button
    var resetBtn = document.getElementById('chart-reset-zoom');
    if (resetBtn) {
      resetBtn.addEventListener('click', resetZoom);
    }

    // Initial data fetch
    fetchData(currentHours);

    // Expose fetchData globally so external controls (e.g. queue dropdown) can trigger a reload
    window.fetchData = fetchData;
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

  function attachTimestamps(points) {
    return (points || []).map(function (p) {
      return { time: p.time, ms: +new Date(p.time), value: p.value };
    });
  }

  function fetchData(hours) {
    var loader = document.getElementById('messages-chart-loading');
    if (loader) loader.style.display = 'block';

    var url = '/api/servicebus-metrics?hours=' + hours;
    if (window.__chartEntityType && window.__chartEntityName) {
      url += '&entity_type=' + encodeURIComponent(window.__chartEntityType);
      url += '&entity_name=' + encodeURIComponent(window.__chartEntityName);
    }

    fetch(url)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        chartData = {
          incoming: attachTimestamps(data && data.incoming),
          outgoing: attachTimestamps(data && data.outgoing),
          timespan: data && data.timespan
        };
        baseDirty = true;
        if (loader) loader.style.display = 'none';
        updateLegend();
        draw();
      })
      .catch(function (err) {
        console.error('Chart data fetch failed:', err);
        chartData = null;
        cachedLayer = null;
        baseDirty = true;
        if (loader) loader.style.display = 'none';
        drawEmpty('Failed to load metrics');
      });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LEGEND
  // ═══════════════════════════════════════════════════════════════════════════

  function updateLegend() {
    var el = document.getElementById('messages-chart-legend');
    if (!el || !chartData) return;

    var inTotal = sumValues(chartData.incoming);
    var outTotal = sumValues(chartData.outgoing);

    el.innerHTML =
      legendDot(COLORS.incoming) +
      'Incoming&ensp;<strong style="color:' + COLORS.incoming + '">' + formatNumber(inTotal) + '</strong>&emsp;' +
      legendDot(COLORS.outgoing) +
      'Outgoing&ensp;<strong style="color:' + COLORS.outgoing + '">' + formatNumber(outTotal) + '</strong>' +
      (zoomedRange ? '&emsp;<span style="color:' + COLORS.zoomedHint + ';font-size:0.7rem;">zoomed — double-click to reset</span>' : '');
  }

  function legendDot(color) {
    return '<span style="display:inline-flex;align-items:center;gap:5px;">' +
           '<span style="width:14px;height:3px;background:' + color + ';border-radius:2px;display:inline-block;"></span>';
  }

  function sumValues(arr) {
    return (arr || []).reduce(function (sum, pt) { return sum + (pt.value || 0); }, 0);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // EMPTY STATE
  // ═══════════════════════════════════════════════════════════════════════════

  function drawEmpty(msg) {
    var w = cssWidth();
    var h = cssHeight();
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = COLORS.axisText;
    ctx.font = '13px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(msg || 'No data', w / 2, h / 2);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // MAIN DRAW
  // ═══════════════════════════════════════════════════════════════════════════

  function renderBaseLayer() {
    var w = cssWidth();
    var h = cssHeight();
    baseCtx.clearRect(0, 0, w, h);

    // Filter data by zoom range
    var incoming = filterByZoom(chartData.incoming || []);
    var outgoing = filterByZoom(chartData.outgoing || []);

    if (!incoming.length && !outgoing.length) {
      cachedLayer = { hasData: false };
      baseDirty = false;
      return;
    }

    // Chart area dimensions
    var areaWidth = w - PAD.left - PAD.right;
    var areaHeight = h - PAD.top - PAD.bottom;

    // Compute time range
    var allPoints = incoming.concat(outgoing);
    var minTime = zoomedRange ? zoomedRange.minT : minTimestamp(allPoints);
    var maxTime = zoomedRange ? zoomedRange.maxT : maxTimestamp(allPoints);
    if (minTime === maxTime) maxTime = minTime + 60000; // Prevent division by zero

    // Compute Y axis range
    var maxVal = 1;
    for (var i = 0; i < allPoints.length; i++) {
      if (allPoints[i].value > maxVal) maxVal = allPoints[i].value;
    }
    var yStep = niceStep(maxVal);
    var yMax = Math.ceil(maxVal / yStep) * yStep || 1;

    // Store metrics for mouse event calculations
    chartMetrics = {
      width: areaWidth,
      height: areaHeight,
      minTime: minTime,
      maxTime: maxTime,
      maxValue: yMax
    };

    var inCoords = pointsToCoords(incoming, minTime, maxTime, yMax, areaWidth, areaHeight);
    var outCoords = pointsToCoords(outgoing, minTime, maxTime, yMax, areaWidth, areaHeight);

    // Draw static layers onto offscreen canvas
    drawBackground(baseCtx, areaWidth, areaHeight);
    drawGrid(baseCtx, incoming, minTime, maxTime, yMax, areaWidth, areaHeight);
    drawSeries(baseCtx, inCoords, COLORS.incoming, COLORS.incomingFill, areaHeight);
    drawSeries(baseCtx, outCoords, COLORS.outgoing, COLORS.outgoingFill, areaHeight);

    cachedLayer = {
      hasData: true,
      inCoords: inCoords,
      outCoords: outCoords,
      srcCoords: inCoords.length ? inCoords : outCoords,
      areaWidth: areaWidth,
      areaHeight: areaHeight
    };
    baseDirty = false;
  }

  function draw() {
    if (!chartData) return;

    if (baseDirty) {
      renderBaseLayer();
    }

    var w = cssWidth();
    var h = cssHeight();

    if (!cachedLayer || !cachedLayer.hasData) {
      drawEmpty('No message data for this period');
      return;
    }

    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(baseCanvas, 0, 0, w, h);

    // Crosshair and tooltip (only when not dragging)
    if (hoverPos && !isDragging) {
      drawCrosshair(cachedLayer.inCoords, cachedLayer.outCoords, cachedLayer.srcCoords, cachedLayer.areaHeight);
    }

    // Zoom selection box
    if (isDragging && dragStart && dragCurrent) {
      drawZoomBox(cachedLayer.areaHeight);
    }

    // Hint text when not zoomed or interacting
    if (!zoomedRange && !isDragging && !hoverPos) {
      ctx.fillStyle = COLORS.hintText;
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'top';
      ctx.fillText('drag to zoom · dbl-click to reset', w - PAD.right - 4, PAD.top + 5);
    }
  }

  function filterByZoom(points) {
    if (!zoomedRange) return points;
    return points.filter(function (p) {
      return p.ms >= zoomedRange.minT && p.ms <= zoomedRange.maxT;
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // BACKGROUND
  // ═══════════════════════════════════════════════════════════════════════════

  function drawBackground(targetCtx, areaWidth, areaHeight) {
    var gradient = targetCtx.createLinearGradient(0, PAD.top, 0, PAD.top + areaHeight);
    gradient.addColorStop(0, COLORS.bgGradientStart);
    gradient.addColorStop(1, COLORS.bgGradientEnd);
    targetCtx.fillStyle = gradient;
    roundedRect(targetCtx, PAD.left, PAD.top, areaWidth, areaHeight, 8);
    targetCtx.fill();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GRID
  // ═══════════════════════════════════════════════════════════════════════════

  function drawGrid(targetCtx, incoming, minTime, maxTime, yMax, areaWidth, areaHeight) {
    var yStep = niceStep(yMax);
    var yTicks = Math.min(6, Math.ceil(yMax / yStep));

    targetCtx.font = '10px monospace';
    targetCtx.textBaseline = 'middle';
    targetCtx.textAlign = 'right';

    // Horizontal grid lines and Y labels
    for (var i = 0; i <= yTicks; i++) {
      var val = i * yStep;
      var y = PAD.top + areaHeight - (val / yMax) * areaHeight;

      targetCtx.strokeStyle = COLORS.gridLine;
      targetCtx.lineWidth = 1;
      targetCtx.beginPath();
      targetCtx.moveTo(PAD.left, y);
      targetCtx.lineTo(PAD.left + areaWidth, y);
      targetCtx.stroke();

      targetCtx.fillStyle = COLORS.axisText;
      targetCtx.fillText(formatNumber(val), PAD.left - 8, y);
    }

    // X axis time labels
    if (!incoming.length) return;

    var labelCount = Math.min(8, incoming.length);
    var interval = Math.max(1, Math.floor(incoming.length / labelCount));

    targetCtx.textAlign = 'center';
    targetCtx.textBaseline = 'top';

    for (var xi = 0; xi < incoming.length; xi += interval) {
      var ms = incoming[xi].ms;
      var x = PAD.left + ((ms - minTime) / (maxTime - minTime)) * areaWidth;

      // Tick mark
      targetCtx.strokeStyle = COLORS.gridLine;
      targetCtx.lineWidth = 1;
      targetCtx.beginPath();
      targetCtx.moveTo(x, PAD.top + areaHeight);
      targetCtx.lineTo(x, PAD.top + areaHeight + 4);
      targetCtx.stroke();

      // Label
      targetCtx.fillStyle = COLORS.axisText;
      targetCtx.fillText(formatTime(new Date(ms), currentHours), x, PAD.top + areaHeight + 8);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SERIES DRAWING (straight line segments with gradient fill and glow)
  // ═══════════════════════════════════════════════════════════════════════════

  function drawSeries(targetCtx, coords, lineColor, fillColor, areaHeight) {
    if (!coords.length) return;

    // Gradient fill under the curve
    var gradient = targetCtx.createLinearGradient(0, PAD.top, 0, PAD.top + areaHeight);
    gradient.addColorStop(0, fillColor);
    gradient.addColorStop(0.6, fillColor.replace(/[\d.]+\)$/, '0.06)'));
    gradient.addColorStop(1, 'rgba(0,0,0,0)');

    targetCtx.save();
    targetCtx.beginPath();
    linearPath(targetCtx, coords);
    targetCtx.lineTo(coords[coords.length - 1].x, PAD.top + areaHeight);
    targetCtx.lineTo(coords[0].x, PAD.top + areaHeight);
    targetCtx.closePath();
    targetCtx.fillStyle = gradient;
    targetCtx.fill();
    targetCtx.restore();

    // Line stroke
    targetCtx.save();
    targetCtx.strokeStyle = lineColor;
    targetCtx.lineWidth = 2.5;
    targetCtx.lineJoin = 'round';
    targetCtx.lineCap = 'round';
    targetCtx.beginPath();
    linearPath(targetCtx, coords);
    targetCtx.stroke();
    targetCtx.restore();

    // Data point dots (skip when data is dense)
    if (coords.length <= 60) {
      targetCtx.fillStyle = lineColor;
      for (var i = 0; i < coords.length; i++) {
        targetCtx.beginPath();
        targetCtx.arc(coords[i].x, coords[i].y, coords.length > 30 ? 2 : 3, 0, Math.PI * 2);
        targetCtx.fill();
      }
    }
  }

  function pointsToCoords(points, minTime, maxTime, yMax, areaWidth, areaHeight) {
    var span = maxTime - minTime;
    return points.map(function (p) {
      return {
        x: PAD.left + ((p.ms - minTime) / span) * areaWidth,
        y: PAD.top + areaHeight - (p.value / yMax) * areaHeight,
        value: p.value,
        ms: p.ms
      };
    });
  }

  // Straight line path connecting data points
  function linearPath(targetCtx, coords) {
    if (coords.length === 0) return;
    targetCtx.moveTo(coords[0].x, coords[0].y);
    for (var i = 1; i < coords.length; i++) {
      targetCtx.lineTo(coords[i].x, coords[i].y);
    }
  }

  function findClosestCoordIndex(coords, targetX) {
    var lo = 0;
    var hi = coords.length - 1;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (coords[mid].x < targetX) lo = mid + 1;
      else hi = mid;
    }
    var best = lo;
    if (lo > 0 && Math.abs(coords[lo - 1].x - targetX) < Math.abs(coords[lo].x - targetX)) {
      best = lo - 1;
    }
    return best;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CROSSHAIR AND TOOLTIP
  // ═══════════════════════════════════════════════════════════════════════════

  function drawCrosshair(inCoords, outCoords, srcCoords, areaHeight) {
    if (!srcCoords.length) return;

    // Find closest point to hover position via binary search on sorted X.
    var closestIdx = findClosestCoordIndex(srcCoords, hoverPos.x);
    var closestDist = Math.abs(srcCoords[closestIdx].x - hoverPos.x);

    if (closestDist > 45) return; // Too far from any point

    var px = srcCoords[closestIdx].x;

    // Vertical crosshair line
    ctx.save();
    ctx.strokeStyle = COLORS.crosshair;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(px, PAD.top);
    ctx.lineTo(px, PAD.top + areaHeight);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    // Highlighted data points
    drawHighlightDot(inCoords, closestIdx, COLORS.incoming);
    drawHighlightDot(outCoords, closestIdx, COLORS.outgoing);

    // Tooltip
    var timestamp = new Date(srcCoords[closestIdx].ms);
    var inValue = (inCoords.length && closestIdx < inCoords.length) ? inCoords[closestIdx].value : 0;
    var outValue = (outCoords.length && closestIdx < outCoords.length) ? outCoords[closestIdx].value : 0;
    drawTooltip(px, hoverPos.y, timestamp, inValue, outValue, areaHeight);
  }

  function drawHighlightDot(coords, idx, color) {
    if (!coords.length || idx >= coords.length) return;
    var c = coords[idx];

    ctx.save();
    ctx.shadowColor = color;
    ctx.shadowBlur = 12;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(c.x, c.y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();
  }

  function drawTooltip(px, py, timestamp, inValue, outValue, areaHeight) {
    var w = cssWidth();
    ctx.font = '11px sans-serif';

    var timeStr = formatTime(timestamp, currentHours, true);
    var lines = [
      { text: timeStr },
      { dot: COLORS.incoming, label: 'Incoming', value: inValue },
      { dot: COLORS.outgoing, label: 'Outgoing', value: outValue }
    ];

    var lineHeight = 20;
    var padding = 10;
    var maxTextWidth = 0;

    for (var i = 0; i < lines.length; i++) {
      var text = lines[i].dot ? lines[i].label + ': ' + formatNumber(lines[i].value) : lines[i].text;
      maxTextWidth = Math.max(maxTextWidth, ctx.measureText(text).width);
    }

    var boxWidth = maxTextWidth + padding * 2 + 14;
    var boxHeight = lines.length * lineHeight + padding * 2;

    // Position tooltip
    var tx = px + 14;
    if (tx + boxWidth > w - 8) tx = px - boxWidth - 14;
    var ty = Math.max(PAD.top + 4, Math.min((py || PAD.top + areaHeight / 2) - boxHeight / 2, PAD.top + areaHeight - boxHeight - 4));

    // Draw tooltip box with shadow
    ctx.save();
    ctx.shadowColor = COLORS.tooltipShadow;
    ctx.shadowBlur = 16;
    ctx.shadowOffsetY = 4;
    ctx.fillStyle = COLORS.tooltipBg;
    roundedRect(ctx, tx, ty, boxWidth, boxHeight, 8);
    ctx.fill();
    ctx.restore();

    ctx.strokeStyle = COLORS.tooltipBorder;
    ctx.lineWidth = 1;
    roundedRect(ctx, tx, ty, boxWidth, boxHeight, 8);
    ctx.stroke();

    // Draw tooltip content
    ctx.textBaseline = 'middle';
    for (var li = 0; li < lines.length; li++) {
      var lx = tx + padding;
      var ly = ty + padding + lineHeight * li + lineHeight / 2;
      var line = lines[li];

      if (line.dot) {
        ctx.fillStyle = line.dot;
        ctx.beginPath();
        ctx.arc(lx + 4, ly, 4, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = COLORS.axisText;
        ctx.textAlign = 'left';
        ctx.fillText(line.label + ':', lx + 12, ly);

        ctx.fillStyle = COLORS.tooltipText;
        ctx.textAlign = 'right';
        ctx.fillText(formatNumber(line.value), tx + boxWidth - padding, ly);
      } else {
        ctx.fillStyle = COLORS.tooltipMuted;
        ctx.textAlign = 'left';
        ctx.fillText(line.text, lx, ly);
      }
    }
    ctx.textAlign = 'center';
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // ZOOM BOX
  // ═══════════════════════════════════════════════════════════════════════════

  function drawZoomBox(areaHeight) {
    var x1 = Math.min(dragStart.x, dragCurrent.x);
    var x2 = Math.max(dragStart.x, dragCurrent.x);

    // Fill
    ctx.fillStyle = COLORS.zoomBoxFill;
    ctx.fillRect(x1, PAD.top, x2 - x1, areaHeight);

    // Dashed border
    ctx.strokeStyle = COLORS.zoomBoxBorder;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.strokeRect(x1, PAD.top, x2 - x1, areaHeight);
    ctx.setLineDash([]);

    // Label
    if (x2 - x1 > 50) {
      ctx.fillStyle = COLORS.zoomLabel;
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText('Release to zoom', (x1 + x2) / 2, PAD.top - 3);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // MOUSE EVENT HANDLERS
  // ═══════════════════════════════════════════════════════════════════════════

  function canvasPos(e) {
    var rect = canvas.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    };
  }

  function isInChartArea(pos) {
    return chartMetrics.width > 0 &&
           pos.x >= PAD.left && pos.x <= PAD.left + chartMetrics.width &&
           pos.y >= PAD.top && pos.y <= PAD.top + chartMetrics.height;
  }

  function onCanvasMouseMove(e) {
    var pos = canvasPos(e);
    hoverPos = pos;
    canvas.style.cursor = isInChartArea(pos) ? 'crosshair' : 'default';
    scheduleDraw();
  }

  function onCanvasMouseLeave() {
    if (!isDragging) {
      hoverPos = null;
      scheduleDraw();
    }
  }

  // CRITICAL: Drag-to-zoom implementation with window event listeners
  function onMouseDown(e) {
    var pos = canvasPos(e);
    if (!isInChartArea(pos)) return;

    e.preventDefault();
    isDragging = true;
    dragStart = pos;
    dragCurrent = pos;
    canvas.style.cursor = 'crosshair';

    // CRITICAL: Attach to window so releasing outside canvas still works
    window.addEventListener('mousemove', onWindowMouseMove);
    window.addEventListener('mouseup', onWindowMouseUp);
  }

  function onWindowMouseMove(e) {
    dragCurrent = canvasPos(e);
    hoverPos = dragCurrent;
    scheduleDraw();
  }

  function onWindowMouseUp(e) {
    // CRITICAL: Remove window listeners immediately
    window.removeEventListener('mousemove', onWindowMouseMove);
    window.removeEventListener('mouseup', onWindowMouseUp);

    isDragging = false;
    var endPos = canvasPos(e);
    var dx = Math.abs(endPos.x - dragStart.x);

    // Apply zoom if drag was significant
    if (dx > 12 && chartMetrics.minTime && chartMetrics.maxTime) {
      var x1 = Math.max(PAD.left, Math.min(dragStart.x, endPos.x));
      var x2 = Math.min(PAD.left + chartMetrics.width, Math.max(dragStart.x, endPos.x));
      var timeRange = chartMetrics.maxTime - chartMetrics.minTime;
      var newMinTime = chartMetrics.minTime + ((x1 - PAD.left) / chartMetrics.width) * timeRange;
      var newMaxTime = chartMetrics.minTime + ((x2 - PAD.left) / chartMetrics.width) * timeRange;

      if (newMaxTime > newMinTime) {
        zoomedRange = { minT: newMinTime, maxT: newMaxTime };
        baseDirty = true;
        updateResetButton();
        updateLegend();
      }
    }

    dragStart = null;
    dragCurrent = null;
    draw();
  }

  function onDoubleClick() {
    resetZoom();
  }

  function resetZoom() {
    zoomedRange = null;
    baseDirty = true;
    updateResetButton();
    updateLegend();
    draw();
  }

  function updateResetButton() {
    var btn = document.getElementById('chart-reset-zoom');
    if (btn) {
      btn.style.display = zoomedRange ? 'inline-flex' : 'none';
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // UTILITY FUNCTIONS
  // ═══════════════════════════════════════════════════════════════════════════

  function minTimestamp(points) {
    if (!points.length) return 0;
    var min = points[0].ms;
    for (var i = 1; i < points.length; i++) {
      if (points[i].ms < min) min = points[i].ms;
    }
    return min;
  }

  function maxTimestamp(points) {
    if (!points.length) return 0;
    var max = points[0].ms;
    for (var i = 1; i < points.length; i++) {
      if (points[i].ms > max) max = points[i].ms;
    }
    return max;
  }

  function roundedRect(targetCtx, x, y, w, h, r) {
    targetCtx.beginPath();
    targetCtx.moveTo(x + r, y);
    targetCtx.lineTo(x + w - r, y);
    targetCtx.quadraticCurveTo(x + w, y, x + w, y + r);
    targetCtx.lineTo(x + w, y + h - r);
    targetCtx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    targetCtx.lineTo(x + r, y + h);
    targetCtx.quadraticCurveTo(x, y + h, x, y + h - r);
    targetCtx.lineTo(x, y + r);
    targetCtx.quadraticCurveTo(x, y, x + r, y);
    targetCtx.closePath();
  }

  function niceStep(max) {
    if (max <= 5) return 1;
    if (max <= 10) return 2;
    if (max <= 25) return 5;
    if (max <= 50) return 10;
    if (max <= 100) return 20;
    if (max <= 500) return 100;
    return Math.pow(10, Math.floor(Math.log10(max)));
  }

  function formatNumber(n) {
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

    var day = String(d.getDate()).padStart(2, '0');
    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var mon = months[d.getMonth()];

    return full ? day + ' ' + mon + ' ' + hh + ':' + mm : day + ' ' + mon;
  }

}());
