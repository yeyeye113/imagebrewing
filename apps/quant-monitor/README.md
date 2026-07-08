# 量化交易监控台

实时监控量化交易系统状态的 Web Dashboard。

## 快速启动

```bat
cd C:\Users\眠\Desktop\workflows\quant-monitor
start.bat
```

或直接运行：

```bash
python server.py
```

打开浏览器访问: **http://localhost:8001**

## 功能

- **状态总览**: 总交易次数、胜率、当日盈亏、峰值权益
- **信号列表**: 从日志中提取最近的交易信号，买入(绿)/卖出(红) 颜色标记
- **风控参数**: 止损线、移动止损、最大回撤等可视化进度条
- **策略配置**: 当前策略名称、标的、数据源等关键参数
- **自动刷新**: 每 30 秒自动更新数据

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /` | Dashboard 页面 |
| `GET /api/status` | 交易状态（胜率、盈亏等） |
| `GET /api/signals` | 最近交易信号 |
| `GET /api/risk` | 风控参数 |
| `GET /api/config` | 策略配置 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `QT_ROOT` | `C:\Users\眠\Desktop\quant-trader` | 量化项目根目录 |

## 依赖

- Python 3.12+
- fastapi
- uvicorn
- pyyaml

## 数据源

Dashboard 读取以下文件（均在 quant-trader 项目中）：

- `daemon_state.json` — 交易状态
- `logs/tracker_*.log` — 交易日志
- `config.yaml` + `config_base.yaml` — 策略配置
