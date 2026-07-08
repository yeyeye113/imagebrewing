"""实时行情数据模块 — 支持新浪/腾讯数据源.

提供:
  - 实时行情获取
  - 历史数据获取
  - 数据缓存
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pandas as pd

from .log import get_logger

logger = get_logger("realtime")

# 数据缓存
_PRICE_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL_S = 300  # 5 分钟缓存


def get_realtime_quote(symbol: str) -> dict | None:
    """获取单只股票实时行情.

    Args:
        symbol: 股票代码 (如 '600519')

    Returns:
        dict: {
            "symbol": str,
            "name": str,
            "price": float,
            "change": float,
            "change_pct": float,
            "volume": float,
            "amount": float,
            "high": float,
            "low": float,
            "open": float,
            "prev_close": float,
        }
    """
    try:
        import akshare as ak

        # 使用新浪数据源
        df = ak.stock_zh_a_spot()

        # 查找股票
        code = symbol.replace('sh', '').replace('sz', '')
        row = df[df['代码'] == code]

        if row.empty:
            # 尝试带前缀
            prefix = 'sh' if code.startswith(('6', '68')) else 'sz'
            row = df[df['代码'] == f'{prefix}{code}']

        if row.empty:
            return None

        r = row.iloc[0]
        return {
            "symbol": code,
            "name": r.get('名称', ''),
            "price": float(r.get('最新价', 0)),
            "change": float(r.get('涨跌额', 0)),
            "change_pct": float(r.get('涨跌幅', 0)),
            "volume": float(r.get('成交量', 0)),
            "amount": float(r.get('成交额', 0)),
            "high": float(r.get('最高', 0)),
            "low": float(r.get('最低', 0)),
            "open": float(r.get('今开', 0)),
            "prev_close": float(r.get('昨收', 0)),
        }
    except Exception as e:
        logger.warning("获取实时行情失败 %s: %s", symbol, e)
        return None


def get_realtime_quotes_batch(symbols: list[str]) -> dict[str, dict]:
    """批量获取实时行情.

    Args:
        symbols: 股票代码列表

    Returns:
        dict: {symbol: quote_dict}
    """
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot()

        results = {}
        for symbol in symbols:
            code = symbol.replace('sh', '').replace('sz', '')
            row = df[df['代码'] == code]

            if row.empty:
                prefix = 'sh' if code.startswith(('6', '68')) else 'sz'
                row = df[df['代码'] == f'{prefix}{code}']

            if not row.empty:
                r = row.iloc[0]
                results[code] = {
                    "symbol": code,
                    "name": r.get('名称', ''),
                    "price": float(r.get('最新价', 0)),
                    "change": float(r.get('涨跌额', 0)),
                    "change_pct": float(r.get('涨跌幅', 0)),
                    "volume": float(r.get('成交量', 0)),
                    "amount": float(r.get('成交额', 0)),
                    "high": float(r.get('最高', 0)),
                    "low": float(r.get('最低', 0)),
                    "open": float(r.get('今开', 0)),
                    "prev_close": float(r.get('昨收', 0)),
                }

        return results
    except Exception as e:
        logger.warning("批量获取实时行情失败: %s", e)
        return {}


def get_historical_prices(
    symbol: str,
    days: int = 365,
    adjust: str = "qfq",
) -> pd.DataFrame | None:
    """获取历史价格数据 (带缓存).

    Args:
        symbol: 股票代码
        days: 获取天数
        adjust: 复权类型 ('qfq'=前复权, 'hfq'=后复权, ''=不复权)

    Returns:
        pd.DataFrame: OHLCV 数据
    """
    cache_key = f"{symbol}_{days}_{adjust}"

    # 检查缓存
    if cache_key in _PRICE_CACHE:
        ts, df = _PRICE_CACHE[cache_key]
        if time.time() - ts < _CACHE_TTL_S:
            return df

    try:
        import akshare as ak

        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        # 腾讯数据源
        prefix = 'sh' if symbol.startswith(('6', '68')) else 'sz'
        tx_code = f"{prefix}{symbol}"

        df = ak.stock_zh_a_hist_tx(
            symbol=tx_code,
            start_date=start,
            end_date=end,
            adjust=adjust,
        )

        if df is None or df.empty:
            return None

        # 标准化列名
        df = df.rename(columns={c: c.lower() for c in df.columns})

        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()

        # 确保有 volume 列
        if 'volume' not in df.columns and 'amount' in df.columns:
            df['volume'] = (df['amount'] * 10000) / df['close'].clip(lower=0.01)

        df = df.dropna(subset=['close'])

        # 更新缓存
        _PRICE_CACHE[cache_key] = (time.time(), df)

        return df
    except Exception as e:
        logger.warning("获取历史数据失败 %s: %s", symbol, e)
        return None


def get_market_overview() -> dict:
    """获取市场概况.

    Returns:
        dict: {
            "total_stocks": int,
            "up_count": int,
            "down_count": int,
            "flat_count": int,
            "avg_change_pct": float,
            "top_gainers": list[dict],
            "top_losers": list[dict],
        }
    """
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot()

        if df is None or df.empty:
            return {}

        # 计算统计
        total = len(df)
        up = len(df[df['涨跌幅'] > 0])
        down = len(df[df['涨跌幅'] < 0])
        flat = total - up - down
        avg_change = float(df['涨跌幅'].mean())

        # 涨幅榜
        top_gainers = df.nlargest(10, '涨跌幅')[['代码', '名称', '最新价', '涨跌幅']].to_dict('records')

        # 跌幅榜
        top_losers = df.nsmallest(10, '涨跌幅')[['代码', '名称', '最新价', '涨跌幅']].to_dict('records')

        return {
            "total_stocks": total,
            "up_count": up,
            "down_count": down,
            "flat_count": flat,
            "avg_change_pct": round(avg_change, 2),
            "top_gainers": top_gainers,
            "top_losers": top_losers,
        }
    except Exception as e:
        logger.warning("获取市场概况失败: %s", e)
        return {}


def clear_cache():
    """清除数据缓存."""
    global _PRICE_CACHE
    _PRICE_CACHE.clear()
    logger.info("数据缓存已清除")
