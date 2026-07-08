/**
 * FuturesPicker — 期货品种选择（多选 / 单选，对接 /api/futures/contracts）
 */
(function (global) {
  'use strict';

  var MAX_MULTI = 16; /* 与 run_forecast futures[:16] 对齐 */

  var PRESETS = {
    hot: { label: '热门', codes: ['I', 'RB', 'SC', 'AU', 'AG'] },
    metal: { label: '金属', sectors: ['有色金属', '黑色金属'] },
    energy: { label: '能源化工', sectors: ['能源化工'] },
    agri: { label: '农产品', sectors: ['油脂油料', '农产品'] },
    finance: { label: '金融', sectors: ['金融期货'] },
    all: { label: '全市场', all: true },
    custom: { label: '自定义', custom: true },
  };

  var state = {
    contracts: [],
    bySector: {},
    selected: new Set(),
    sectorFilter: '',
    onChange: null,
    mode: 'multi', /* multi | single */
    singleContainerId: '',
    singleDefault: 'M',
    singleOnChange: null,
  };

  function presetCodes(key) {
    var p = PRESETS[key];
    if (!p || p.custom) return [];
    if (p.all) return state.contracts.map(function (c) { return c.code; });
    if (p.codes) return p.codes.slice();
    if (p.sectors) return codesFromSectors(p.sectors);
    return [];
  }

  function codesFromSectors(sectors) {
    var out = [];
    sectors.forEach(function (s) {
      (state.bySector[s] || []).forEach(function (c) {
        if (out.indexOf(c.code) < 0) out.push(c.code);
      });
    });
    return out;
  }

  function visibleContracts() {
    var list = state.contracts;
    if (state.sectorFilter) {
      list = list.filter(function (c) { return c.sector === state.sectorFilter; });
    }
    return list;
  }

  function notify() {
    if (state.mode === 'multi' && typeof state.onChange === 'function') {
      state.onChange(getCodes());
    }
  }

  function getCodes() {
    return Array.from(state.selected);
  }

  function getCodesString() {
    return getCodes().join(',');
  }

  function detectPresetKey() {
    var cur = getCodes().slice().sort().join(',');
    var keys = ['hot', 'metal', 'energy', 'agri', 'finance', 'all'];
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var pc = presetCodes(k).slice().sort().join(',');
      if (pc && pc === cur) return k;
    }
    return getCodes().length ? 'custom' : 'custom';
  }

  function syncPresetChip() {
    var el = document.getElementById('fp-preset-chips');
    if (!el) return;
    ChipSelect.setValue('fp-preset-chips', detectPresetKey(), true);
  }

  function setCodes(codes, silent) {
    var list = (codes || []).map(function (c) { return String(c).toUpperCase(); });
    if (state.mode === 'multi' && list.length > MAX_MULTI) {
      list = list.slice(0, MAX_MULTI);
    }
    state.selected = new Set(list);
    if (state.mode === 'multi') {
      renderContractChips();
      renderSelectionSummary();
      syncPresetChip();
    }
    if (!silent) notify();
  }

  function toggleCode(code) {
    code = String(code).toUpperCase();
    if (state.mode === 'single') {
      state.selected = new Set([code]);
      refreshSingleChips();
      if (typeof state.singleOnChange === 'function') state.singleOnChange(code);
      return;
    }
    if (state.selected.has(code)) state.selected.delete(code);
    else {
      if (state.selected.size >= MAX_MULTI) return;
      state.selected.add(code);
    }
    renderContractChips();
    renderSelectionSummary();
    syncPresetChip();
    notify();
  }

  function selectAllVisible() {
    visibleContracts().forEach(function (c) {
      if (state.selected.size >= MAX_MULTI) return;
      state.selected.add(c.code);
    });
    renderContractChips();
    renderSelectionSummary();
    syncPresetChip();
    notify();
  }

  function clearAll() {
    state.selected.clear();
    renderContractChips();
    renderSelectionSummary();
    syncPresetChip();
    notify();
  }

  function invertVisible() {
    visibleContracts().forEach(function (c) {
      if (state.selected.has(c.code)) state.selected.delete(c.code);
      else if (state.selected.size < MAX_MULTI) state.selected.add(c.code);
    });
    renderContractChips();
    renderSelectionSummary();
    syncPresetChip();
    notify();
  }

  function applyPreset(key) {
    if (key === 'custom') return;
    state.sectorFilter = '';
    var sectorEl = document.getElementById('fp-sector-chips');
    if (sectorEl) ChipSelect.setValue('fp-sector-chips', 'all', true);
    setCodes(presetCodes(key));
    ChipSelect.setValue('fp-preset-chips', key, true);
  }

  function filterBySector(sector) {
    state.sectorFilter = sector || '';
    if (state.mode === 'multi') renderContractChips();
    else refreshSingleChips();
  }

  function renderSelectionSummary() {
    var el = document.getElementById('fp-summary');
    if (!el) return;
    var n = state.selected.size;
    if (!n) {
      el.textContent = '请至少选择 1 个品种';
      el.className = 'fp-summary warn';
      return;
    }
    var extra = n >= MAX_MULTI ? '（已达上限 ' + MAX_MULTI + '）' : '';
    el.textContent = '已选 ' + n + ' 个' + extra;
    el.className = 'fp-summary' + (n >= MAX_MULTI ? ' limit' : '');
  }

  function renderContractChips() {
    var box = document.getElementById('fp-contract-chips');
    if (!box) return;
    var list = visibleContracts();
    box.innerHTML = '';
    box.className = 'chip-select chip-select-wrap compact fp-contract-grid';
    list.forEach(function (c) {
      var btn = document.createElement('button');
      btn.type = 'button';
      var atLimit = !state.selected.has(c.code) && state.selected.size >= MAX_MULTI;
      btn.className = 'chip-opt' + (state.selected.has(c.code) ? ' active' : '') + (atLimit ? ' disabled' : '');
      btn.disabled = atLimit;
      btn.dataset.value = c.code;
      btn.title = (c.sector || '') + (atLimit ? ' · 已达上限' : '');
      btn.textContent = c.code + ' ' + c.name;
      btn.addEventListener('click', function () { if (!atLimit || state.selected.has(c.code)) toggleCode(c.code); });
      box.appendChild(btn);
    });
  }

  function mountPresetBar() {
    var opts = ['hot', 'metal', 'energy', 'agri', 'finance', 'all', 'custom'].map(function (k) {
      return { value: k, label: PRESETS[k].label };
    });
    ChipSelect.mount('fp-preset-chips', opts, {
      value: 'hot',
      compact: true,
      onChange: function (v) { if (v !== 'custom') applyPreset(v); },
    });
  }

  function mountSectorBar(sectorContainerId) {
    var id = sectorContainerId || 'fp-sector-chips';
    var sectors = [{ value: 'all', label: '全部板块' }];
    Object.keys(state.bySector).sort().forEach(function (s) {
      sectors.push({ value: s, label: s });
    });
    var allLabel = sectorContainerId === 'fp-single-sector' ? '全部' : '全部板块';
    sectors[0].label = allLabel;
    ChipSelect.mount(id, sectors, {
      value: 'all',
      compact: true,
      wrap: true,
      onChange: function (v) { filterBySector(v === 'all' ? '' : v); },
    });
  }

  function indexContracts(data) {
    state.contracts = data.contracts || [];
    state.bySector = {};
    state.contracts.forEach(function (c) {
      var s = c.sector || '其他';
      if (!state.bySector[s]) state.bySector[s] = [];
      state.bySector[s].push(c);
    });
  }

  function fetchContracts(apiBase) {
    var url = (apiBase || '') + '/api/futures/contracts';
    return fetch(url).then(function (r) { return r.json(); }).then(function (data) {
      indexContracts(data);
      return state.contracts;
    }).catch(function () {
      indexContracts({
        contracts: PRESETS.hot.codes.map(function (code) {
          return { code: code, name: code, sector: '' };
        }),
      });
      return state.contracts;
    });
  }

  /** 首页多选 */
  function init(apiBase, config) {
    config = config || {};
    state.mode = 'multi';
    state.onChange = config.onChange || null;
    return fetchContracts(apiBase).then(function () {
      mountPresetBar();
      mountSectorBar('fp-sector-chips');
      setCodes(config.defaultCodes || PRESETS.hot.codes, true);
      renderContractChips();
      renderSelectionSummary();
      return state.contracts;
    });
  }

  function refreshSingleChips() {
    var cid = state.singleContainerId;
    if (!cid) return;
    var list = visibleContracts();
    var cur = getCodes()[0] || '';
    var opts = list.map(function (c) {
      return { value: c.code, label: c.code + ' ' + c.name };
    });
    if (!opts.length) opts = [{ value: state.singleDefault, label: state.singleDefault }];
    var val = opts.some(function (o) { return o.value === cur; }) ? cur
      : opts.some(function (o) { return o.value === state.singleDefault; }) ? state.singleDefault
      : opts[0].value;
    state.selected = new Set([val]);
    ChipSelect.mount(cid, opts, {
      value: val,
      wrap: true,
      compact: true,
      onChange: function (v) {
        state.selected = new Set([v]);
        if (typeof state.singleOnChange === 'function') state.singleOnChange(v);
      },
    });
  }

  /** 预测页单选 — 不污染多选 DOM / 状态 */
  function mountSingle(containerId, config) {
    config = config || {};
    state.mode = 'single';
    state.singleContainerId = containerId;
    state.singleDefault = (config.defaultCode || 'M').toUpperCase();
    state.singleOnChange = config.onSymbolChange || null;
    var sectorId = config.sectorContainerId || 'fp-single-sector';

    return fetchContracts(config.apiBase || '').then(function () {
      mountSectorBar(sectorId);
      state.selected = new Set([state.singleDefault]);
      refreshSingleChips();
    });
  }

  /** 期货主力合约码（API 常用 RB0 / M0） */
  function toMainContract(code) {
    var c = String(code || '').toUpperCase();
    if (!c) return c;
    return /0$/.test(c) ? c : c + '0';
  }

  global.FuturesPicker = {
    PRESETS: PRESETS,
    MAX_MULTI: MAX_MULTI,
    init: init,
    mountSingle: mountSingle,
    fetchContracts: fetchContracts,
    getCodes: getCodes,
    getCodesString: getCodesString,
    setCodes: setCodes,
    applyPreset: applyPreset,
    selectAllVisible: selectAllVisible,
    clearAll: clearAll,
    invertVisible: invertVisible,
    toMainContract: toMainContract,
  };
})(typeof window !== 'undefined' ? window : this);
