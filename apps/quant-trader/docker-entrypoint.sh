#!/bin/sh
# ============================================================
#  docker-entrypoint.sh — quant-trader 容器启动脚本
# ============================================================
#  用法 (docker run ... <CMD>):
#    daemon    启动 API 服务器 + 守护进程 (默认)
#    api       仅启动 API 服务器
#    once      单次决策后退出
#    scan      仅扫描 (不下单)
#    status    查看守护进程状态
#    <其他>    直接传给 python run.py
# ============================================================

set -e

# ── 信号处理 (graceful shutdown) ──────────────────────────────
_cleanup() {
    echo "[entrypoint] 收到终止信号，正在关闭..."
    # 杀掉所有子进程
    if [ -n "$API_PID" ]; then
        kill -TERM "$API_PID" 2>/dev/null || true
        wait "$API_PID" 2>/dev/null || true
    fi
    if [ -n "$DAEMON_PID" ]; then
        kill -TERM "$DAEMON_PID" 2>/dev/null || true
        wait "$DAEMON_PID" 2>/dev/null || true
    fi
    echo "[entrypoint] 已关闭。"
    exit 0
}

trap _cleanup TERM INT QUIT

# ── 配置文件初始化 ────────────────────────────────────────────
# 如果挂载了外部配置，优先使用；否则用镜像内默认配置
if [ -f /app/config/custom/config.yaml ]; then
    cp /app/config/custom/config.yaml /app/config.yaml
    echo "[entrypoint] 使用自定义 config.yaml"
fi

if [ -f /app/config/custom/daemon.yaml ]; then
    cp /app/config/custom/daemon.yaml /app/daemon.yaml
    echo "[entrypoint] 使用自定义 daemon.yaml"
fi

# ── 环境变量覆盖 (优先级: 环境变量 > 配置文件) ────────────────
CONFIG_FILE="${QT_CONFIG:-config.yaml}"
DAEMON_CONFIG="${QT_DAEMON_CONFIG:-daemon.yaml}"

# ── 启动模式路由 ──────────────────────────────────────────────
CMD="${1:-daemon}"

case "$CMD" in

  daemon)
    echo "[quant-trader] 模式: API 服务器 + 守护进程"
    # 启动 API 服务器 (后台)
    python -m uvicorn quanttrader.api.server:app \
        --host "${QT_HOST:-0.0.0.0}" \
        --port "${QT_PORT:-8000}" \
        --workers 1 \
        --log-level info &
    API_PID=$!
    echo "[quant-trader] API 服务器 PID=$API_PID, 端口=${QT_PORT:-8000}"

    # 等待 API 启动
    sleep 3

    # 启动守护进程 (前台)
    exec python run.py --daemon -c "$CONFIG_FILE" -d "$DAEMON_CONFIG"
    ;;

  api)
    echo "[quant-trader] 模式: 仅 API 服务器"
    exec python -m uvicorn quanttrader.api.server:app \
        --host "${QT_HOST:-0.0.0.0}" \
        --port "${QT_PORT:-8000}" \
        --workers 1 \
        --log-level info
    ;;

  once)
    echo "[quant-trader] 模式: 单次决策"
    exec python run.py --once -c "$CONFIG_FILE" -d "$DAEMON_CONFIG"
    ;;

  scan)
    echo "[quant-trader] 模式: 扫描"
    exec python run.py --scan -c "$CONFIG_FILE"
    ;;

  status)
    exec python run.py --status -d "$DAEMON_CONFIG"
    ;;

  backtest)
    shift
    exec python -m quanttrader backtest -c "$CONFIG_FILE" "$@"
    ;;

  shell)
    echo "[quant-trader] 进入交互式 Shell"
    exec /bin/sh
    ;;

  *)
    # 透传所有参数给 run.py
    exec python run.py "$@"
    ;;
esac
