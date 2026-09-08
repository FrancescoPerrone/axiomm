"""Client-side interactivity for HTML reports (stage two, S4).

A self-contained, dependency-free layer the ``html`` backend injects so a report
becomes a live workspace: modules drag to rearrange (pointer events — touch and
mouse), and the page title, section titles and paragraphs edit in place. On a wide
screen a module can be dropped on the right-edge zone to spin off a **new column**,
so results, plots and tables sit **side by side** for comparison; columns collapse
to a single stack on narrow screens. A viewer's arrangement and edits persist
per-device in ``localStorage``; the default is exactly what was generated. Nothing
is labelled — it is found by touch. No external assets, so the report stays one
offline-capable file.
"""

from __future__ import annotations

INTERACTIVE_CSS = """
.module { position: relative; }
.module-handle { position: absolute; top: .55rem; right: .55rem; width: 1.5rem; height: 1.5rem;
  border-radius: 7px; cursor: grab; opacity: 0; transition: opacity .2s, background .2s;
  display: flex; align-items: center; justify-content: center; color: var(--muted);
  touch-action: none; user-select: none; }
.module-handle::before { content: "\\2059\\2059"; letter-spacing: -2px; font-size: .9rem; line-height: 1; }
.module:hover .module-handle { opacity: .5; }
.module-handle:hover { opacity: 1; background: var(--accent-soft); }
@media (hover: none) { .module-handle { opacity: .35; } }
.module.dragging { z-index: 30; box-shadow: 0 14px 34px rgba(0,0,0,.20); opacity: .98; }
.module-placeholder { border: 2px dashed var(--border); border-radius: 10px; }
.newcol-zone { align-self: stretch; width: .6rem; min-height: 8rem; border-radius: 8px;
  border: 2px dashed color-mix(in srgb, var(--accent) 35%, transparent); opacity: 0;
  transition: opacity .15s, background .15s; }
.newcol-zone.show { opacity: .5; }
.newcol-zone.active { opacity: 1; background: var(--accent-soft); }
[data-editable] { border-radius: 5px; transition: background .15s; outline: none; }
[data-editable]:hover { background: color-mix(in srgb, var(--accent) 9%, transparent); }
[data-editable]:focus { background: color-mix(in srgb, var(--accent) 6%, transparent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 40%, transparent); }
.report-reset { position: fixed; bottom: 1rem; right: 1rem; font-family: var(--mono);
  font-size: .68rem; letter-spacing: .04em; color: var(--muted); background: var(--surface);
  border: 1px solid var(--border); border-radius: 999px; padding: .35rem .8rem; cursor: pointer;
  opacity: 0; transition: opacity .25s; }
body:hover .report-reset { opacity: .55; }
.report-reset:hover { opacity: 1; }
@media (hover: none) { .report-reset { opacity: .4; } }
""".strip()


