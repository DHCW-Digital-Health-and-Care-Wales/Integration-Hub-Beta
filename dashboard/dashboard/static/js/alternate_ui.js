/**
 * Service Bus page easter egg — Ctrl + 6 + 7
 * All page elements vanish, the ocean rises, one element becomes a boat
 * that sails across the screen and crashes into an iceberg. Then everything resets.
 * Fully self-contained — no external dependencies.
 */
(function () {
  'use strict';

  var pressed = {};
  var active = false;

  document.addEventListener('keydown', function (e) {
    pressed[e.key] = true;
    if (pressed['Control'] && pressed['6'] && pressed['7']) {
      e.preventDefault();
      if (!active) runScene();
    }
  });
  document.addEventListener('keyup', function (e) { delete pressed[e.key]; });
  window.addEventListener('blur', function () { pressed = {}; });

  // ── Inject styles ────────────────────────────────────────────────────────
  var css = document.createElement('style');
  css.textContent = [
    /* Ocean */
    '.ee-ocean{',
    '  position:fixed;left:0;bottom:0;width:100%;height:0;',
    '  pointer-events:none;z-index:99990;',
    '  background:linear-gradient(180deg,',
    '    rgba(6,40,61,0.80) 0%,rgba(4,56,90,0.90) 30%,rgba(1,18,40,0.97) 100%);',
    '  transition:height 3s cubic-bezier(0.22,0.61,0.36,1);',
    '}',
    '.ee-waves{',
    '  position:absolute;top:-18px;left:0;width:200%;height:24px;',
    '  background:url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 1200 24\'%3E%3Cpath d=\'M0 12Q150 0 300 12T600 12T900 12T1200 12V24H0z\' fill=\'rgba(6,40,61,0.85)\'/%3E%3C/svg%3E") repeat-x;',
    '  background-size:600px 24px;',
    '  animation:ee-wave 3s linear infinite;',
    '}',
    '@keyframes ee-wave{0%{transform:translateX(0)}100%{transform:translateX(-600px)}}',
    '.ee-foam{',
    '  position:absolute;top:-10px;left:0;width:200%;height:14px;',
    '  background:url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 1200 14\'%3E%3Cpath d=\'M0 8Q75 2 150 8T300 8T450 8T600 8T750 8T900 8T1050 8T1200 8\' fill=\'none\' stroke=\'rgba(255,255,255,0.35)\' stroke-width=\'2\'/%3E%3C/svg%3E") repeat-x;',
    '  background-size:600px 14px;animation:ee-foam 2.2s linear infinite;',
    '}',
    '@keyframes ee-foam{0%{transform:translateX(0)}100%{transform:translateX(-600px)}}',
    '.ee-rays{',
    '  position:absolute;top:0;left:0;width:100%;height:100%;',
    '  background:repeating-linear-gradient(105deg,transparent,transparent 60px,rgba(80,180,220,0.04) 60px,rgba(80,180,220,0.04) 62px);',
    '  animation:ee-rays 4s ease-in-out infinite alternate;',
    '}',
    '@keyframes ee-rays{0%{opacity:.3;transform:skewX(0)}100%{opacity:.7;transform:skewX(2deg)}}',

    /* Horn flash */
    '.ee-horn{',
    '  position:fixed;top:0;left:0;width:100%;height:100%;',
    '  background:rgba(0,10,20,0.35);pointer-events:none;z-index:100000;',
    '  animation:ee-horn 1.5s ease-out forwards;',
    '}',
    '@keyframes ee-horn{0%{opacity:1}30%{opacity:.6}100%{opacity:0}}',

    /* Page elements fade out */
    '.ee-vanish{',
    '  transition:opacity 1s ease-out,transform 1s ease-out;',
    '  opacity:0!important;transform:scale(0.95);pointer-events:none;',
    '}',

    /* Boat — an SVG ship rendered as a fixed element */
    '.ee-boat{',
    '  position:fixed;z-index:99995;pointer-events:none;',
    '  transition:none;',
    '}',
    '.ee-boat svg{display:block;}',
    /* Gentle bobbing while sailing */
    '.ee-boat--sailing{',
    '  animation:ee-bob 1.2s ease-in-out infinite;',
    '}',
    '@keyframes ee-bob{',
    '  0%,100%{transform:translateY(0) rotate(-1deg)}',
    '  50%{transform:translateY(-8px) rotate(1deg)}',
    '}',

    /* Iceberg */
    '.ee-iceberg{',
    '  position:fixed;z-index:99993;pointer-events:none;',
    '}',
    '.ee-iceberg svg{display:block;}',

    /* Smoke puffs from the funnel */
    '.ee-smoke{',
    '  position:fixed;z-index:99996;pointer-events:none;',
    '  width:12px;height:12px;border-radius:50%;',
    '  background:rgba(180,180,180,0.5);',
    '  animation:ee-smoke var(--dur) ease-out forwards;',
    '}',
    '@keyframes ee-smoke{',
    '  0%{transform:translate(0,0) scale(1);opacity:.6}',
    '  100%{transform:translate(var(--dx),var(--dy)) scale(3);opacity:0}',
    '}',

    /* Debris after collision */
    '.ee-debris{',
    '  position:fixed;z-index:99997;pointer-events:none;',
    '  animation:ee-debris var(--dur) ease-out forwards;',
    '}',
    '@keyframes ee-debris{',
    '  0%{transform:translate(0,0) rotate(0);opacity:1}',
    '  100%{transform:translate(var(--dx),var(--dy)) rotate(var(--rot));opacity:0}',
    '}',

    /* Splash ring on impact */
    '.ee-splash{',
    '  position:fixed;z-index:99998;pointer-events:none;',
    '  border:3px solid rgba(200,230,255,0.6);border-radius:50%;',
    '  animation:ee-splash 1.2s ease-out forwards;',
    '}',
    '@keyframes ee-splash{',
    '  0%{width:10px;height:10px;opacity:1;transform:translate(-5px,-5px)}',
    '  100%{width:200px;height:100px;opacity:0;transform:translate(-100px,-50px)}',
    '}',

    /* Sinking after collision */
    '.ee-sinking{',
    '  animation:ee-sink 4s cubic-bezier(0.4,0,0.6,1) forwards;',
    '}',
    '@keyframes ee-sink{',
    '  0%{transform:translateY(0) rotate(0)}',
    '  40%{transform:translateY(20px) rotate(12deg)}',
    '  100%{transform:translateY(300px) rotate(25deg);opacity:0}',
    '}',
  ].join('\n');
  document.head.appendChild(css);

  // ── Helpers ──────────────────────────────────────────────────────────────
  function rand(a, b) { return Math.random() * (b - a) + a; }

  function makeSVGBoat() {
    // A side-view ship: hull, cabin, funnel, portholes
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 180 100');
    svg.setAttribute('width', '180');
    svg.setAttribute('height', '100');
    svg.innerHTML =
      // Hull
      '<path d="M10 65 L30 90 L150 90 L170 65 Z" fill="#1B294A" stroke="#325083" stroke-width="2"/>' +
      // Deck
      '<rect x="35" y="50" width="110" height="18" rx="3" fill="#325083"/>' +
      // Cabin
      '<rect x="55" y="30" width="60" height="22" rx="2" fill="#F8CA4D"/>' +
      // Cabin windows
      '<rect x="62" y="35" width="8" height="8" rx="1" fill="#12A3C9" opacity="0.8"/>' +
      '<rect x="76" y="35" width="8" height="8" rx="1" fill="#12A3C9" opacity="0.8"/>' +
      '<rect x="90" y="35" width="8" height="8" rx="1" fill="#12A3C9" opacity="0.8"/>' +
      '<rect x="104" y="35" width="8" height="8" rx="1" fill="#12A3C9" opacity="0.8"/>' +
      // Funnel
      '<rect x="78" y="12" width="14" height="20" rx="2" fill="#C0392B"/>' +
      '<rect x="76" y="10" width="18" height="5" rx="1" fill="#1B294A"/>' +
      // Portholes on hull
      '<circle cx="55" cy="72" r="3" fill="#12A3C9" opacity="0.6"/>' +
      '<circle cx="75" cy="72" r="3" fill="#12A3C9" opacity="0.6"/>' +
      '<circle cx="95" cy="72" r="3" fill="#12A3C9" opacity="0.6"/>' +
      '<circle cx="115" cy="72" r="3" fill="#12A3C9" opacity="0.6"/>' +
      '<circle cx="135" cy="72" r="3" fill="#12A3C9" opacity="0.6"/>' +
      // Bow accent
      '<path d="M10 65 L25 55 L35 50 L35 65 Z" fill="#325083"/>';
    return svg;
  }

  function makeSVGIceberg() {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 140 180');
    svg.setAttribute('width', '140');
    svg.setAttribute('height', '180');
    svg.innerHTML =
      // Above-water peak (white/blue)
      '<path d="M70 5 L20 80 L45 75 L30 85 L110 85 L95 75 L120 80 Z" fill="#E8F0FE" stroke="#B0C4DE" stroke-width="1.5"/>' +
      // Facets / highlights
      '<path d="M70 5 L55 50 L80 45 Z" fill="rgba(176,196,222,0.4)"/>' +
      '<path d="M55 50 L30 85 L70 70 Z" fill="rgba(176,196,222,0.25)"/>' +
      // Waterline
      '<line x1="10" y1="85" x2="130" y2="85" stroke="rgba(100,180,220,0.5)" stroke-width="2" stroke-dasharray="4,3"/>' +
      // Below-water mass (darker, translucent)
      '<path d="M20 85 L5 150 L40 175 L100 175 L135 150 L120 85 Z" fill="rgba(60,130,170,0.3)" stroke="rgba(80,150,190,0.4)" stroke-width="1"/>' +
      '<path d="M50 85 L35 140 L75 130 Z" fill="rgba(80,160,200,0.15)"/>';
    return svg;
  }

  function spawnSmoke(x, y) {
    var s = document.createElement('div');
    s.className = 'ee-smoke';
    s.style.left = x + 'px';
    s.style.top = y + 'px';
    var dur = rand(1.5, 3);
    s.style.setProperty('--dur', dur + 's');
    s.style.setProperty('--dx', rand(-30, 10) + 'px');
    s.style.setProperty('--dy', rand(-40, -80) + 'px');
    s.style.width = rand(8, 16) + 'px';
    s.style.height = s.style.width;
    document.body.appendChild(s);
    setTimeout(function () { s.remove(); }, dur * 1000 + 100);
  }

  function spawnDebris(x, y, count) {
    for (var i = 0; i < count; i++) {
      var d = document.createElement('div');
      d.className = 'ee-debris';
      var size = rand(4, 12);
      d.style.width = size + 'px';
      d.style.height = size + 'px';
      d.style.left = x + 'px';
      d.style.top = y + 'px';
      d.style.background = ['#E8F0FE', '#B0C4DE', '#1B294A', '#325083', '#F8CA4D'][Math.floor(rand(0, 5))];
      d.style.borderRadius = rand(0, 1) > 0.5 ? '50%' : '2px';
      var dur = rand(0.8, 2);
      d.style.setProperty('--dur', dur + 's');
      d.style.setProperty('--dx', rand(-120, 120) + 'px');
      d.style.setProperty('--dy', rand(-150, 50) + 'px');
      d.style.setProperty('--rot', rand(-360, 360) + 'deg');
      document.body.appendChild(d);
      setTimeout(function (el) { el.remove(); }, dur * 1000 + 100, d);
    }
  }

  function spawnSplash(x, y) {
    for (var i = 0; i < 3; i++) {
      var s = document.createElement('div');
      s.className = 'ee-splash';
      s.style.left = (x + rand(-20, 20)) + 'px';
      s.style.top = (y + rand(-10, 10)) + 'px';
      s.style.animationDelay = (i * 0.15) + 's';
      document.body.appendChild(s);
      setTimeout(function (el) { el.remove(); }, 1500, s);
    }
  }

  // ── Main scene ───────────────────────────────────────────────────────────
  function runScene() {
    active = true;
    var body = document.body;

    // ── 1. Horn flash ──
    var horn = document.createElement('div');
    horn.className = 'ee-horn';
    body.appendChild(horn);
    setTimeout(function () { horn.remove(); }, 1600);

    // ── 2. Collect all page elements & save state ──
    var wrapper = document.querySelector('.page-wrapper') || document.querySelector('main') || body;
    var targets = wrapper.querySelectorAll(
      'h1,h2,h3,h4,h5,h6,p,a,button,table,thead,tbody,tr,' +
      '.kpi-card,.dash-card,.section-header,.btn-dash,.status-badge,.queue-table-wrapper,' +
      '.kpi-strip,.page-header,.page-subtitle,.sidebar,.nav-link,.filter-banner'
    );
    var elList = Array.prototype.slice.call(targets);
    var originals = [];

    // Pick one random element to become the boat
    var boatIndex = Math.floor(rand(0, elList.length));

    // ── 3. Fade out all elements except the chosen one ──
    elList.forEach(function (el, i) {
      originals.push({ el: el, cssText: el.style.cssText, classes: el.className });
      if (i !== boatIndex) {
        el.classList.add('ee-vanish');
      }
    });

    // ── 4. Build the ocean (same as before) ──
    var ocean = document.createElement('div');
    ocean.className = 'ee-ocean';
    ocean.innerHTML = '<div class="ee-rays"></div><div class="ee-waves"></div><div class="ee-foam"></div>';
    body.appendChild(ocean);
    requestAnimationFrame(function () { ocean.style.height = '25vh'; });

    // ── 5. After elements vanish, transform the chosen one into a boat ──
    var boatEl = document.createElement('div');
    boatEl.className = 'ee-boat';
    boatEl.appendChild(makeSVGBoat());

    // Position boat at left side, sitting on the waterline
    var waterY = window.innerHeight * 0.75; // top of 25vh ocean
    boatEl.style.left = '-200px';
    boatEl.style.top = (waterY - 70) + 'px'; // hull sits on water

    setTimeout(function () {
      // Hide the original element
      elList[boatIndex].classList.add('ee-vanish');
      body.appendChild(boatEl);
      boatEl.classList.add('ee-boat--sailing');

      // ── 6. Place iceberg on the right side ──
      var iceberg = document.createElement('div');
      iceberg.className = 'ee-iceberg';
      iceberg.appendChild(makeSVGIceberg());
      var icebergX = window.innerWidth * 0.72;
      iceberg.style.left = icebergX + 'px';
      iceberg.style.top = (waterY - 85) + 'px'; // peak above water
      body.appendChild(iceberg);

      // ── 7. Sail the boat across ──
      var boatX = -200;
      var collisionX = icebergX - 160; // stop before iceberg
      var sailDuration = 5000;
      var startTime = performance.now();
      var smokeTimer = 0;

      function animateSail(now) {
        var elapsed = now - startTime;
        var t = Math.min(elapsed / sailDuration, 1);
        // Ease out
        var eased = 1 - Math.pow(1 - t, 2);
        var currentX = boatX + (collisionX - boatX) * eased;
        boatEl.style.left = currentX + 'px';

        // Funnel smoke
        smokeTimer += elapsed;
        if (elapsed - smokeTimer > 200 || smokeTimer === 0) {
          smokeTimer = elapsed;
          spawnSmoke(currentX + 85, waterY - 90);
        }

        if (t < 1) {
          requestAnimationFrame(animateSail);
        } else {
          onCollision(boatEl, iceberg, waterY, icebergX);
        }
      }
      requestAnimationFrame(animateSail);
    }, 1500); // wait for elements to vanish + ocean to rise

    // ── 8. Collision! ──
    function onCollision(boat, iceberg, wy, ix) {
      boat.classList.remove('ee-boat--sailing');

      // Impact effects
      spawnDebris(ix - 20, wy - 40, 20);
      spawnSplash(ix - 10, wy);

      // Screen shake
      body.style.transition = 'none';
      var shakes = 0;
      var shakeInterval = setInterval(function () {
        var dx = rand(-6, 6), dy = rand(-4, 4);
        body.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
        shakes++;
        if (shakes > 12) {
          clearInterval(shakeInterval);
          body.style.transform = '';
        }
      }, 50);

      // Boat starts sinking
      setTimeout(function () {
        boat.classList.add('ee-sinking');
      }, 400);

      // More debris after a beat
      setTimeout(function () {
        spawnDebris(ix - 30, wy - 20, 10);
        spawnSplash(ix + 20, wy + 10);
      }, 600);

      // ── 9. Reset everything ──
      setTimeout(function () {
        // Drain ocean
        ocean.style.transition = 'height 2s cubic-bezier(0.55,0.09,0.68,0.53)';
        ocean.style.height = '0';
        setTimeout(function () { ocean.remove(); }, 2200);

        // Remove boat & iceberg
        boat.remove();
        iceberg.remove();

        // Clean up any leftover effects
        document.querySelectorAll('.ee-smoke,.ee-debris,.ee-splash').forEach(function (el) { el.remove(); });

        // Restore all original elements
        originals.forEach(function (o) {
          o.el.className = o.classes;
          o.el.style.cssText = o.cssText;
        });

        body.style.transform = '';
        body.style.transition = '';
        active = false;
      }, 5000); // 5s after collision
    }
  }

}());
