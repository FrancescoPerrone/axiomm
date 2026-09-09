"""Client-side interactivity for HTML reports (stage two, S4).

A self-contained, dependency-free layer the ``html`` backend injects so a report
becomes a live workspace. On a wide screen it is a **free canvas**: every module
can be dragged anywhere by its handle and resized from its corner, so results,
plots and tables float where the user wants them and sit side by side for
comparison; the grabbed card comes to the front. On a narrow screen (phone) it
falls back to a readable vertical stack ordered by where cards sit on the canvas.
Page/section titles and paragraphs edit in place. Arrangement and edits persist
per-device in ``localStorage``; the default is exactly what was generated, and a
subtle reset returns to it. Nothing is labelled — it is found by touch. No
external assets, so the report stays one offline-capable file.
"""

from __future__ import annotations

INTERACTIVE_CSS = """
.module { position: relative; }
.module-handle { position: absolute; top: .55rem; right: .55rem; width: 1.5rem; height: 1.5rem;
  border-radius: 7px; cursor: grab; opacity: 0; transition: opacity .2s, background .2s;
  display: flex; align-items: center; justify-content: center; color: var(--muted);
  touch-action: none; user-select: none; z-index: 2; }
.module-handle::before { content: "\\2059\\2059"; letter-spacing: -2px; font-size: .9rem; line-height: 1; }
.module:hover .module-handle { opacity: .5; }
.module-handle:hover { opacity: 1; background: var(--accent-soft); }
@media (hover: none) { .module-handle { opacity: .35; } }
.module.dragging { z-index: 9999; box-shadow: 0 16px 40px rgba(0,0,0,.22); }
.module.sizing { user-select: none; }
.report-grid.canvas { position: relative; }
.report-grid.canvas .module { position: absolute; margin: 0; }
.module-resize { position: absolute; right: 2px; bottom: 2px; width: 20px; height: 20px;
  cursor: nwse-resize; opacity: 0; transition: opacity .2s; touch-action: none; z-index: 2; }
.module-resize::after { content: ""; position: absolute; right: 5px; bottom: 5px; width: 8px; height: 8px;
  border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); }
.report-grid:not(.canvas) .module-resize { display: none; }
.report-grid.canvas .module:hover .module-resize { opacity: .5; }
.module-resize:hover { opacity: 1; }
.module-placeholder { border: 2px dashed var(--border); border-radius: 10px; }
[data-editable] { border-radius: 5px; transition: background .15s; outline: none; }
[data-editable]:hover { background: color-mix(in srgb, var(--accent) 9%, transparent); }
[data-editable]:focus { background: color-mix(in srgb, var(--accent) 6%, transparent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 40%, transparent); }
.report-reset { position: fixed; bottom: 1rem; right: 1rem; font-family: var(--mono);
  font-size: .68rem; letter-spacing: .04em; color: var(--muted); background: var(--surface);
  border: 1px solid var(--border); border-radius: 999px; padding: .35rem .8rem; cursor: pointer;
  opacity: 0; transition: opacity .25s; z-index: 10000; }
body:hover .report-reset { opacity: .55; }
.report-reset:hover { opacity: 1; }
@media (hover: none) { .report-reset { opacity: .4; } }
""".strip()


