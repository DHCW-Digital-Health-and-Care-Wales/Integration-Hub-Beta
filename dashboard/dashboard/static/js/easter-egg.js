/**
 * Easter egg — animated LEGO man using HTML5 Canvas 2D.
 * He is singing "Everything is Awesome" from The LEGO Movie.
 *
 * Trigger: Konami code  ↑ ↑ ↓ ↓ ← → ← → B A
 * Dismiss: ESC key or the × button on the panel.
 *
 * Fully self-contained — no external dependencies.
 */
(function () {
  'use strict';

  // ── Konami code listener ────────────────────────────────────────────────
  const KONAMI = [
    'ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown',
    'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight',
    'b', 'a',
  ];
  let seq = 0;

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { hideEgg(); return; }
    if (e.key === KONAMI[seq]) {
      seq++;
      if (seq === KONAMI.length) { seq = 0; showEgg(); }
    } else {
      seq = (e.key === KONAMI[0]) ? 1 : 0;
    }
  });

  // Close button — use event delegation so it works regardless of load order
  document.addEventListener('click', function (e) {
    if (e.target && e.target.id === 'lego-close-btn') hideEgg();
  });

  // ── State ────────────────────────────────────────────────────────────────
  let active     = false;
  let rafId      = null;
  let noteTimer  = null;
  let lyricTimer = null;

  // ── Show / hide ──────────────────────────────────────────────────────────
  function showEgg() {
    if (active) return;
    active = true;
    const panel = document.getElementById('lego-panel');
    if (!panel) return;
    panel.style.display = 'flex';
    requestAnimationFrame(function () { panel.classList.add('lego-panel--visible'); });
    startCanvas();
    startNotes();
    startLyrics();
  }

  function hideEgg() {
    if (!active) return;
    active = false;
    const panel = document.getElementById('lego-panel');
    if (panel) panel.classList.remove('lego-panel--visible');
    clearInterval(noteTimer);
    clearInterval(lyricTimer);
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    setTimeout(function () {
      if (panel) panel.style.display = 'none';
      document.querySelectorAll('.lego-note').forEach(function (n) { n.remove(); });
      // Clear canvas so a fresh draw starts next time
      const canvas = document.getElementById('lego-canvas');
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
    }, 350);
  }

  // ── Floating musical notes ────────────────────────────────────────────────
  const NOTE_CHARS  = ['♪', '♫', '♩', '♬'];
  const NOTE_COLORS = ['#FFD700', '#12A3C9', '#F8CA4D', '#ffffff', '#f97316'];

  function spawnNote() {
    const panel = document.getElementById('lego-panel');
    if (!panel) return;
    const note       = document.createElement('span');
    note.className   = 'lego-note';
    note.textContent = NOTE_CHARS[Math.floor(Math.random() * NOTE_CHARS.length)];
    note.style.left  = (20 + Math.random() * 210) + 'px';
    note.style.color = NOTE_COLORS[Math.floor(Math.random() * NOTE_COLORS.length)];
    panel.appendChild(note);
    setTimeout(function () { note.remove(); }, 2200);
  }

  function startNotes() {
    spawnNote();
    noteTimer = setInterval(spawnNote, 520);
  }

  // ── Lyrics ───────────────────────────────────────────────────────────────
  const LYRICS = [
    '♪ Everything is awesome! ♪',
    "♪ Everything is cool when you're part of a team ♪",
    '♪ Everything is awesome! ♪',
    "♪ When you're living our dream ♪",
    '♪ Everything is better when we stick together ♪',
    '♪ Side by side, you and I gonna win forever ♪',
    "♪ Let's party forever! ♪",
    "♪ We're the same, I'm like you, you're like me ♪",
    "♪ We're all working in harmony ♪",
    '♪ Everything is AWESOME! ♪',
  ];
  let lyricIdx = 0;

  function cycleLyric() {
    const el = document.getElementById('lego-lyrics');
    if (!el) return;
    el.style.opacity = '0';
    setTimeout(function () {
      el.textContent = LYRICS[lyricIdx % LYRICS.length];
      lyricIdx++;
      el.style.opacity = '1';
    }, 300);
  }

  function startLyrics() {
    lyricIdx = 0;
    cycleLyric();
    lyricTimer = setInterval(cycleLyric, 2600);
  }

  // ── Canvas 2D: floating background bricks ────────────────────────────────
  // Pre-generate random brick positions once so they don't re-randomise on hide/show
  const BRICKS = (function () {
    const cols = ['#FFD700', '#12A3C9', '#325083', '#e05555', '#44bb66', '#F8CA4D'];
    return cols.map(function (col, i) {
      return {
        col:    col,
        x:      28 + (i * 37) % 200,
        baseY:  14 + (i * 23) % 60,
        yOff:   (i * 1.1),
        speed:  0.38 + (i * 0.07),
      };
    });
  }());

  function drawBrick(ctx, x, y, col) {
    ctx.fillStyle = col;
    ctx.fillRect(x - 18, y - 10, 36, 20);
    // Two studs on top
    ctx.beginPath();
    ctx.arc(x - 8, y - 14, 5, 0, Math.PI * 2);
    ctx.arc(x + 8, y - 14, 5, 0, Math.PI * 2);
    ctx.fill();
  }

  // ── Canvas 2D: draw the LEGO man ─────────────────────────────────────────
  // Coordinates are relative to the man's centre-bottom (cx, baseY).
  // All measurements in canvas pixels (canvas is 260 × 295).
  function drawMan(ctx, cx, baseY, beat, t) {
    const bounce = Math.sin(t * 7.25) * 4;    // full-body vertical bounce
    const sway   = Math.sin(t * 0.38) * 5;    // gentle left-right sway
    const by     = baseY + bounce;             // adjusted baseline

    // ── LEGS ──
    ctx.fillStyle = '#1B294A';
    ctx.fillRect(cx - 27 + sway, by - 52, 23, 50);   // left leg
    ctx.fillRect(cx + 4  + sway, by - 52, 23, 50);   // right leg

    // ── FEET ──
    ctx.fillRect(cx - 30 + sway, by - 10, 27, 12);
    ctx.fillRect(cx + 3  + sway, by - 10, 27, 12);

    // ── HIPS ──
    ctx.fillRect(cx - 29 + sway, by - 69, 58, 19);

    // ── TORSO ──
    ctx.fillStyle = '#325083';
    ctx.fillRect(cx - 28 + sway, by - 122, 56, 55);

    // DHCW cyan badge on chest
    ctx.fillStyle = '#12A3C9';
    ctx.fillRect(cx - 13 + sway, by - 108, 26, 12);

    // ── ARMS — both raised, concert pumping ──
    const pump = Math.sin(t * 7.25) * 0.35;
    const HALF_PI = Math.PI / 2;

    // Left arm
    ctx.save();
    ctx.translate(cx - 28 + sway, by - 112);
    ctx.rotate(-(HALF_PI * 0.9 + pump));
    ctx.fillStyle = '#325083';
    ctx.fillRect(-8, 0, 16, 40);
    ctx.fillStyle = '#FFD700';
    ctx.beginPath();
    ctx.arc(0, 46, 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // Right arm
    ctx.save();
    ctx.translate(cx + 28 + sway, by - 112);
    ctx.rotate(HALF_PI * 0.9 - pump);
    ctx.fillStyle = '#325083';
    ctx.fillRect(-8, 0, 16, 40);
    ctx.fillStyle = '#FFD700';
    ctx.beginPath();
    ctx.arc(0, 46, 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // ── NECK ──
    ctx.fillStyle = '#FFD700';
    ctx.fillRect(cx - 9 + sway, by - 134, 18, 14);

    // ── HEAD — slight bob ──
    const headBob  = Math.sin(t * 7.25) * 2;
    const headSway = Math.sin(t * 0.6) * 4;
    const hx = cx + sway + headSway;
    const hy = by - 188 + headBob;

    // Head block
    ctx.fillStyle = '#FFD700';
    ctx.beginPath();
    ctx.roundRect(hx - 24, hy, 48, 52, 6);
    ctx.fill();

    // Stud on top
    ctx.beginPath();
    ctx.arc(hx, hy - 6, 8, 0, Math.PI * 2);
    ctx.fill();

    // Eyes
    ctx.fillStyle = '#111111';
    ctx.beginPath();
    ctx.arc(hx - 11, hy + 18, 5, 0, Math.PI * 2);
    ctx.arc(hx + 11, hy + 18, 5, 0, Math.PI * 2);
    ctx.fill();

    // Mouth — open/close on beat
    const mouthOpen = 0.1 + beat * 0.85;
    const mcy = hy + 37;
    const mcx = hx;

    // Dark red inner mouth (ellipse opens on beat)
    ctx.fillStyle = '#AA1133';
    ctx.beginPath();
    ctx.ellipse(mcx, mcy, 12, 12 * mouthOpen, 0, 0, Math.PI);
    ctx.fill();

    // Teeth flash when mouth is open
    if (beat > 0.25) {
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(mcx - 8, mcy - 2, 16, 4);
    }

    // Outer lip outline
    ctx.strokeStyle = '#111111';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(mcx, mcy, 13, 0, Math.PI);
    ctx.stroke();
  }

  // ── Main animation loop ───────────────────────────────────────────────────
  function startCanvas() {
    const canvas = document.getElementById('lego-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W   = canvas.width;   // 260
    const H   = canvas.height;  // 295

    let t = 0;

    function frame() {
      if (!active) return;
      rafId = requestAnimationFrame(frame);
      t += 0.038;

      // Beat pulse: ~140 BPM at 60 fps
      const beat = Math.max(0, Math.sin(t * 14.5));

      // Background
      ctx.fillStyle = '#1b294a';
      ctx.fillRect(0, 0, W, H);

      // Floating bricks
      BRICKS.forEach(function (b) {
        const y = b.baseY + Math.sin(t * b.speed + b.yOff) * 10;
        drawBrick(ctx, b.x, y, b.col);
      });

      // LEGO man — centred, standing at 90% height from top
      drawMan(ctx, W / 2, H - 10, beat, t);
    }

    frame();
  }

}());
