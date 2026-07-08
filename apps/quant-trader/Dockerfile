# Quant Trader Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令（根据实际启动方式调整）
CMD ["python", "-m", "quanttrader", "api"]
