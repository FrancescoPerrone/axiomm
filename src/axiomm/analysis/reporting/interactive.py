"""Client-side interactivity for HTML reports (stage two, S4).

A self-contained, dependency-free layer the ``html`` backend injects so a report
becomes a live workspace. On a wide screen the **whole viewport is a free
canvas**: every item — the section cards *and* the masthead (title + opening
paragraph) — can be dragged anywhere by its handle, resized from its corner,
raised above its neighbours by hovering or clicking it (so a covered card's
controls surface), and minimised to a dock of pills along the bottom of the
window (click a pill to restore it). Titles/paragraphs edit in place. On a narrow
screen (phone) it is a readable vertical stack.

**The report always opens in its default arrangement.** Customisation is live for
the viewing session only — nothing is persisted, so every open or refresh shows
the clean default view (a fresh reader never sees a rearranged/scattered layout
and is never tipped off that it is customisable). Found by touch; no labels; no
external assets.
"""

from __future__ import annotations

INTERACTIVE_CSS = """
.canvas-item { position: relative; }
.masthead { display: flex; flex-direction: column; gap: .35rem; }
.module-handle { position: absolute; top: .55rem; right: .55rem; width: 1.5rem; height: 1.5rem;
  border-radius: 7px; cursor: grab; opacity: 0; transition: opacity .2s, background .2s;
  display: flex; align-items: center; justify-content: center; color: var(--muted);
  touch-action: none; user-select: none; z-index: 3; }
.module-handle::before { content: "\\2059\\2059"; letter-spacing: -2px; font-size: .9rem; line-height: 1; }
.canvas-item:hover .module-handle { opacity: .5; }
.module-handle:hover { opacity: 1; background: var(--accent-soft); }
@media (hover: none) { .module-handle { opacity: .35; } }
.canvas-item.dragging { z-index: 9999; }
.module.dragging { box-shadow: 0 16px 40px rgba(0,0,0,.22); }
.canvas-item.sizing { user-select: none; }
body.canvas-mode { max-width: none; padding: 1.25rem; }
.report-grid.canvas { position: relative; width: 100%; min-height: calc(100vh - 4rem); }
.report-grid.canvas .canvas-item { position: absolute; margin: 0; }
.module-resize { position: absolute; right: 2px; bottom: 2px; width: 20px; height: 20px;
  cursor: nwse-resize; opacity: 0; transition: opacity .2s; touch-action: none; z-index: 3; }
.module-resize::after { content: ""; position: absolute; right: 5px; bottom: 5px; width: 8px; height: 8px;
  border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); }
.report-grid:not(.canvas) .module-resize { display: none; }
.report-grid.canvas .canvas-item:hover .module-resize { opacity: .5; }
.module-resize:hover { opacity: 1; }
.module-hide { position: absolute; top: .55rem; left: .55rem; width: 1.5rem; height: 1.5rem;
  border-radius: 7px; cursor: pointer; opacity: 0; transition: opacity .2s, background .2s;
  display: flex; align-items: center; justify-content: center; color: var(--muted);
  user-select: none; z-index: 3; }
.module-hide::before { content: "\\2212"; font-size: 1.15rem; line-height: 1; }
.canvas-item:hover .module-hide { opacity: .5; }
.module-hide:hover { opacity: 1; background: var(--accent-soft); }
@media (hover: none) { .module-hide { opacity: .3; } }
.module-placeholder { border: 2px dashed var(--border); border-radius: 10px; }
/* Minimised modules dock as pills along the bottom of the viewport. */
.module-dock { position: fixed; left: 0; right: 0; bottom: 0; z-index: 9998;
  display: flex; flex-wrap: wrap; gap: 6px; padding: 7px 12px; pointer-events: none; }
.module-dock:empty { display: none; }
.dock-tab { pointer-events: auto; cursor: pointer; display: inline-flex; align-items: center;
  gap: .4rem; max-width: 15rem; padding: .3rem .7rem; border-radius: 999px;
  background: var(--panel, #fff); border: 1px solid var(--border, #dadce0);
  color: var(--fg); font-size: .82rem; box-shadow: 0 6px 18px rgba(0,0,0,.14);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dock-tab:hover { border-color: var(--accent, #5aa9e6); }
.dock-tab::before { content: "\\25A2"; color: var(--muted); font-size: .9rem; }
[data-editable] { border-radius: 5px; transition: background .15s; outline: none; }
[data-editable]:hover { background: color-mix(in srgb, var(--accent) 9%, transparent); }
[data-editable]:focus { background: color-mix(in srgb, var(--accent) 6%, transparent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 40%, transparent); }
/* Content wrapper: a resized card zooms this as a whole, so figures AND text grow. */
.module-body { position: relative; }
.report-grid.canvas .module figure img, .report-grid.canvas .module figure svg { cursor: zoom-in; }
/* Click a figure to inspect it large, over a blurred report, with a PNG download. */
.axm-lightbox { position: fixed; inset: 0; z-index: 10000; display: flex; align-items: center;
  justify-content: center; padding: 3vmin; background: rgba(10,12,14,.62);
  -webkit-backdrop-filter: blur(7px); backdrop-filter: blur(7px); }
.axm-lightbox[hidden] { display: none; }
.axm-lb-inner { position: relative; max-width: 96vw; max-height: 92vh; }
.axm-lb-img { max-width: 96vw; max-height: 92vh; display: block; border-radius: 8px;
  background: var(--surface, #fff); box-shadow: 0 24px 70px rgba(0,0,0,.5); }
.axm-lb-bar { position: absolute; top: 8px; right: 8px; display: flex; gap: 6px; }
.axm-lb-bar button { width: 2rem; height: 2rem; border-radius: 7px; border: none; cursor: pointer;
  background: rgba(0,0,0,.55); color: #fff; font-size: 1rem; line-height: 1;
  display: flex; align-items: center; justify-content: center; }
.axm-lb-bar button:hover { background: rgba(0,0,0,.82); }
/* Faint per-table export controls, found on hover (copy for slides/docs, or CSV). */
.axm-tbl-wrap { position: relative; }
.axm-tbl-tools { position: absolute; top: 2px; right: 2px; display: flex; gap: 4px;
  opacity: 0; transition: opacity .2s; z-index: 2; }
.canvas-item:hover .axm-tbl-tools { opacity: .4; }
.axm-tbl-tools:hover { opacity: 1; }
.axm-tbl-tools button { width: 1.5rem; height: 1.5rem; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--border); background: var(--surface); color: var(--muted);
  font-size: .8rem; line-height: 1; display: flex; align-items: center; justify-content: center; }
.axm-tbl-tools button:hover { color: var(--accent); border-color: var(--accent); }
@media (hover: none) { .axm-tbl-tools { opacity: .3; } }
.axm-toast { position: fixed; left: 50%; bottom: 1.5rem; transform: translateX(-50%);
  background: var(--ink); color: var(--bg); font-size: .8rem; padding: .45rem .9rem;
  border-radius: 999px; z-index: 10001; opacity: 0; transition: opacity .2s; pointer-events: none; }
.axm-toast.show { opacity: .95; }
""".strip()


