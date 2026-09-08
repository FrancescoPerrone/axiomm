"""Client-side interactivity for HTML reports (stage two, S4).

A self-contained, dependency-free layer the ``html`` backend injects so a report
becomes a live workspace: modules drag to reorder (pointer events — works on
touch and mouse), and the page title, section titles and paragraphs are edited in
place. A viewer's arrangement and edits persist per-device in ``localStorage``;
the default is exactly what was generated. Nothing is labelled — it is found by
touch (a handle fades in on hover; text highlights when hovered). No external
assets, so the report stays one offline-capable file.
"""

from __future__ import annotations

INTERACTIVE_CSS = """
.report-grid { display: flex; flex-direction: column; gap: 1.25rem; }
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
  state.order = state.order || [];
  state.edits = state.edits || {};

  // --- editable text -------------------------------------------------------
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

  // --- restore saved order -------------------------------------------------
  state.order.forEach(function (id) {
    var m = grid.querySelector('.module[data-module="' + id + '"]');
    if (m) grid.appendChild(m);
  });
  function currentOrder() {
    return Array.prototype.map.call(grid.querySelectorAll('.module'),
      function (m) { return m.getAttribute('data-module'); });
  }

  // --- pointer-drag reorder (touch + mouse) --------------------------------
  var drag = null, ph = null, offY = 0;
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
    if (handle.setPointerCapture) handle.setPointerCapture(e.pointerId);
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  });
  function onMove(e) {
    if (!drag) return;
    drag.style.top = (e.clientY - offY) + 'px';
    var mods = Array.prototype.filter.call(grid.querySelectorAll('.module'),
      function (m) { return m !== drag; });
    var placed = false;
    for (var i = 0; i < mods.length; i++) {
      var r = mods[i].getBoundingClientRect();
      if (e.clientY < r.top + r.height / 2) { grid.insertBefore(ph, mods[i]); placed = true; break; }
    }
    if (!placed) grid.appendChild(ph);
  }
  function onUp() {
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onUp);
    if (!drag) return;
    grid.insertBefore(drag, ph);
    ph.remove();
    drag.classList.remove('dragging');
    drag.style.position = drag.style.top = drag.style.left = drag.style.width = drag.style.pointerEvents = '';
    drag = null;
    state.order = currentOrder();
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
