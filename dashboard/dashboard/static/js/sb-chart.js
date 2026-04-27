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

  var COLORS = {
    // Background gradient
    bgGradientStart: 'rgba(30,41,59,0.55)',
    bgGradientEnd:   'rgba(15,23,42,0.25)',
    // Grid & Axes
    gridLine:        'rgba(51,65,85,0.45)',
    axisText:        '#94a3b8',
    // Series
    incoming:        '#3b82f6',
    incomingFill:    'rgba(59,130,246,0.18)',
    outgoing:        '#d946ef',
    outgoingFill:    'rgba(217,70,239,0.12)',
    // Tooltip
    tooltipBg:       'rgba(15,23,42,0.96)',
    tooltipBorder:   'rgba(59,130,246,0.45)',
    tooltipText:     '#f1f5f9',
    // Interaction
    crosshair:       'rgba(148,163,184,0.35)',
    zoomBoxFill:     'rgba(59,130,246,0.12)',
    zoomBoxBorder:   'rgba(59,130,246,0.65)'
  };

  var PAD = { top: 22, right: 24, bottom: 44, left: 56 };

  // ═══════════════════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════════════════

  var canvas, ctx, dpr;
  var chartData = null;
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
    dpr = window.devicePixelRatio || 1;

    sizeCanvas();
    window.addEventListener('resize', onResize);

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
    var loader = document.getElementById('messages-chart-loading');
    if (loader) loader.style.display = 'block';

    var url = '/api/servicebus-metrics?hours=' + hours;
    if (window.__chartQueueFilter) {
      url += '&queue=' + encodeURIComponent(window.__chartQueueFilter);
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
        console.error('Chart data fetch failed:', err);
        chartData = null;
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
      (zoomedRange ? '&emsp;<span style="color:#22d3ee;font-size:0.7rem;">zoomed — double-click to reset</span>' : '');
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

  function draw() {
    if (!chartData) return;

    var w = cssWidth();
    var h = cssHeight();
    ctx.clearRect(0, 0, w, h);

    // Filter data by zoom range
    var incoming = filterByZoom(chartData.incoming || []);
    var outgoing = filterByZoom(chartData.outgoing || []);

    if (!incoming.length && !outgoing.length) {
      drawEmpty('No message data for this period');
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
    var maxVal = Math.max.apply(null, allPoints.map(function (p) { return p.value; }).concat([1]));
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

    // Draw layers
    drawBackground(areaWidth, areaHeight);
    drawGrid(incoming, minTime, maxTime, yMax, areaWidth, areaHeight);
    drawSeries(incoming, COLORS.incoming, COLORS.incomingFill, minTime, maxTime, yMax, areaWidth, areaHeight);
    drawSeries(outgoing, COLORS.outgoing, COLORS.outgoingFill, minTime, maxTime, yMax, areaWidth, areaHeight);

    // Crosshair and tooltip (only when not dragging)
    if (hoverPos && !isDragging) {
      drawCrosshair(incoming, outgoing, minTime, maxTime, yMax, areaWidth, areaHeight);
    }

    // Zoom selection box
    if (isDragging && dragStart && dragCurrent) {
      drawZoomBox(areaHeight);
    }

    // Hint text when not zoomed or interacting
    if (!zoomedRange && !isDragging && !hoverPos) {
      ctx.fillStyle = 'rgba(148,163,184,0.28)';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'top';
      ctx.fillText('drag to zoom · dbl-click to reset', w - PAD.right - 4, PAD.top + 5);
    }
  }

  function filterByZoom(points) {
    if (!zoomedRange) return points;
    return points.filter(function (p) {
      var t = +new Date(p.time);
      return t >= zoomedRange.minT && t <= zoomedRange.maxT;
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // BACKGROUND
  // ═══════════════════════════════════════════════════════════════════════════

  function drawBackground(areaWidth, areaHeight) {
    var gradient = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + areaHeight);
    gradient.addColorStop(0, COLORS.bgGradientStart);
    gradient.addColorStop(1, COLORS.bgGradientEnd);
    ctx.fillStyle = gradient;
    roundedRect(PAD.left, PAD.top, areaWidth, areaHeight, 8);
    ctx.fill();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GRID
  // ═══════════════════════════════════════════════════════════════════════════

  function drawGrid(incoming, minTime, maxTime, yMax, areaWidth, areaHeight) {
    var yStep = niceStep(yMax);
    var yTicks = Math.min(6, Math.ceil(yMax / yStep));

    ctx.font = '10px monospace';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'right';

    // Horizontal grid lines and Y labels
    for (var i = 0; i <= yTicks; i++) {
      var val = i * yStep;
      var y = PAD.top + areaHeight - (val / yMax) * areaHeight;

      ctx.strokeStyle = COLORS.gridLine;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(PAD.left, y);
      ctx.lineTo(PAD.left + areaWidth, y);
      ctx.stroke();

      ctx.fillStyle = COLORS.axisText;
      ctx.fillText(formatNumber(val), PAD.left - 8, y);
    }

    // X axis time labels
    if (!incoming.length) return;

    var labelCount = Math.min(8, incoming.length);
    var interval = Math.max(1, Math.floor(incoming.length / labelCount));

    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';

    for (var xi = 0; xi < incoming.length; xi += interval) {
      var t = new Date(incoming[xi].time);
      var x = PAD.left + ((+t - minTime) / (maxTime - minTime)) * areaWidth;

      // Tick mark
      ctx.strokeStyle = COLORS.gridLine;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, PAD.top + areaHeight);
      ctx.lineTo(x, PAD.top + areaHeight + 4);
      ctx.stroke();

      // Label
      ctx.fillStyle = COLORS.axisText;
      ctx.fillText(formatTime(t, currentHours), x, PAD.top + areaHeight + 8);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SERIES DRAWING (straight line segments with gradient fill and glow)
  // ═══════════════════════════════════════════════════════════════════════════

  function drawSeries(points, lineColor, fillColor, minTime, maxTime, yMax, areaWidth, areaHeight) {
    if (!points.length) return;

    var coords = pointsToCoords(points, minTime, maxTime, yMax, areaWidth, areaHeight);

    // Gradient fill under the curve
    var gradient = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + areaHeight);
    gradient.addColorStop(0, fillColor);
    gradient.addColorStop(0.6, fillColor.replace(/[\d.]+\)$/, '0.06)'));
    gradient.addColorStop(1, 'rgba(0,0,0,0)');

    ctx.save();
    ctx.beginPath();
    linearPath(coords);
    ctx.lineTo(coords[coords.length - 1].x, PAD.top + areaHeight);
    ctx.lineTo(coords[0].x, PAD.top + areaHeight);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
    ctx.restore();

    // Line stroke
    ctx.save();
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    linearPath(coords);
    ctx.stroke();
    ctx.restore();

    // Data point dots (skip when data is dense)
    if (coords.length <= 60) {
      ctx.fillStyle = lineColor;
      for (var i = 0; i < coords.length; i++) {
        ctx.beginPath();
        ctx.arc(coords[i].x, coords[i].y, coords.length > 30 ? 2 : 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  function pointsToCoords(points, minTime, maxTime, yMax, areaWidth, areaHeight) {
    return points.map(function (p) {
      var t = +new Date(p.time);
      return {
        x: PAD.left + ((t - minTime) / (maxTime - minTime)) * areaWidth,
        y: PAD.top + areaHeight - (p.value / yMax) * areaHeight,
        value: p.value,
        time: p.time
      };
    });
  }

  // Straight line path connecting data points
  function linearPath(coords) {
    if (coords.length === 0) return;
    ctx.moveTo(coords[0].x, coords[0].y);
    for (var i = 1; i < coords.length; i++) {
      ctx.lineTo(coords[i].x, coords[i].y);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CROSSHAIR AND TOOLTIP
  // ═══════════════════════════════════════════════════════════════════════════

  function drawCrosshair(incoming, outgoing, minTime, maxTime, yMax, areaWidth, areaHeight) {
    var inCoords = pointsToCoords(incoming, minTime, maxTime, yMax, areaWidth, areaHeight);
    var outCoords = pointsToCoords(outgoing, minTime, maxTime, yMax, areaWidth, areaHeight);
    var srcCoords = inCoords.length ? inCoords : outCoords;
    if (!srcCoords.length) return;

    // Find closest point to hover position
    var closestIdx = 0;
    var closestDist = Infinity;
    for (var i = 0; i < srcCoords.length; i++) {
      var dist = Math.abs(srcCoords[i].x - hoverPos.x);
      if (dist < closestDist) {
        closestDist = dist;
        closestIdx = i;
      }
    }

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
    var timestamp = new Date(srcCoords[closestIdx].time);
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
    ctx.shadowColor = 'rgba(0,0,0,0.55)';
    ctx.shadowBlur = 16;
    ctx.shadowOffsetY = 4;
    ctx.fillStyle = COLORS.tooltipBg;
    roundedRect(tx, ty, boxWidth, boxHeight, 8);
    ctx.fill();
    ctx.restore();

    ctx.strokeStyle = COLORS.tooltipBorder;
    ctx.lineWidth = 1;
    roundedRect(tx, ty, boxWidth, boxHeight, 8);
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

        ctx.fillStyle = '#fff';
        ctx.textAlign = 'right';
        ctx.fillText(formatNumber(line.value), tx + boxWidth - padding, ly);
      } else {
        ctx.fillStyle = 'rgba(148,163,184,0.7)';
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
      ctx.fillStyle = 'rgba(59,130,246,0.9)';
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
    draw();
  }

  function onCanvasMouseLeave() {
    if (!isDragging) {
      hoverPos = null;
      draw();
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
    draw();
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
    return Math.min.apply(null, points.map(function (p) { return +new Date(p.time); }));
  }

  function maxTimestamp(points) {
    if (!points.length) return 0;
    return Math.max.apply(null, points.map(function (p) { return +new Date(p.time); }));
  }

  function roundedRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
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