INTERACTIVE_JS = r"""
(function () {
  var grid = document.getElementById('report-grid');
  if (!grid) return;
  var WIDE = '(min-width: 62rem)';

  // Layout is never persisted: every open/refresh is the default view.
  // Clear any layout data left by earlier versions so nothing lingers.
  try {
    Object.keys(localStorage).forEach(function (k) {
      if (k.indexOf('axiomm-report:') === 0) localStorage.removeItem(k);
    });
  } catch (e) {}

  // Wrap each card's content so a resize can zoom it as a whole — figures AND
  // text grow together — while the drag/hide/resize controls stay outside and
  // unscaled. Idempotent.
  function bodyOf(m) {
    var b = m.querySelector(':scope > .module-body');
    if (!b) {
      b = document.createElement('div'); b.className = 'module-body';
      Array.prototype.slice.call(m.childNodes).forEach(function (n) {
        if (n.nodeType === 1 && (n.classList.contains('module-handle') ||
            n.classList.contains('module-resize') || n.classList.contains('module-hide'))) return;
        b.appendChild(n);
      });
      m.insertBefore(b, m.firstChild);
    }
    return b;
  }
  Array.prototype.forEach.call(grid.querySelectorAll('.canvas-item'), bodyOf);

  // --- editable text (live for the session only) --------------------------
  document.querySelectorAll('[data-editable]').forEach(function (el) {
    el.setAttribute('contenteditable', 'true');
    el.setAttribute('spellcheck', 'false');
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && el.tagName !== 'P') { e.preventDefault(); el.blur(); }
    });
    el.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
  });

  // items() excludes cards the viewer has hidden this session (layout ignores them)
  function items() {
    return Array.prototype.filter.call(grid.querySelectorAll('.canvas-item'),
      function (m) { return !m.hidden; });
  }
  function isWide() { return window.matchMedia(WIDE).matches; }
  function isMast(m) { return m.classList.contains('masthead'); }

  Array.prototype.forEach.call(grid.querySelectorAll('.canvas-item'), function (m) {
    if (!m.querySelector('.module-resize')) {
      var h = document.createElement('div'); h.className = 'module-resize'; m.appendChild(h);
    }
    if (!m.querySelector('.module-hide')) {
      var hb = document.createElement('div');
      hb.className = 'module-hide';
      hb.setAttribute('aria-hidden', 'true');
      hb.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
      hb.addEventListener('click', function (e) {
        e.stopPropagation();
        minimize(m);               // -> a pill in the bottom dock; click it to restore
      });
      m.appendChild(hb);
    }
  });

  var maxZ = 1;
  function front(m) { maxZ += 1; m.style.zIndex = maxZ; }
  function canvasHeight() {
    if (!grid.classList.contains('canvas')) return;
    var b = 0;
    items().forEach(function (m) { b = Math.max(b, m.offsetTop + m.offsetHeight); });
    grid.style.height = (b + 28) + 'px';
  }

  // --- minimise to a bottom dock (a hidden module is one click to restore) ----
  var dock = document.createElement('div'); dock.className = 'module-dock';
  document.body.appendChild(dock);
  function titleOf(m) {
    var h = m.querySelector('h1, h2, h3, [data-editable]');
    var t = ((h && h.textContent) || 'Module').trim();
    return t.length > 26 ? t.slice(0, 25) + '…' : (t || 'Module');
  }
  function minimize(m) {
    if (m._tab) return;
    m.hidden = true;
    var tab = document.createElement('button'); tab.type = 'button';
    tab.className = 'dock-tab'; tab.textContent = titleOf(m);
    tab.title = 'Restore “' + titleOf(m) + '”';
    tab.addEventListener('click', function () { restore(m); });
    dock.appendChild(tab); m._tab = tab;
    canvasHeight();
  }
  function restore(m) {
    m.hidden = false;
    if (m._tab) { m._tab.remove(); m._tab = null; }
    front(m);            // reappears where it was, raised above its neighbours
    canvasHeight();
  }

  // Hover a card (after a short rest) to raise it, so an overlapped card's
  // controls become reachable without hunting; a click on it also raises it.
  Array.prototype.forEach.call(grid.querySelectorAll('.canvas-item'), function (m) {
    var ht;
    m.addEventListener('pointerenter', function () {
      if (!grid.classList.contains('canvas')) return;
      clearTimeout(ht); ht = setTimeout(function () { front(m); }, 160);
    });
    m.addEventListener('pointerleave', function () { clearTimeout(ht); });
  });

  // --- default layout (always) --------------------------------------------
  function applyCanvas() {
    grid.classList.add('canvas');
    document.body.classList.add('canvas-mode');
    var cw = grid.clientWidth, GAP = 16, PAD = 8, COLW = 360;
    var all = items();
    all.forEach(function (m) { var b = m.querySelector(':scope > .module-body'); if (b) b.style.zoom = ''; });
    // How many card columns fit across the canvas (>=1). Tiling the modules into
    // columns — instead of one tall centred stack — means a reader sees every
    // available module on open, without a long vertical scroll.
    var ncol = Math.max(1, Math.floor((cw - 2 * PAD + GAP) / (COLW + GAP)));
    // Masthead (title / eyebrow / lede) stays full-width at the very top.
    var topY = PAD;
    all.filter(isMast).forEach(function (m) {
      var w = Math.min(cw - 2 * PAD, 1040);
      m.style.position = 'absolute'; m.style.height = ''; m.style.overflow = '';
      m.style.width = w + 'px';
      m.style.left = Math.max(PAD, (cw - w) / 2) + 'px';
      m.style.top = topY + 'px'; m.style.zIndex = 1;
      topY += m.offsetHeight + GAP;
    });
    // The section cards pack into the columns (masonry: each card drops into the
    // currently-shortest column), so the layout stays compact and balanced.
    var usedW = ncol * COLW + (ncol - 1) * GAP;
    var x0 = Math.max(PAD, (cw - usedW) / 2);
    var colY = []; for (var i = 0; i < ncol; i++) colY.push(topY);
    all.filter(function (m) { return !isMast(m); }).forEach(function (m) {
      var ci = 0; for (var i = 1; i < ncol; i++) { if (colY[i] < colY[ci]) ci = i; }
      m.style.position = 'absolute'; m.style.height = ''; m.style.overflow = '';
      m.style.width = COLW + 'px';
      m.style.left = (x0 + ci * (COLW + GAP)) + 'px';
      m.style.top = colY[ci] + 'px'; m.style.zIndex = 1;
      colY[ci] += m.offsetHeight + GAP;
    });
    maxZ = 1;
    canvasHeight();
  }
  function applyStack() {
    grid.classList.remove('canvas');
    document.body.classList.remove('canvas-mode');
    grid.style.height = '';
    items().forEach(function (m) {
      ['position', 'left', 'top', 'width', 'height', 'overflow', 'zIndex'].forEach(
        function (k) { m.style[k] = ''; });
      var b = m.querySelector(':scope > .module-body'); if (b) b.style.zoom = '';
    });
  }
  function layout() { if (isWide()) applyCanvas(); else applyStack(); }
  try { layout(); } catch (e) {}
  var rt; window.addEventListener('resize', function () {
    clearTimeout(rt); rt = setTimeout(function () { try { layout(); } catch (e) {} }, 150);
  });

  // --- pointer interactions (live; not persisted) --------------------------
  var act = null;
  grid.addEventListener('pointerdown', function (e) {
    var rh = e.target.closest('.module-resize');
    var hh = e.target.closest('.module-handle');
    if (rh && isWide()) {
      var m = rh.closest('.canvas-item'); if (!m) return;
      e.preventDefault(); front(m); m.classList.add('sizing');
      var rb = m.querySelector(':scope > .module-body');
      act = { type: 'resize', m: m, b: rb, sx: e.clientX,
              sw: m.offsetWidth, sz: (rb && parseFloat(rb.style.zoom)) || 1 };
    } else if (hh) {
      var mod = hh.closest('.canvas-item'); if (!mod) return;
      e.preventDefault();
      if (isWide()) {
        front(mod); mod.classList.add('dragging');
        act = { type: 'cdrag', m: mod, sx: e.clientX, sy: e.clientY,
                sl: parseFloat(mod.style.left) || mod.offsetLeft,
                st: parseFloat(mod.style.top) || mod.offsetTop };
      } else {
        var r = mod.getBoundingClientRect();
        var ph = document.createElement('div'); ph.className = 'module-placeholder';
        ph.style.height = r.height + 'px';
        mod.parentNode.insertBefore(ph, mod.nextSibling);
        mod.classList.add('dragging');
        mod.style.width = r.width + 'px'; mod.style.position = 'fixed';
        mod.style.left = r.left + 'px'; mod.style.top = r.top + 'px'; mod.style.pointerEvents = 'none';
        act = { type: 'sdrag', m: mod, ph: ph, offY: e.clientY - r.top };
      }
    } else {
      // Click anywhere on a card to raise it (so a covered card's controls surface).
      var card = e.target.closest('.canvas-item');
      if (card && isWide()) front(card);
      return;
    }
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  });
  function onMove(e) {
    if (!act) return;
    var m = act.m;
    if (act.type === 'cdrag') {
      m.style.left = Math.max(0, act.sl + (e.clientX - act.sx)) + 'px';
      m.style.top = Math.max(0, act.st + (e.clientY - act.sy)) + 'px';
      canvasHeight();
    } else if (act.type === 'resize') {
      // Drag the corner to enlarge: width grows and the card's content zooms with
      // it, so the figure / table / text all get bigger (not just the box).
      var nw = Math.max(220, act.sw + (e.clientX - act.sx));
      if (act.b) act.b.style.zoom = act.sz * nw / act.sw;
      m.style.width = nw + 'px';
      m.style.height = '';
      canvasHeight();
    } else if (act.type === 'sdrag') {
      m.style.top = (e.clientY - act.offY) + 'px';
      var others = items().filter(function (x) { return x !== m; });
      var placed = false;
      for (var i = 0; i < others.length; i++) {
        var r = others[i].getBoundingClientRect();
        if (e.clientY < r.top + r.height / 2) { grid.insertBefore(act.ph, others[i]); placed = true; break; }
      }
      if (!placed) grid.appendChild(act.ph);
    }
  }
  function onUp() {
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onUp);
    if (!act) return;
    var m = act.m;
    if (act.type === 'cdrag' || act.type === 'resize') {
      m.classList.remove('dragging'); m.classList.remove('sizing');
    } else if (act.type === 'sdrag') {
      grid.insertBefore(m, act.ph); act.ph.remove();
      m.classList.remove('dragging');
      ['width', 'position', 'left', 'top', 'pointerEvents'].forEach(function (k) { m.style[k] = ''; });
    }
    act = null;
  }

  // --- tiny transient toast (export feedback) ------------------------------
  var toastEl;
  function toast(msg) {
    if (!toastEl) { toastEl = document.createElement('div'); toastEl.className = 'axm-toast';
      document.body.appendChild(toastEl); }
    toastEl.textContent = msg; toastEl.classList.add('show');
    clearTimeout(toastEl._t); toastEl._t = setTimeout(function () { toastEl.classList.remove('show'); }, 1500);
  }

  // --- figure lightbox: click a figure to inspect it large + download the PNG --
  var lb = document.createElement('div'); lb.className = 'axm-lightbox'; lb.hidden = true;
  lb.innerHTML = '<div class="axm-lb-inner"><img class="axm-lb-img" alt="">' +
    '<div class="axm-lb-bar"><button class="axm-lb-dl" type="button" title="Download PNG">↓</button>' +
    '<button class="axm-lb-x" type="button" title="Close">✕</button></div></div>';
  document.body.appendChild(lb);
  var lbImg = lb.querySelector('.axm-lb-img');
  function openLB(src, name) {
    lbImg.src = src; lbImg.setAttribute('data-name', name || 'figure');
    document.body.appendChild(lb); lb.hidden = false;   // escape the card's stacking context
  }
  function closeLB() { lb.hidden = true; }
  lb.addEventListener('click', function (e) { if (e.target === lb) closeLB(); });
  lb.querySelector('.axm-lb-x').addEventListener('click', closeLB);
  lb.querySelector('.axm-lb-dl').addEventListener('click', function () {
    var a = document.createElement('a'); a.href = lbImg.src;
    a.download = (lbImg.getAttribute('data-name') || 'figure').replace(/[^\w.-]+/g, '_').slice(0, 60) + '.png';
    document.body.appendChild(a); a.click(); a.remove();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !lb.hidden) closeLB(); });
  Array.prototype.forEach.call(grid.querySelectorAll('.module figure img'), function (img) {
    img.addEventListener('click', function (e) {
      e.stopPropagation();
      var fig = img.closest('figure'); var cap = fig && fig.querySelector('figcaption');
      openLB(img.src, ((cap && cap.textContent) || img.alt || 'figure').trim());
    });
  });

  // --- table export: copy (TSV, pastes as a table into Sheets/Word/PowerPoint) or CSV --
  function tableCells(tbl) {
    return Array.prototype.map.call(tbl.querySelectorAll('tr'), function (tr) {
      return Array.prototype.map.call(tr.querySelectorAll('th,td'), function (c) {
        return (c.textContent || '').trim();
      });
    });
  }
  function toTSV(rows) { return rows.map(function (r) { return r.join('\t'); }).join('\n'); }
  function toCSV(rows) {
    return rows.map(function (r) {
      return r.map(function (c) { return /[",\n]/.test(c) ? '"' + c.replace(/"/g, '""') + '"' : c; }).join(',');
    }).join('\r\n');
  }
  Array.prototype.forEach.call(grid.querySelectorAll('.module table'), function (tbl) {
    if (tbl.closest('.axm-tbl-wrap')) return;
    var w = document.createElement('div'); w.className = 'axm-tbl-wrap';
    tbl.parentNode.insertBefore(w, tbl); w.appendChild(tbl);
    var tools = document.createElement('div'); tools.className = 'axm-tbl-tools';
    tools.innerHTML = '<button type="button" class="axm-tcopy" title="Copy table (paste into Sheets, Word or PowerPoint)">⧉</button>' +
      '<button type="button" class="axm-tcsv" title="Download CSV">↓</button>';
    w.appendChild(tools);
    var capEl = tbl.querySelector('caption');
    var base = (((capEl && capEl.textContent) || 'table').trim().replace(/[^\w.-]+/g, '_').slice(0, 60)) || 'table';
    tools.querySelector('.axm-tcopy').addEventListener('click', function (e) {
      e.stopPropagation();
      var text = toTSV(tableCells(tbl));
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { toast('Table copied'); },
          function () { toast('Copy blocked here'); });
      } else { toast('Copy not available'); }
    });
    tools.querySelector('.axm-tcsv').addEventListener('click', function (e) {
      e.stopPropagation();
      var blob = new Blob([toCSV(tableCells(tbl))], { type: 'text/csv;charset=utf-8' });
      var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
      a.download = base + '.csv'; document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
      toast('CSV downloaded');
    });
    Array.prototype.forEach.call(tools.querySelectorAll('button'), function (b) {
      b.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
    });
  });
})();
""".strip()


__all__ = ["INTERACTIVE_CSS", "INTERACTIVE_JS"]
