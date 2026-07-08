# imagebrewing

个人项目集，包含以下应用：

## 项目结构

```
apps/
├── future-sim/       # 未来模拟引擎 (React + TypeScript + Vite)
├── quant-trader/     # 量化交易系统 (Python)
└── quant-monitor/    # 量化监控系统 (Python + FastAPI)
```

## 技术栈

| 项目 | 技术栈 | 域名 |
|------|--------|------|
| 未来模拟引擎 | React + TypeScript + Vite | sim.imagebrewing.com |
| 量化交易 | Python + FastAPI | quant.imagebrewing.com |
| 量化监控 | Python + FastAPI | - |

## 开发

```bash
# 未来模拟引擎
cd apps/future-sim
npm install
npm run dev

# 量化交易
cd apps/quant-trader
pip install -r requirements.txt
python -m quanttrader

# 量化监控
cd apps/quant-monitor
pip install -r requirements.txt
python server.py
```

## 部署

部署流程完全自动化：
1. 代码推送到 GitHub
2. GitHub Actions 自动构建 Docker 镜像
3. 镜像推送到 ghcr.io
4. 本地 watchdog 自动拉取并重启容器

详见 [deploy/README.md](deploy/README.md)

## 许可证

MIT
