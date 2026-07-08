# 部署指南

## 架构概览

```
GitHub → GitHub Actions → ghcr.io (镜像仓库)
                              ↓
                    本地 watchdog 自动拉取
                              ↓
                    Docker 容器运行
                              ↓
                    frpc → VPS (62.234.39.66) → 用户
```

## 部署流程

### 1. 推送到 GitHub

```bash
cd /c/Users/眠/Projects/imagebrewing
git add .
git commit -m "更新内容"
git push origin master
```

### 2. GitHub Actions 自动构建

- **future-sim**: 检测到 `apps/future-sim/` 变更时触发
- **quant-trader**: 检测到 `apps/quant-trader/` 变更时触发
- **quant-monitor**: 检测到 `apps/quant-monitor/` 变更时触发

### 3. 本地自动拉取

启动 watchdog 脚本：

```bash
# 前台运行（测试用）
python deploy/watchdog.py --once

# 后台运行
python deploy/watchdog.py --daemon

# 指定项目
python deploy/watchdog.py --project future-sim
```

### 4. 查看日志

```bash
cat logs/watchdog.log
```

## 本地容器管理

### 手动启动容器

```bash
# 未来模拟引擎
docker run -d --name future-sim --restart unless-stopped -p 80:80 ghcr.io/yeyeye113/imagebrewing-future-sim:latest

# 量化交易
docker run -d --name quanttrader --restart unless-stopped -p 8010:8000 ghcr.io/yeyeye113/imagebrewing-quant-trader:latest

# 量化监控
docker run -d --name quant-monitor --restart unless-stopped -p 8081:8080 ghcr.io/yeyeye113/imagebrewing-quant-monitor:latest
```

### 手动拉取和重启

```bash
# 拉取最新镜像
docker pull ghcr.io/yeyeye113/imagebrewing-future-sim:latest

# 重启容器
docker stop future-sim && docker rm future-sim
docker run -d --name future-sim --restart unless-stopped -p 80:80 ghcr.io/yeyeye113/imagebrewing-future-sim:latest
```

### 查看容器状态

```bash
docker ps | grep -E "future-sim|quanttrader|quant-monitor"
```

## frpc 配置

frpc 已配置好，会将以下域名透传到本地容器：

| 域名 | 目标容器 | 本地端口 |
|------|----------|----------|
| sim.imagebrewing.com | future-sim | 80 |
| quant.imagebrewing.com | quanttrader | 8010 |

## 故障排除

### 容器无法启动

```bash
# 查看容器日志
docker logs future-sim

# 查看镜像是否存在
docker images | grep imagebrewing
```

### 镜像拉取失败

```bash
# 检查网络
docker pull ghcr.io/yeyeye113/imagebrewing-future-sim:latest

# 检查登录状态
docker login ghcr.io
```

### frpc 连接问题

```bash
# 检查 frpc 日志
docker logs lx-frpc

# 检查端口占用
netstat -an | grep ":80"
```
