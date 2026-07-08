/**
 * StrategyPicker — 回测/回放策略分组选择（经典 / 技术 / AI）
 */
(function (global) {
  'use strict';

  var DEFAULT_GROUPS = {
    classic: {
      label: '经典',
      strategies: [
        { value: 'sma_cross', label: 'SMA交叉' },
        { value: 'momentum', label: '动量' },
        { value: 'bollinger', label: '布林带' },
        { value: 'rsi', label: 'RSI' },
      ],
    },
    tech: {
      label: '技术',
      strategies: [
        { value: 'macd', label: 'MACD' },
        { value: 'trend_follow', label: '趋势跟随' },
        { value: 'deep_dip', label: '深超跌' },
      ],
    },
    ai: {
      label: 'AI',
      strategies: [
        { value: 'ai', label: 'AI接口' },
        { value: 'llm', label: 'LLM' },
      ],
    },
  };

  var state = {
    groups: DEFAULT_GROUPS,
    group: 'classic',
    value: 'sma_cross',
    containerId: '',
    groupId: '',
    onStrategyChange: null,
  };

  function strategiesForGroup(gid) {
    return (state.groups[gid] || state.groups.classic).strategies;
  }

  function refreshStrategyChips() {
    var list = strategiesForGroup(state.group);
    if (!list.some(function (s) { return s.value === state.value; })) {
      state.value = list[0].value;
    }
    ChipSelect.mount(state.containerId, list, {
      value: state.value,
      wrap: true,
      compact: true,
      onChange: function (v) {
        state.value = v;
        if (typeof state.onStrategyChange === 'function') state.onStrategyChange(v);
      },
    });
  }

  function cloneGroups(src) {
    var out = {};
    Object.keys(src).forEach(function (k) {
      out[k] = {
        label: src[k].label,
        strategies: src[k].strategies.map(function (s) { return { value: s.value, label: s.label }; }),
      };
    });
    return out;
  }

  /**
   * @param {string} strategyContainerId
   * @param {string} groupContainerId
   * @param {object} config - { defaultGroup, defaultStrategy, groups? }
   */
  function mount(strategyContainerId, groupContainerId, config) {
    config = config || {};
    state.groups = config.groups ? cloneGroups(config.groups) : cloneGroups(DEFAULT_GROUPS);
    state.containerId = strategyContainerId;
    state.groupId = groupContainerId;
    state.group = config.defaultGroup || 'classic';
    state.value = config.defaultStrategy || 'sma_cross';
    state.onStrategyChange = config.onStrategyChange || null;

    var groupOpts = Object.keys(state.groups).map(function (k) {
      return { value: k, label: state.groups[k].label };
    });

    ChipSelect.mount(groupContainerId, groupOpts, {
      value: state.group,
      compact: true,
      onChange: function (g) {
        state.group = g;
        refreshStrategyChips();
      },
    });
    refreshStrategyChips();
  }

  function getValue() {
    return state.value;
  }

  function setValue(v) {
    state.value = v;
    Object.keys(state.groups).forEach(function (g) {
      if (state.groups[g].strategies.some(function (s) { return s.value === v; })) {
        state.group = g;
        ChipSelect.setValue(state.groupId, g, true);
      }
    });
    refreshStrategyChips();
  }

  global.StrategyPicker = {
    DEFAULT_GROUPS: DEFAULT_GROUPS,
    mount: mount,
    getValue: getValue,
    setValue: setValue,
  };
})(typeof window !== 'undefined' ? window : this);
