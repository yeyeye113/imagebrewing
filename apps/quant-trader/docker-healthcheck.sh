#!/bin/sh
# ============================================================
#  docker-healthcheck.sh — quant-trader 容器健康检查
# ============================================================
#  检查 API 服务器是否响应 /health 端点
#  退出码: 0=健康 | 1=不健康
# ============================================================

set -e

HEALTH_PORT="${QT_PORT:-8000}"

# 方法1: 检查 FastAPI /health 端点
if curl -sf "http://127.0.0.1:${HEALTH_PORT}/health" > /dev/null 2>&1; then
    exit 0
fi

# 方法2: 检查 /docs 端点 (FastAPI 内置)
if curl -sf "http://127.0.0.1:${HEALTH_PORT}/docs" > /dev/null 2>&1; then
    exit 0
fi

# 方法3: 检查端口是否在监听
if curl -sf "http://127.0.0.1:${HEALTH_PORT}/" > /dev/null 2>&1; then
    exit 0
fi

echo "[healthcheck] API server not responding on port ${HEALTH_PORT}"
exit 1
