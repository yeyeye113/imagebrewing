/**
 * ChipSelect — 量化看板统一选择面（替代原生 <select>）
 * 用法: ChipSelect.mount('container-id', [{value, label}], { value, onChange, wrap })
 */
(function (global) {
  'use strict';

  var STYLE_ID = 'ui-chips-styles';
  if (!document.getElementById(STYLE_ID)) {
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      '.chip-select{display:flex;gap:4px;align-items:center}',
      '.chip-select-wrap{flex-wrap:wrap;max-width:420px}',
      '.chip-select-inline{flex-wrap:nowrap}',
      '.chip-opt{',
      '  font-family:inherit;font-size:12px;padding:4px 10px;',
      '  border:1px solid var(--border,#1a2744);border-radius:6px;',
      '  background:var(--bg2,var(--bg,#0d1220));color:var(--text,#e2e6f2);',
      '  cursor:pointer;transition:all .15s;white-space:nowrap;line-height:1.4',
      '}',
      '.chip-opt:hover{border-color:var(--blue,#6366f1)}',
      '.chip-opt:focus-visible{outline:2px solid var(--blue,#6366f1);outline-offset:1px}',
      '.chip-opt.active{',
      '  background:var(--blue,#6366f1);color:#fff;border-color:var(--blue,#6366f1)',
      '}',
      '.chip-select.compact .chip-opt{font-size:11px;padding:3px 8px;border-radius:12px}',
      '.chip-select.modal-chips{justify-content:center;margin:12px 0}',
      '.chip-select.modal-chips .chip-opt{font-size:13px;padding:6px 14px;border-radius:8px}',
      '.chip-opt.tone-long.active{background:var(--green,#22c55e);border-color:var(--green,#22c55e)}',
      '.chip-opt.tone-short.active{background:var(--red,#ef4444);border-color:var(--red,#ef4444)}',
      '.chip-opt.tone-neutral.active{background:var(--yellow,#f59e0b);border-color:var(--yellow,#f59e0b);color:#1a1a1a}',
      '.fp-summary{font-size:11px;color:var(--text-muted,#8892b0);margin-top:6px}',
      '.fp-summary.warn{color:var(--yellow,#f59e0b)}',
      '.fp-summary.limit{color:var(--red,#ef4444)}',
      '.chip-opt.disabled{opacity:.35;cursor:not-allowed}',
      '.chip-opt.disabled:hover{border-color:var(--border,#1a2744)}',
      '.fp-actions{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}',
      '.fp-action-btn{font:inherit;font-size:11px;padding:3px 10px;border-radius:12px;border:1px solid var(--border,#1a2744);background:transparent;color:var(--text-muted,#8892b0);cursor:pointer}',
      '.fp-action-btn:hover{border-color:var(--blue,#6366f1);color:var(--blue,#6366f1)}',
      '.stat-card.clickable{cursor:pointer;transition:var(--transition,all .2s)}',
      '.stat-card.clickable:hover{border-color:var(--blue,#3b82f6);transform:translateY(-1px)}',
      '.stat-card.clickable.active-filter{outline:2px solid var(--blue,#3b82f6);outline-offset:2px}',
      '.stat-card.clickable.disabled-stat{opacity:.4;cursor:not-allowed;pointer-events:none}',
      '.fp-contract-grid{max-height:120px;overflow-y:auto;padding:4px 0}',
      '.fp-picker-block{margin-bottom:10px}',
      '.fp-picker-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--text-muted,#64748b);margin-bottom:6px}',
    ].join('');
    document.head.appendChild(style);
  }

  function resolveEl(container) {
    if (!container) return null;
    return typeof container === 'string' ? document.getElementById(container) : container;
  }

  function mount(container, options, config) {
    var el = resolveEl(container);
    if (!el || !options || !options.length) return null;

    config = config || {};
    var initial = config.value != null ? String(config.value) : String(options[0].value);
    var wrap = !!config.wrap;
    var compact = !!config.compact;
    var extraClass = config.className || '';

    el.className = ['chip-select', wrap ? 'chip-select-wrap' : 'chip-select-inline', compact ? 'compact' : '', extraClass]
      .filter(Boolean)
      .join(' ');
    el.innerHTML = '';
    el.setAttribute('role', 'listbox');
    el.dataset.chipValue = initial;

    options.forEach(function (opt) {
      var btn = document.createElement('button');
      btn.type = 'button';
      var tone = opt.tone ? ' tone-' + opt.tone : '';
      btn.className = 'chip-opt' + tone + (String(opt.value) === initial ? ' active' : '');
      btn.dataset.value = String(opt.value);
      btn.textContent = opt.label;
      btn.setAttribute('role', 'option');
      btn.setAttribute('aria-selected', String(opt.value) === initial ? 'true' : 'false');
      btn.addEventListener('click', function () {
        setValue(el, opt.value, false);
        if (typeof config.onChange === 'function') config.onChange(opt.value);
      });
      el.appendChild(btn);
    });

    return el;
  }

  function getValue(container) {
    var el = resolveEl(container);
    if (!el) return '';
    var active = el.querySelector('.chip-opt.active');
    return active ? active.dataset.value : (el.dataset.chipValue || '');
  }

  function setValue(container, value, silent) {
    var el = resolveEl(container);
    if (!el) return;
    var str = String(value);
    el.dataset.chipValue = str;
    el.querySelectorAll('.chip-opt').forEach(function (btn) {
      var on = btn.dataset.value === str;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    if (!silent && typeof el._chipOnChange === 'function') el._chipOnChange(str);
  }

  /** 绑定 setValue 时可选的外部 onChange（供 reset 等场景） */
  function bindOnChange(container, fn) {
    var el = resolveEl(container);
    if (el) el._chipOnChange = fn;
  }

  global.ChipSelect = { mount: mount, getValue: getValue, setValue: setValue, bindOnChange: bindOnChange };
})(typeof window !== 'undefined' ? window : this);
