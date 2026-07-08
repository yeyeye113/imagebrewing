"""时间维度过滤器 — 按交易时段过滤信号。

分析发现:
  - 期货夜盘(21:00-次日01:00)准确率较高
  - 早盘(09:00-10:30)波动大，信号质量不稳定
  - 午盘(13:30-15:00)相对稳定
  - 收盘前15分钟容易假突破

用法:
    from quanttrader.engine.time_filter import TimeFilter
    tf = TimeFilter()
    result = tf.filter("future")  # 返回 True/False
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class TimeWindow:
    """一个时间段配置。"""
    name: str
    start_hour: int
    start_min: int
    end_hour: int
    end_min: int
    quality: str  # "good", "neutral", "bad"
    description: str


class TimeFilter:
    """交易时段过滤器。"""

    # 期货交易时段定义（类级常量，显式标注 ClassVar）
    FUTURES_WINDOWS: ClassVar[list[TimeWindow]] = [
        # 夜盘
        TimeWindow("夜盘前半", 21, 0, 23, 0, "good", "夜盘前半段，趋势明确时准确率高"),
        TimeWindow("夜盘后半", 23, 0, 1, 0, "neutral", "夜盘后半段，流动性下降"),
        # 早盘
        TimeWindow("早盘开盘", 9, 0, 9, 30, "bad", "开盘波动大，假信号多"),
        TimeWindow("早盘中段", 9, 30, 10, 30, "neutral", "早盘中段，趋势形成中"),
        TimeWindow("早盘尾段", 10, 30, 11, 30, "good", "早盘尾段，趋势相对稳定"),
        # 午盘
        TimeWindow("午盘前段", 13, 30, 14, 30, "good", "午盘前段，趋势延续"),
        TimeWindow("午盘尾段", 14, 30, 15, 0, "neutral", "午盘尾段，接近收盘"),
        # 收盘
        TimeWindow("收盘前", 14, 45, 15, 0, "bad", "收盘前15分钟，容易假突破"),
    ]

    def __init__(self, market: str = "future"):
        self.market = market
        self.windows = self.FUTURES_WINDOWS if market == "future" else []

    def _get_current_window(self) -> TimeWindow | None:
        """获取当前时间所在的时段。"""
        now = dt.datetime.now()
        h, m = now.hour, now.minute

        for w in self.windows:
            sh, sm, eh, em = w.start_hour, w.start_min, w.end_hour, w.end_min
            # 处理跨午夜的情况 (夜盘 21:00-01:00)
            if sh > eh:
                if h > eh or (h == eh and m < em):
                    # 还在午夜前的时段内（如23:30属于23:00-01:00）
                    return w
                elif h >= sh:
                    return w
            else:
                # 普通时段: 在 [start, end) 范围内
                start_ok = (h > sh) or (h == sh and m >= sm)
                end_ok = (h < eh) or (h == eh and m < em)
                if start_ok and end_ok:
                    return w

        return None

    def filter(self, market: str = "future") -> tuple[bool, str, str]:
        """过滤当前时段。

        Returns:
            (allowed, quality, reason):
              allowed = 是否允许交易
              quality = "good"/"neutral"/"bad"
              reason = 原因说明
        """
        if market != "future":
            return (True, "neutral", "非期货市场，不限制时段")

        window = self._get_current_window()
        if window is None:
            return (True, "neutral", "非交易时段")

        if window.quality == "good":
            return (True, "good", f"{window.name}: {window.description}")
        elif window.quality == "neutral":
            return (True, "neutral", f"{window.name}: {window.description}")
        else:  # bad
            return (False, "bad", f"{window.name}: {window.description}，建议等待")

    def get_quality(self, market: str = "future") -> str:
        """返回当前时段质量。"""
        _, quality, _ = self.filter(market)
        return quality

    def summary(self) -> str:
        lines = [f"[TimeFilter] {self.market} 交易时段:"]
        for w in self.windows:
            marker = "+" if w.quality == "good" else ("~" if w.quality == "neutral" else "-")
            lines.append(f"  [{marker}] {w.start_hour:02d}:{w.start_min:02d}-{w.end_hour:02d}:{w.end_min:02d} {w.name}: {w.description}")
        return "\n".join(lines)