INTERACTIVE_JS = r"""
(function () {
  var grid = document.getElementById('report-grid');
  if (!grid) return;
  var WIDE = '(min-width: 62rem)';
  var key = 'axiomm-report:' + (grid.getAttribute('data-report-id') || document.title || 'report');
  function load() { try { return JSON.parse(localStorage.getItem(key)) || {}; } catch (e) { return {}; } }
  function save() { try { localStorage.setItem(key, JSON.stringify(state)); } catch (e) {} }
  var state = load();
  state.edits = state.edits || {};
  state.pos = state.pos || {};   // { moduleId: {x,y,w,h,z} } for the canvas

  // --- editable text (always on) ------------------------------------------
  document.querySelectorAll('[data-editable]').forEach(function (el) {
    var id = el.getAttribute('data-editable');
    if (state.edits[id] != null) el.textContent = state.edits[id];
    el.setAttribute('contenteditable', 'true');
    el.setAttribute('spellcheck', 'false');
    el.addEventListener('blur', function () { state.edits[id] = el.textContent; save(); });
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && el.tagName !== 'P') { e.preventDefault(); el.blur(); }
    });
    el.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
  });

  function mods() { return Array.prototype.slice.call(grid.querySelectorAll('.module')); }
  function idOf(m) { return m.getAttribute('data-module'); }
  function isWide() { return window.matchMedia(WIDE).matches; }

  // give every module a resize handle (shown only on the canvas)
  mods().forEach(function (m) {
    if (!m.querySelector('.module-resize')) {
      var h = document.createElement('div'); h.className = 'module-resize'; m.appendChild(h);
    }
  });

  var maxZ = 1;
  Object.keys(state.pos).forEach(function (id) { maxZ = Math.max(maxZ, state.pos[id].z || 1); });
  function front(m) { maxZ += 1; m.style.zIndex = maxZ; }
  function canvasHeight() {
    if (!grid.classList.contains('canvas')) return;
    var b = 0;
    mods().forEach(function (m) { b = Math.max(b, m.offsetTop + m.offsetHeight); });
    grid.style.height = (b + 28) + 'px';
  }
  function savePos(m) {
    state.pos[idOf(m)] = {
      x: parseFloat(m.style.left) || 0, y: parseFloat(m.style.top) || 0,
      w: m.style.width ? parseFloat(m.style.width) : null,
      h: m.style.height ? parseFloat(m.style.height) : null,
      z: parseInt(m.style.zIndex, 10) || 1
    };
    save();
  }

  // --- layout engine -------------------------------------------------------
  function applyCanvas() {
    grid.classList.add('canvas');
    var cw = grid.clientWidth;
    var defW = Math.min(360, cw - 16);
    var flowY = 8;
    mods().forEach(function (m) {
      var p = state.pos[idOf(m)];
      m.style.position = 'absolute';
      if (p) {
        m.style.left = p.x + 'px'; m.style.top = p.y + 'px';
        m.style.width = (p.w ? p.w + 'px' : defW + 'px');
        if (p.h) { m.style.height = p.h + 'px'; m.style.overflow = 'auto'; }
        else { m.style.height = ''; m.style.overflow = ''; }
        m.style.zIndex = p.z || 1;
      } else {
        m.style.left = Math.max(0, (cw - defW) / 2) + 'px';
        m.style.width = defW + 'px'; m.style.height = ''; m.style.overflow = '';
        m.style.top = flowY + 'px'; m.style.zIndex = 1;
        flowY += m.offsetHeight + 16;
      }
    });
    canvasHeight();
  }
  function applyStack() {
    grid.classList.remove('canvas');
    grid.style.height = '';
    mods().forEach(function (m) {
      ['position', 'left', 'top', 'width', 'height', 'overflow', 'zIndex'].forEach(
        function (k) { m.style[k] = ''; });
    });
    // order by where cards sit on the canvas (top-to-bottom, then left-to-right)
    var withPos = mods().filter(function (m) { return state.pos[idOf(m)]; });
    if (withPos.length) {
      withPos.sort(function (a, b) {
        var pa = state.pos[idOf(a)], pb = state.pos[idOf(b)];
        return (pa.y - pb.y) || (pa.x - pb.x);
      }).forEach(function (m) { grid.appendChild(m); });
    }
  }
  function layout() { if (isWide()) applyCanvas(); else applyStack(); }
  try { layout(); } catch (e) {}
  var rt; window.addEventListener('resize', function () {
    clearTimeout(rt); rt = setTimeout(function () { try { layout(); } catch (e) {} }, 150);
  });

  // --- pointer interactions (drag / resize) --------------------------------
  var act = null;
  grid.addEventListener('pointerdown', function (e) {
    var rh = e.target.closest('.module-resize');
    var hh = e.target.closest('.module-handle');
    if (rh && isWide()) {
      var m = rh.closest('.module'); if (!m) return;
      e.preventDefault(); front(m); m.classList.add('sizing');
      act = { type: 'resize', m: m, sx: e.clientX, sy: e.clientY, sw: m.offsetWidth, sh: m.offsetHeight };
    } else if (hh) {
      var mod = hh.closest('.module'); if (!mod) return;
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
    } else { return; }
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
      m.style.width = Math.max(220, act.sw + (e.clientX - act.sx)) + 'px';
      m.style.height = Math.max(140, act.sh + (e.clientY - act.sy)) + 'px';
      m.style.overflow = 'auto';
      canvasHeight();
    } else if (act.type === 'sdrag') {
      m.style.top = (e.clientY - act.offY) + 'px';
      var others = mods().filter(function (x) { return x !== m; });
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
      savePos(m);
    } else if (act.type === 'sdrag') {
      grid.insertBefore(m, act.ph); act.ph.remove();
      m.classList.remove('dragging');
      ['width', 'position', 'left', 'top', 'pointerEvents'].forEach(function (k) { m.style[k] = ''; });
      // remember the new reading order as canvas positions (top-to-bottom)
      var y = 0;
      mods().forEach(function (x) { var p = state.pos[idOf(x)] || {}; p.x = 0; p.y = y; y += 1;
        p.z = p.z || 1; p.w = p.w || null; p.h = p.h || null; state.pos[idOf(x)] = p; });
      save();
    }
    act = null;
  }

  // --- reset ---------------------------------------------------------------
  var reset = document.createElement('button');
  reset.className = 'report-reset';
  reset.textContent = 'reset layout';
  reset.addEventListener('click', function () {
    try { localStorage.removeItem(key); } catch (e) {}
    location.reload();
  });
  document.body.appendChild(reset);
})();
""".strip()


__all__ = ["INTERACTIVE_CSS", "INTERACTIVE_JS"]
