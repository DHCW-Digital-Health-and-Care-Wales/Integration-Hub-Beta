/**
 * Network Test — Latency History Chart — Canvas 2D Implementation
 * NHS Wales Integration Hub Dashboard
 *
 * Factory-based (one instance per expanded row in the endpoint list) so several
 * charts can exist at once without stepping on each other's state. No external
 * dependencies — mirrors the conventions used by hl7-throughput-chart.js.
 *
 * Supported metrics (see METRIC_UNITS below): 'avg' (average latency line),
 * 'minmax' (min/max latency band), 'loss' (packet loss % line).
 */
(function () {
  'use strict';

  var COLORS = {
    gridLine: 'rgba(51,65,85,0.45)',
    axisText: '#94a3b8',
    line: '#12A3C9',
    fill: 'rgba(18,163,201,0.16)',
    band: 'rgba(18,163,201,0.14)',
    loss: '#f59e0b',
    lossFill: 'rgba(245,158,11,0.16)',
    fail: '#ef4444',
    crosshair: 'rgba(148,163,184,0.5)',
    tooltipBg: 'rgba(15,23,42,0.96)',
    tooltipBorder: 'rgba(59,130,246,0.45)',
    tooltipText: '#f1f5f9',
  };

  var PAD = { top: 16, right: 16, bottom: 26, left: 48 };

  var METRIC_UNITS = { avg: 'ms', minmax: 'ms', loss: '%' };

  function create(canvas) {
    var ctx = canvas.getContext('2d');
    var dpr = window.devicePixelRatio || 1;
    var samples = [];
    var metric = 'avg';
    var hoverIdx = -1;

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

    function onResize() { sizeCanvas(); draw(); }

    function xFor(idx, plotW) {
      return samples.length > 1
        ? PAD.left + (idx / (samples.length - 1)) * plotW
        : PAD.left + plotW / 2;
    }

    function drawGrid(plotW, plotH, maxValue, unit) {
      ctx.strokeStyle = COLORS.gridLine;
      ctx.fillStyle = COLORS.axisText;
      ctx.font = '10px Rubik, sans-serif';
      ctx.textBaseline = 'middle';
      [0, 0.5, 1].forEach(function (frac) {
        var y = PAD.top + plotH * (1 - frac);
        ctx.beginPath();
        ctx.moveTo(PAD.left, y);
        ctx.lineTo(PAD.left + plotW, y);
        ctx.stroke();
        ctx.textAlign = 'right';
        ctx.fillText(Math.round(maxValue * frac) + unit, PAD.left - 6, y);
      });
    }

    function drawLineMetric(plotW, plotH, valueKey) {
      var values = samples
        .map(function (s) { return s[valueKey]; })
        .filter(function (v) { return v !== null && v !== undefined; });
      var maxValue = Math.max(10, values.length ? Math.max.apply(null, values) * 1.2 : 10);
      drawGrid(plotW, plotH, maxValue, METRIC_UNITS[metric]);

      function yFor(v) { return PAD.top + plotH * (1 - Math.min(1, v / maxValue)); }
      var scale = { yFor: yFor };

      ctx.beginPath();
      var started = false;
      var fillPoints = [];
      samples.forEach(function (s, idx) {
        var v = s[valueKey];
        if (v === null || v === undefined) { started = false; return; }
        var x = xFor(idx, plotW);
        var y = yFor(v);
        if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
        fillPoints.push([x, y]);
      });
      ctx.strokeStyle = metric === 'loss' ? COLORS.loss : COLORS.line;
      ctx.lineWidth = 2;
      ctx.stroke();

      if (fillPoints.length > 1) {
        ctx.lineTo(fillPoints[fillPoints.length - 1][0], PAD.top + plotH);
        ctx.lineTo(fillPoints[0][0], PAD.top + plotH);
        ctx.closePath();
        ctx.fillStyle = metric === 'loss' ? COLORS.lossFill : COLORS.fill;
        ctx.fill();
      }

      samples.forEach(function (s, idx) {
        var x = xFor(idx, plotW);
        var v = s[valueKey];
        var ok = s.success && v !== null && v !== undefined;
        var y = ok ? yFor(v) : PAD.top + plotH;
        ctx.beginPath();
        ctx.arc(x, y, ok ? 2.5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = ok ? (metric === 'loss' ? COLORS.loss : COLORS.line) : COLORS.fail;
        ctx.fill();
      });

      return scale;
    }

    function drawMinMaxBand(plotW, plotH) {
      var maxes = samples
        .map(function (s) { return s.max_latency_ms; })
        .filter(function (v) { return v !== null && v !== undefined; });
      var maxValue = Math.max(10, maxes.length ? Math.max.apply(null, maxes) * 1.2 : 10);
      drawGrid(plotW, plotH, maxValue, 'ms');

      function yFor(v) { return PAD.top + plotH * (1 - Math.min(1, v / maxValue)); }
      var scale = { yFor: yFor };

      var bandPoints = [];
      samples.forEach(function (s, idx) {
        if (s.min_latency_ms === null || s.min_latency_ms === undefined) return;
        if (s.max_latency_ms === null || s.max_latency_ms === undefined) return;
        bandPoints.push({ x: xFor(idx, plotW), min: yFor(s.min_latency_ms), max: yFor(s.max_latency_ms) });
      });

      if (bandPoints.length > 1) {
        ctx.beginPath();
        ctx.moveTo(bandPoints[0].x, bandPoints[0].max);
        bandPoints.forEach(function (p) { ctx.lineTo(p.x, p.max); });
        for (var i = bandPoints.length - 1; i >= 0; i--) { ctx.lineTo(bandPoints[i].x, bandPoints[i].min); }
        ctx.closePath();
        ctx.fillStyle = COLORS.band;
        ctx.fill();

        ctx.beginPath();
        bandPoints.forEach(function (p, idx) { idx === 0 ? ctx.moveTo(p.x, p.max) : ctx.lineTo(p.x, p.max); });
        ctx.strokeStyle = COLORS.line;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.beginPath();
        bandPoints.forEach(function (p, idx) { idx === 0 ? ctx.moveTo(p.x, p.min) : ctx.lineTo(p.x, p.min); });
        ctx.strokeStyle = COLORS.line;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      samples.forEach(function (s, idx) {
        if (s.success) return;
        var x = xFor(idx, plotW);
        ctx.beginPath();
        ctx.arc(x, PAD.top + plotH, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = COLORS.fail;
        ctx.fill();
      });

      return scale;
    }

    function fmtMs(v) { return (v === null || v === undefined) ? '—' : Math.round(v) + ' ms'; }

    function tooltipLines(sample) {
      var lines = [];
      lines.push(sample.timestamp ? new Date(sample.timestamp * 1000).toLocaleTimeString() : '');
      if (!sample.success) {
        lines.push('Failed');
      } else if (metric === 'minmax') {
        lines.push('Min ' + fmtMs(sample.min_latency_ms));
        lines.push('Max ' + fmtMs(sample.max_latency_ms));
      } else if (metric === 'loss') {
        lines.push('Loss ' + (sample.loss_percent === null || sample.loss_percent === undefined ? '—' : sample.loss_percent + '%'));
      } else {
        lines.push('Avg ' + fmtMs(sample.avg_latency_ms));
      }
      return lines;
    }

    function drawCrosshair(x, plotH) {
      ctx.save();
      ctx.strokeStyle = COLORS.crosshair;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(x, PAD.top);
      ctx.lineTo(x, PAD.top + plotH);
      ctx.stroke();
      ctx.restore();
    }

    function drawHoverMarkers(x, scale, sample) {
      var values = metric === 'minmax'
        ? [sample.min_latency_ms, sample.max_latency_ms]
        : [metric === 'loss' ? sample.loss_percent : sample.avg_latency_ms];

      ctx.lineWidth = 2;
      ctx.strokeStyle = metric === 'loss' ? COLORS.loss : COLORS.line;
      values.forEach(function (v) {
        if (v === null || v === undefined) return;
        ctx.beginPath();
        ctx.arc(x, scale.yFor(v), 4, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();
        ctx.stroke();
      });
    }

    function drawTooltip(x, plotW) {
      var sample = samples[hoverIdx];
      var lines = tooltipLines(sample);

      ctx.font = '11px Rubik, sans-serif';
      var paddingX = 8;
      var lineHeight = 15;
      var textWidth = Math.max.apply(null, lines.map(function (l) { return ctx.measureText(l).width; }));
      var boxW = textWidth + paddingX * 2;
      var boxH = lines.length * lineHeight + 6;
      var boxX = Math.min(Math.max(x - boxW / 2, PAD.left), PAD.left + plotW - boxW);
      var boxY = PAD.top + 4;

      ctx.save();
      ctx.fillStyle = COLORS.tooltipBg;
      ctx.strokeStyle = COLORS.tooltipBorder;
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (ctx.roundRect) { ctx.roundRect(boxX, boxY, boxW, boxH, 4); } else { ctx.rect(boxX, boxY, boxW, boxH); }
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = COLORS.tooltipText;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      lines.forEach(function (line, idx) {
        ctx.fillText(line, boxX + paddingX, boxY + 3 + idx * lineHeight);
      });
      ctx.restore();
    }

    function draw() {
      var w = cssWidth();
      var h = cssHeight();
      ctx.clearRect(0, 0, w, h);
      if (!samples.length) return;

      var plotW = w - PAD.left - PAD.right;
      var plotH = h - PAD.top - PAD.bottom;

      var scale = metric === 'minmax'
        ? drawMinMaxBand(plotW, plotH)
        : drawLineMetric(plotW, plotH, metric === 'loss' ? 'loss_percent' : 'avg_latency_ms');

      if (hoverIdx >= 0 && hoverIdx < samples.length) {
        var x = xFor(hoverIdx, plotW);
        drawCrosshair(x, plotH);
        drawHoverMarkers(x, scale, samples[hoverIdx]);
        drawTooltip(x, plotW);
      }
    }

    function nearestIndexForX(mouseX, plotW) {
      var nearest = 0;
      var minDist = Infinity;
      for (var i = 0; i < samples.length; i++) {
        var dist = Math.abs(xFor(i, plotW) - mouseX);
        if (dist < minDist) { minDist = dist; nearest = i; }
      }
      return nearest;
    }

    function onMouseMove(e) {
      if (!samples.length) return;
      var rect = canvas.getBoundingClientRect();
      var mouseX = e.clientX - rect.left;
      var plotW = cssWidth() - PAD.left - PAD.right;
      hoverIdx = mouseX < PAD.left - 4 || mouseX > PAD.left + plotW + 4 ? -1 : nearestIndexForX(mouseX, plotW);
      draw();
    }

    function onMouseLeave() {
      hoverIdx = -1;
      draw();
    }

    sizeCanvas();
    window.addEventListener('resize', onResize);
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mouseleave', onMouseLeave);

    return {
      render: function (newSamples, newMetric) {
        samples = newSamples || [];
        if (newMetric) metric = newMetric;
        draw();
      },
      setMetric: function (newMetric) {
        metric = newMetric;
        draw();
      },
      destroy: function () {
        window.removeEventListener('resize', onResize);
        canvas.removeEventListener('mousemove', onMouseMove);
        canvas.removeEventListener('mouseleave', onMouseLeave);
      },
    };
  }

  window.NetworkTestChart = { create: create };
})();

