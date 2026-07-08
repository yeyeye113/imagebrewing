/**
 * StrategyOptimize — 参数优化元数据、策略分析面板、Walk-Forward 解读
 */
(function (global) {
  'use strict';

  var catalog = null;

  function fetchCatalog(apiBase) {
    var url = (apiBase || '') + '/optimize/meta';
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (data) {
      catalog = data;
      return data;
    });
  }

  function getCatalog() {
    return catalog;
  }

  function isOptimizable(name) {
    return !!(catalog && catalog.strategies && catalog.strategies[name]);
  }

  /** 从 catalog 构建 StrategyPicker 分组（仅含可优化策略） */
  function buildPickerGroups() {
    if (!catalog) return null;
    var groupLabels = catalog.group_labels || {};
    var buckets = {};
    Object.keys(catalog.strategies).forEach(function (name) {
      var s = catalog.strategies[name];
      var gid = s.group || 'other';
      if (!buckets[gid]) {
        buckets[gid] = { label: groupLabels[gid] || gid, strategies: [] };
      }
      buckets[gid].strategies.push({
        value: name,
        label: s.label + ' · ' + s.combo_count + '组',
      });
    });
    return buckets;
  }

  function formatGrid(grid) {
    if (!grid) return '';
    return Object.keys(grid).map(function (k) {
      return k + ': [' + grid[k].join(', ') + ']';
    }).join(' · ');
  }

  function overfitLevel(gap) {
    if (gap == null || isNaN(gap)) return { cls: 'neutral', label: '未知' };
    if (gap < 0.15) return { cls: 'safe', label: '低' };
    if (gap < 0.4) return { cls: 'warn', label: '中' };
    return { cls: 'danger', label: '高' };
  }

  function metricLabel(m) {
    return { sharpe: '夏普', total_return: '总收益', sortino: '索提诺', cagr: '年化' }[m] || m;
  }

  /**
   * 渲染策略优化分析侧栏
   * @param {string} containerId
   * @param {string} strategyName
   */
  function renderAnalysis(containerId, strategyName) {
    var el = document.getElementById(containerId);
    if (!el || !catalog) return;
    var s = catalog.strategies[strategyName];
    if (!s) {
      el.innerHTML = '<div class="opt-analysis empty">当前策略不支持参数网格优化（AI/LLM 等需外部调参）</div>';
      el.style.display = '';
      return;
    }
    var tips = (s.tips || []).map(function (t) {
      return '<li>' + t + '</li>';
    }).join('');
    el.innerHTML =
      '<div class="opt-analysis">' +
        '<div class="opt-analysis-title">' + s.label + ' · 参数空间</div>' +
        '<div class="opt-grid-desc">' + formatGrid(s.grid) + '</div>' +
        '<div class="opt-combo">共 <strong>' + s.combo_count + '</strong> 组组合 · 指标可选 ' +
          (s.metrics || []).map(metricLabel).join(' / ') +
        '</div>' +
        (tips ? '<ul class="opt-tips">' + tips + '</ul>' : '') +
      '</div>';
    el.style.display = '';
  }

  function renderOptimizeResults(containerId, data, metric) {
    var el = document.getElementById(containerId);
    if (!el || !data) return;

    global.StrategyOptimize._lastResult = data;

    var wf = data.walk_forward || {};
    var gap = wf.overfit_gap;
    var risk = overfitLevel(gap);
    var gapPct = gap != null ? (Math.abs(gap) * (Math.abs(gap) <= 2 ? 100 : 1)).toFixed(2) : '--';

    var topRows = (data.top || []).map(function (row, i) {
      var params = Object.keys(row.params || {}).map(function (k) {
        return k + '=' + row.params[k];
      }).join(', ');
      var nt = row.n_trades;
      var lowTrade = (nt != null && nt < 2);
      return '<tr' + (lowTrade ? ' class="opt-low-trade"' : '') + '>' +
        '<td>' + (i + 1) + '</td>' +
        '<td><code>' + params + '</code></td>' +
        '<td>' + (row.sharpe != null ? row.sharpe.toFixed(2) : '-') + '</td>' +
        '<td>' + (row.total_return != null ? (row.total_return * 100).toFixed(1) + '%' : '-') + '</td>' +
        '<td>' + (row.max_drawdown != null ? (row.max_drawdown * 100).toFixed(1) + '%' : '-') + '</td>' +
        '<td>' + (nt != null ? nt + (lowTrade ? ' \u26a0' : '') : '-') + '</td>' +
        '<td>' + (row.win_rate != null ? (row.win_rate * 100).toFixed(0) + '%' : '-') + '</td>' +
      '</tr>';
    }).join('');

    var foldRows = (wf.folds || []).map(function (f, i) {
      var p = Object.keys(f.best_params || {}).map(function (k) {
        return k + '=' + f.best_params[k];
      }).join(', ');
      return '<tr>' +
        '<td>#' + (i + 1) + '</td>' +
        '<td><code>' + p + '</code></td>' +
        '<td>' + ((f.oos_return || 0) * 100).toFixed(1) + '%</td>' +
        '<td>' + (f.oos_sharpe != null ? f.oos_sharpe.toFixed(2) : '-') + '</td>' +
      '</tr>';
    }).join('');

    var bestParams = Object.keys(data.best_params || {}).map(function (k) {
      return k + ' = <strong>' + data.best_params[k] + '</strong>';
    }).join(' · ');

    var best0 = (data.top || [])[0] || {};
    var bestTrades = best0.n_trades;
    var bestWr = best0.win_rate;
    var lowBest = (bestTrades != null && bestTrades < 2);
    var tradeInfo = bestTrades != null
      ? '<div class="opt-best-trades' + (lowBest ? ' warn' : '') + '">成交 ' + bestTrades + ' 笔'
        + (bestWr != null ? ' · 胜率 ' + (bestWr * 100).toFixed(0) + '%' : '')
        + (lowBest ? ' \u26a0 交易过少，该「最优」统计不可信' : '') + '</div>'
      : '';

    var wfErr = wf.error ? '<div class="opt-wf-error">Walk-Forward 未完整: ' + wf.error + '</div>' : '';

    el.innerHTML =
      '<div class="panel">' +
        '<div class="panel-title"><div class="dot dot-green"></div>最优参数 · ' + metricLabel(metric) + '</div>' +
        '<div class="opt-best-params">' + bestParams + '</div>' +
        '<div class="opt-best-score">样本内最优 ' + metricLabel(metric) + ': <strong>' +
          (data.best_score != null ? Number(data.best_score).toFixed(3) : '-') + '</strong></div>' +
        tradeInfo +
        '<button type="button" class="btn-run optimize" style="margin-top:10px" onclick="applyOptimizedParams()">' +
          '应用最优参数并回测</button>' +
      '</div>' +
      '<div class="panel">' +
        '<div class="panel-title"><div class="dot dot-yellow"></div>Walk-Forward 样本外验证</div>' +
        wfErr +
        '<div class="stats-grid opt-wf-stats">' +
          '<div class="stat-card"><div class="stat-value">' +
            (wf.avg_oos_sharpe != null ? wf.avg_oos_sharpe.toFixed(2) : '-') +
          '</div><div class="stat-label">平均 OOS 夏普</div></div>' +
          '<div class="stat-card"><div class="stat-value">' +
            (wf.avg_oos_return != null ? (wf.avg_oos_return * 100).toFixed(1) + '%' : '-') +
          '</div><div class="stat-label">平均 OOS 收益</div></div>' +
          '<div class="stat-card"><div class="stat-value ' + risk.cls + '">' + gapPct +
          '</div><div class="stat-label">过拟合差距 · ' + risk.label + '</div></div>' +
        '</div>' +
        '<p class="opt-wf-hint">过拟合差距 = 样本内得分 − 样本外得分；差距越大越可能是曲线拟合，实盘慎用。</p>' +
        (foldRows ? '<div class="table-wrap"><table class="data-table"><thead><tr>' +
          '<th>折</th><th>训练最优参数</th><th>OOS 收益</th><th>OOS 夏普</th></tr></thead><tbody>' +
          foldRows + '</tbody></table></div>' : '') +
      '</div>' +
      '<div class="panel">' +
        '<div class="panel-title"><div class="dot dot-blue"></div>Top 10 参数组合（样本内）</div>' +
        '<div class="table-wrap"><table class="data-table"><thead><tr>' +
          '<th>#</th><th>参数</th><th>夏普</th><th>总收益</th><th>最大回撤</th><th>交易数</th><th>胜率</th></tr></thead><tbody>' +
          topRows + '</tbody></table></div>' +
      '</div>';

    el.style.display = '';
  }

  global.StrategyOptimize = {
    fetchCatalog: fetchCatalog,
    getCatalog: getCatalog,
    isOptimizable: isOptimizable,
    buildPickerGroups: buildPickerGroups,
    renderAnalysis: renderAnalysis,
    renderOptimizeResults: renderOptimizeResults,
    metricLabel: metricLabel,
    overfitLevel: overfitLevel,
    getLastResult: function () { return global.StrategyOptimize._lastResult || null; },
    _lastResult: null,
  };
})(typeof window !== 'undefined' ? window : this);
