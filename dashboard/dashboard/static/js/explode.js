/**
 * Service Bus page easter egg — Ctrl + 6 + 7 triggers a Titanic-style
 * sinking scene.  The ocean rises from below and every page component
 * tilts, bobs, and sinks beneath the waves.
 * Fully self-contained — no external dependencies.
 */
(function () {
  'use strict';

  // ── Track simultaneous keys ──────────────────────────────────────────────
  var pressed = {};
  var sinking = false;

  document.addEventListener('keydown', function (e) {
    pressed[e.key] = true;
    if (pressed['Control'] && pressed['6'] && pressed['7']) {
      e.preventDefault();
      if (!sinking) triggerSinking();
    }
  });

  document.addEventListener('keyup', function (e) {
    delete pressed[e.key];
  });

  window.addEventListener('blur', function () { pressed = {}; });

  // ── Inject CSS once ──────────────────────────────────────────────────────
  var style = document.createElement('style');
  style.textContent = [
    /* Ocean layer — rises from the bottom of the viewport */
    '.titanic-ocean{',
    '  position:fixed;left:0;bottom:0;width:100%;height:0;',
    '  pointer-events:none;z-index:99990;',
    '  background:linear-gradient(180deg,',
    '    rgba(6,40,61,0.75) 0%,',
    '    rgba(4,56,90,0.88) 20%,',
    '    rgba(2,38,72,0.94) 50%,',
    '    rgba(1,18,40,0.97) 100%);',
    '  transition:height 5s cubic-bezier(0.22,0.61,0.36,1);',
    '}',

    /* Animated wave crest on top of the ocean */
    '.titanic-waves{',
    '  position:absolute;top:-18px;left:0;width:200%;height:24px;',
    '  background:',
    '    url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 1200 24\'%3E%3Cpath d=\'M0 12 Q150 0 300 12 T600 12 T900 12 T1200 12 V24 H0z\' fill=\'rgba(6,40,61,0.85)\'/%3E%3C/svg%3E") repeat-x;',
    '  background-size:600px 24px;',
    '  animation:titanic-wave 3s linear infinite;',
    '}',
    '@keyframes titanic-wave{',
    '  0%{transform:translateX(0)}',
    '  100%{transform:translateX(-600px)}',
    '}',

    /* Foam / whitecap highlights */
    '.titanic-foam{',
    '  position:absolute;top:-10px;left:0;width:200%;height:14px;',
    '  background:',
    '    url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 1200 14\'%3E%3Cpath d=\'M0 8 Q75 2 150 8 T300 8 T450 8 T600 8 T750 8 T900 8 T1050 8 T1200 8\' fill=\'none\' stroke=\'rgba(255,255,255,0.35)\' stroke-width=\'2\'/%3E%3C/svg%3E") repeat-x;',
    '  background-size:600px 14px;',
    '  animation:titanic-foam 2.2s linear infinite;',
    '}',
    '@keyframes titanic-foam{',
    '  0%{transform:translateX(0)}',
    '  100%{transform:translateX(-600px)}',
    '}',

    /* Underwater light rays */
    '.titanic-rays{',
    '  position:absolute;top:0;left:0;width:100%;height:100%;',
    '  background:repeating-linear-gradient(',
    '    105deg,',
    '    transparent,',
    '    transparent 60px,',
    '    rgba(80,180,220,0.04) 60px,',
    '    rgba(80,180,220,0.04) 62px',
    '  );',
    '  animation:titanic-rays 4s ease-in-out infinite alternate;',
    '}',
    '@keyframes titanic-rays{',
    '  0%{opacity:0.3;transform:skewX(0deg)}',
    '  100%{opacity:0.7;transform:skewX(2deg)}',
    '}',

    /* Bubbles that rise from sinking elements */
    '@keyframes titanic-bubble{',
    '  0%{transform:translateY(0) scale(1);opacity:0.7}',
    '  60%{opacity:0.5}',
    '  100%{transform:translateY(var(--rise)) scale(0.3);opacity:0}',
    '}',
    '.titanic-bubble{',
    '  position:fixed;',
    '  pointer-events:none;',
    '  z-index:99995;',
    '  border-radius:50%;',
    '  border:1px solid rgba(150,210,240,0.5);',
    '  background:radial-gradient(circle at 35% 35%,rgba(200,230,255,0.4),rgba(60,140,180,0.15));',
    '  animation:titanic-bubble var(--dur) ease-out forwards;',
    '}',

    /* Ship horn dark overlay flash */
    '.titanic-horn{',
    '  position:fixed;top:0;left:0;width:100%;height:100%;',
    '  background:rgba(0,10,20,0.3);',
    '  pointer-events:none;z-index:100000;',
    '  animation:titanic-horn-fade 1.5s ease-out forwards;',
    '}',
    '@keyframes titanic-horn-fade{',
    '  0%{opacity:1}30%{opacity:0.6}100%{opacity:0}',
    '}',

    /* Gentle body tilt — the whole page lists to starboard */
    '@keyframes titanic-list{',
    '  0%{transform:rotate(0) translateY(0)}',
    '  40%{transform:rotate(1.5deg) translateY(30px)}',
    '  70%{transform:rotate(3deg) translateY(80px)}',
    '  100%{transform:rotate(5deg) translateY(200px)}',
    '}',
    '.titanic-list{',
    '  transform-origin:bottom right;',
    '  animation:titanic-list 5s cubic-bezier(0.22,0.61,0.36,1) forwards;',
    '}',

    /* Individual element sinking — drops below waterline */
    '@keyframes titanic-sink{',
    '  0%{transform:translateY(0) rotate(0deg);opacity:1;filter:brightness(1)}',
    '  30%{opacity:1;filter:brightness(0.85)}',
    '  60%{filter:brightness(0.6) saturate(0.5)}',
    '  100%{transform:translateY(var(--sink-y)) rotate(var(--sink-r));opacity:0.15;filter:brightness(0.3) saturate(0.2) blur(1px)}',
    '}',
    '.titanic-sink{',
    '  animation:titanic-sink var(--sink-dur) cubic-bezier(0.22,0.61,0.36,1) forwards;',
    '  pointer-events:none;',
    '}',
  ].join('\n');
  document.head.appendChild(style);

  // ── Helpers ──────────────────────────────────────────────────────────────
  function rand(min, max) { return Math.random() * (max - min) + min; }

  function spawnBubbles(el) {
    var rect = el.getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var count = 5 + Math.floor(Math.random() * 8);

    for (var i = 0; i < count; i++) {
      var b = document.createElement('div');
      b.className = 'titanic-bubble';
      var size = rand(4, 14);
      var rise = rand(-80, -250);
      var dur = rand(1.5, 3.5);
      b.style.setProperty('--rise', rise + 'px');
      b.style.setProperty('--dur', dur + 's');
      b.style.width = size + 'px';
      b.style.height = size + 'px';
      b.style.left = (cx + rand(-rect.width / 3, rect.width / 3)) + 'px';
      b.style.top = (cy + rand(-10, 10)) + 'px';
      document.body.appendChild(b);
      (function (node, d) {
        setTimeout(function () { node.remove(); }, d * 1000 + 200);
      })(b, dur);
    }
  }

  // Continuous ambient bubbles rising from the deep
  function startAmbientBubbles(ocean, duration) {
    var interval = setInterval(function () {
      var b = document.createElement('div');
      b.className = 'titanic-bubble';
      var size = rand(3, 10);
      var rise = rand(-100, -400);
      var dur = rand(2, 5);
      b.style.setProperty('--rise', rise + 'px');
      b.style.setProperty('--dur', dur + 's');
      b.style.width = size + 'px';
      b.style.height = size + 'px';
      b.style.left = rand(5, 95) + 'vw';
      b.style.top = (window.innerHeight - rand(20, parseInt(ocean.style.height) || 100)) + 'px';
      document.body.appendChild(b);
      setTimeout(function () { b.remove(); }, dur * 1000 + 200);
    }, 150);
    setTimeout(function () { clearInterval(interval); }, duration);
  }

  // ── Main sinking scene ───────────────────────────────────────────────────
  function triggerSinking() {
    sinking = true;
    var body = document.body;

    // Dark flash — the horn sounds
    var horn = document.createElement('div');
    horn.className = 'titanic-horn';
    body.appendChild(horn);
    setTimeout(function () { horn.remove(); }, 1600);

    // Create ocean layer
    var ocean = document.createElement('div');
    ocean.className = 'titanic-ocean';
    var waves = document.createElement('div');
    waves.className = 'titanic-waves';
    var foam = document.createElement('div');
    foam.className = 'titanic-foam';
    var rays = document.createElement('div');
    rays.className = 'titanic-rays';
    ocean.appendChild(rays);
    ocean.appendChild(waves);
    ocean.appendChild(foam);
    body.appendChild(ocean);

    // Trigger ocean rise — quarter of the page
    requestAnimationFrame(function () {
      ocean.style.height = '25vh';
    });

    // Start ambient bubbles
    startAmbientBubbles(ocean, 8000);

    // Tilt the entire page
    var wrapper = document.querySelector('.page-wrapper') || document.querySelector('main') || body;
    wrapper.classList.add('titanic-list');

    // Collect sinkable elements — stagger them sinking one by one
    var targets = wrapper.querySelectorAll(
      'h1,h2,h3,h4,h5,h6,p,a,button,table,thead,tbody,tr,' +
      '.kpi-card,.dash-card,.section-header,.btn-dash,.status-badge,.queue-table-wrapper,' +
      '.kpi-strip,.page-header,.page-subtitle'
    );

    var originals = [];
    var elList = Array.prototype.slice.call(targets);

    // Sort by vertical position — elements near the bottom sink first
    elList.sort(function (a, b) {
      return b.getBoundingClientRect().top - a.getBoundingClientRect().top;
    });

    elList.forEach(function (el, i) {
      originals.push({
        el: el,
        cssText: el.style.cssText,
        classes: el.className,
      });

      var delay = 800 + i * 180;
      setTimeout(function () {
        // Sink to the very bottom of the viewport
        var elRect = el.getBoundingClientRect();
        var sinkY = window.innerHeight - elRect.top + rand(20, 80);
        var sinkR = rand(-8, 8);
        var sinkDur = rand(2.5, 4.5);
        el.style.setProperty('--sink-y', sinkY + 'px');
        el.style.setProperty('--sink-r', sinkR + 'deg');
        el.style.setProperty('--sink-dur', sinkDur + 's');
        el.classList.add('titanic-sink');
        spawnBubbles(el);

        // More bubbles mid-sink
        setTimeout(function () { spawnBubbles(el); }, sinkDur * 400);
      }, delay);
    });

    // Reset after 9 seconds — the sea recedes
    setTimeout(function () {
      ocean.style.transition = 'height 2s cubic-bezier(0.55,0.09,0.68,0.53)';
      ocean.style.height = '0';
      setTimeout(function () { ocean.remove(); }, 2200);

      wrapper.classList.remove('titanic-list');

      document.querySelectorAll('.titanic-bubble').forEach(function (b) { b.remove(); });

      originals.forEach(function (o) {
        o.el.className = o.classes;
        o.el.style.cssText = o.cssText;
      });

      sinking = false;
    }, 9000);
  }

}());
