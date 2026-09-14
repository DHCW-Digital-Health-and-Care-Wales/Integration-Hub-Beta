/**
 * Network Test — Latency History Chart — Canvas 2D Implementation
 * NHS Wales Integration Hub Dashboard
 *
 * Minimal single-series line chart (avg latency per sample, most recent last)
 * with failed samples marked in red. No external dependencies — mirrors the
 * conventions used by hl7-throughput-chart.js.
 */
(function () {
  'use strict';

  var COLORS = {
    gridLine: 'rgba(51,65,85,0.45)',
    axisText: '#94a3b8',
    line: '#12A3C9',
    fill: 'rgba(18,163,201,0.16)',
    fail: '#ef4444',
  };

  var PAD = { top: 16, right: 16, bottom: 26, left: 48 };

  var canvas, ctx, dpr = 1;
  var samples = [];

  document.addEventListener('DOMContentLoaded', function () {
    canvas = document.getElementById('network-test-chart');
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    dpr = window.devicePixelRatio || 1;
    sizeCanvas();
    window.addEventListener('resize', function () { sizeCanvas(); draw(); });
  });

  function sizeCanvas() {
    if (!canvas) return;
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

  function render(newSamples) {
    samples = newSamples || [];
    var emptyEl = document.getElementById('network-test-chart-empty');
    if (emptyEl) emptyEl.style.display = samples.length ? 'none' : 'flex';
    if (!canvas) return;
    draw();
  }

  function draw() {
    if (!ctx) return;
    var w = cssWidth();
    var h = cssHeight();

    ctx.clearRect(0, 0, w, h);
    if (!samples.length) return;

    var plotW = w - PAD.left - PAD.right;
    var plotH = h - PAD.top - PAD.bottom;

    var latencies = samples.map(function (s) { return s.avg_latency_ms; }).filter(function (v) { return v !== null && v !== undefined; });
    var maxLatency = Math.max(10, latencies.length ? Math.max.apply(null, latencies) * 1.2 : 10);

    // Grid lines + y-axis labels (0 / mid / max)
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
      ctx.fillText(Math.round(maxLatency * frac) + 'ms', PAD.left - 6, y);
    });

    function xFor(idx) {
      return samples.length > 1
        ? PAD.left + (idx / (samples.length - 1)) * plotW
        : PAD.left + plotW / 2;
    }
    function yFor(latency) {
      return PAD.top + plotH * (1 - Math.min(1, latency / maxLatency));
    }

    // Line + fill through successful samples only (gaps break the line)
    ctx.beginPath();
    var started = false;
    var fillPoints = [];
    samples.forEach(function (s, idx) {
      if (s.avg_latency_ms === null || s.avg_latency_ms === undefined) {
        started = false;
        return;
      }
      var x = xFor(idx);
      var y = yFor(s.avg_latency_ms);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
      fillPoints.push([x, y]);
    });
    ctx.strokeStyle = COLORS.line;
    ctx.lineWidth = 2;
    ctx.stroke();

    if (fillPoints.length > 1) {
      ctx.lineTo(fillPoints[fillPoints.length - 1][0], PAD.top + plotH);
      ctx.lineTo(fillPoints[0][0], PAD.top + plotH);
      ctx.closePath();
      ctx.fillStyle = COLORS.fill;
      ctx.fill();
    }

    // Point markers — red for failed samples, cyan dot for successful ones
    samples.forEach(function (s, idx) {
      var x = xFor(idx);
      var ok = s.success && s.avg_latency_ms !== null && s.avg_latency_ms !== undefined;
      var y = ok ? yFor(s.avg_latency_ms) : PAD.top + plotH;
      ctx.beginPath();
      ctx.arc(x, y, ok ? 2.5 : 3.5, 0, Math.PI * 2);
      ctx.fillStyle = ok ? COLORS.line : COLORS.fail;
      ctx.fill();
    });
  }

  window.NetworkTestChart = { render: render };
})();