INTERACTIVE_JS = r"""
(function () {
  var grid = document.getElementById('report-grid');
  if (!grid) return;
  var key = 'axiomm-report:' + (grid.getAttribute('data-report-id') || document.title || 'report');
  function load() { try { return JSON.parse(localStorage.getItem(key)) || {}; } catch (e) { return {}; } }
  function save() { try { localStorage.setItem(key, JSON.stringify(state)); } catch (e) {} }
  var state = load();
  state.edits = state.edits || {};
  if (!state.columns && state.order) state.columns = [state.order];   // migrate old single-column

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
  });

  // --- columns -------------------------------------------------------------
  function cols() { return Array.prototype.slice.call(grid.querySelectorAll('.report-col')); }
  function ensureCol() {
    var c = grid.querySelector('.report-col');
    if (!c) { c = document.createElement('div'); c.className = 'report-col'; grid.appendChild(c); }
    return c;
  }
  function moduleMap() {
    var m = {};
    grid.querySelectorAll('.module').forEach(function (x) { m[x.getAttribute('data-module')] = x; });
    return m;
  }
  function applyColumns() {
    if (!state.columns) return;
    var byId = moduleMap(), used = {};
    cols().forEach(function (c) { c.remove(); });
    state.columns.forEach(function (ids) {
      var real = ids.filter(function (id) { return byId[id]; });
      if (!real.length) return;
      var col = document.createElement('div'); col.className = 'report-col'; grid.appendChild(col);
      real.forEach(function (id) { col.appendChild(byId[id]); used[id] = 1; });
    });
    var leftover = Object.keys(byId).filter(function (id) { return !used[id]; });
    if (leftover.length) {
      var col = grid.querySelector('.report-col') || ensureCol();
      leftover.forEach(function (id) { col.appendChild(byId[id]); });
    }
    if (!cols().length) ensureCol();
  }
  function currentColumns() {
    return cols().map(function (c) {
      return Array.prototype.map.call(c.querySelectorAll('.module'),
        function (m) { return m.getAttribute('data-module'); });
    }).filter(function (a) { return a.length; });
  }
  function cleanup() {
    cols().forEach(function (c) { if (!c.querySelector('.module')) c.remove(); });
    if (!cols().length) ensureCol();
  }
  try { applyColumns(); } catch (e) {}

  // --- pointer-drag reorder + column moves --------------------------------
  var drag = null, ph = null, offY = 0, zone = null, overZone = false;
  function colUnder(x, y) {
    var cs = cols(), best = null, bd = Infinity;
    for (var i = 0; i < cs.length; i++) {
      var r = cs[i].getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return cs[i];
      var dx = x - (r.left + r.right) / 2, dy = y - (r.top + r.bottom) / 2, d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = cs[i]; }
    }
    return best;
  }
  grid.addEventListener('pointerdown', function (e) {
    var handle = e.target.closest('.module-handle');
    if (!handle) return;
    var mod = handle.closest('.module');
    if (!mod) return;
    e.preventDefault();
    drag = mod;
    var r = mod.getBoundingClientRect();
    offY = e.clientY - r.top;
    ph = document.createElement('div');
    ph.className = 'module-placeholder';
    ph.style.height = r.height + 'px';
    mod.parentNode.insertBefore(ph, mod.nextSibling);
    mod.classList.add('dragging');
    mod.style.width = r.width + 'px';
    mod.style.position = 'fixed';
    mod.style.left = r.left + 'px';
    mod.style.top = (e.clientY - offY) + 'px';
    mod.style.pointerEvents = 'none';
    zone = document.createElement('div');
    zone.className = 'newcol-zone show';
    grid.appendChild(zone);
    if (handle.setPointerCapture) handle.setPointerCapture(e.pointerId);
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  });
  function onMove(e) {
    if (!drag) return;
    drag.style.top = (e.clientY - offY) + 'px';
    overZone = false;
    if (zone) {
      var zr = zone.getBoundingClientRect();
      overZone = e.clientX >= zr.left - 8 && e.clientX <= zr.right + 8
                 && e.clientY >= zr.top && e.clientY <= zr.bottom;
      zone.classList.toggle('active', overZone);
    }
    if (overZone) { if (ph.parentNode) ph.parentNode.removeChild(ph); return; }
    var col = colUnder(e.clientX, e.clientY);
    if (!col) return;
    var mods = Array.prototype.filter.call(col.querySelectorAll('.module'),
      function (m) { return m !== drag; });
    var placed = false;
    for (var i = 0; i < mods.length; i++) {
      var r = mods[i].getBoundingClientRect();
      if (e.clientY < r.top + r.height / 2) { col.insertBefore(ph, mods[i]); placed = true; break; }
    }
    if (!placed) col.appendChild(ph);
  }
  function onUp() {
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onUp);
    if (!drag) return;
    if (overZone) {
      var col = document.createElement('div'); col.className = 'report-col';
      grid.insertBefore(col, zone); col.appendChild(drag);
    } else if (ph && ph.parentNode) {
      ph.parentNode.insertBefore(drag, ph);
    } else {
      ensureCol().appendChild(drag);
    }
    if (ph && ph.parentNode) ph.parentNode.removeChild(ph);
    if (zone && zone.parentNode) zone.parentNode.removeChild(zone);
    drag.classList.remove('dragging');
    drag.style.position = drag.style.top = drag.style.left = drag.style.width = drag.style.pointerEvents = '';
    drag = null; zone = null; overZone = false;
    cleanup();
    state.columns = currentColumns();
    delete state.order;
    save();
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
