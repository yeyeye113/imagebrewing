# ============================================================
#  Dockerfile — quant-trader (multi-stage build)
# ============================================================
#  构建: docker build -t quant-trader:latest .
#  运行: docker run -d --name qt -p 8000:8000 --env-file .env quant-trader:latest
# ============================================================

# ── Stage 1: Builder ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# 系统依赖 (编译用，运行时不需要)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="quant-trader"
LABEL description="quant-trader 全自动交易平台"
LABEL version="0.6.0"

# 运行时系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        tini \
        ca-certificates \
        fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

# 从 builder 拷贝已安装的 Python 包
COPY --from=builder /install /usr/local

# 创建非 root 用户
RUN groupadd -r qt && useradd -r -g qt -d /app -s /sbin/nologin qt

WORKDIR /app

# 拷贝应用代码
COPY --chown=qt:qt quanttrader/ ./quanttrader/
COPY --chown=qt:qt run.py .
COPY --chown=qt:qt config.yaml .
COPY --chown=qt:qt config.example.yaml .
COPY --chown=qt:qt config_llm.yaml .
COPY --chown=qt:qt daemon.yaml .

# 拷贝启动脚本和健康检查
COPY --chown=qt:qt docker-entrypoint.sh /usr/local/bin/
COPY --chown=qt:qt docker-healthcheck.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-healthcheck.sh

# 创建数据目录
RUN mkdir -p /app/logs /app/data && chown -R qt:qt /app

# 切换到非 root 用户
USER qt

# 环境变量 (默认值，可通过 docker-compose 覆盖)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QT_HOST=0.0.0.0 \
    QT_PORT=8000 \
    QT_WEBHOOK_URL="" \
    QT_ALLOW_LIVE=0 \
    QT_BROKER=cn_paper \
    QT_CORS_ORIGINS="*"

# 端口
EXPOSE 8000

# 健康检查 (每30秒检查一次)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["/usr/local/bin/docker-healthcheck.sh"]

# 使用 tini 作为 PID 1 (正确处理信号)
ENTRYPOINT ["tini", "--", "/usr/local/bin/docker-entrypoint.sh"]

# 默认: 启动 API 服务器 + 守护进程
CMD ["daemon"]
