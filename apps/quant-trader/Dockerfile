# ============================================================
#  Dockerfile — quant-trader (multi-stage build)
# ============================================================
#  构建: docker build -t quant-trader:latest -f apps/quant-trader/Dockerfile .
#  运行: docker run -d --name qt -p 8000:8000 quant-trader:latest
# ============================================================

# ── Stage 1: Builder ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="quant-trader"
LABEL description="quant-trader 全自动交易平台"
LABEL version="1.0.0"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl tini ca-certificates fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN groupadd -r qt && useradd -r -g qt -d /app -s /sbin/nologin qt

WORKDIR /app

# 拷贝应用代码 (所有Python文件直接在根目录)
COPY --chown=qt:qt . .

RUN mkdir -p /app/logs /app/data && chown -R qt:qt /app

USER qt

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QT_HOST=0.0.0.0 \
    QT_PORT=8000 \
    QT_WEBHOOK_URL="" \
    QT_ALLOW_LIVE=0 \
    QT_BROKER=cn_paper \
    QT_CORS_ORIGINS="*"

EXPOSE 8000

CMD ["python", "run.py", "api"]
