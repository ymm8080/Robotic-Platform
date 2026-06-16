# SAP-EWM Watchdog v3.4 Dockerfile
# 使用官方 Python 3.11 slim（禁止 Alpine，兼容 pyrfc 风格）
FROM python:3.11-slim

LABEL maintainer="robot-platform-team"
LABEL version="v3.4"
LABEL description="独立 Watchdog 进程：动态限流 + 致命熔断 + 安全模式"

# 安装系统依赖（docker stats 需要 docker CLI）
RUN apt-get update && apt-get install -y --no-install-recommends     docker.io     curl     && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 应用代码（只读挂载，运行时从 docker-compose 卷映射）
WORKDIR /app

# 创建日志目录
RUN mkdir -p /app/logs && chmod 755 /app/logs

# 非 root 运行（安全加固）
RUN groupadd -r watchdog && useradd -r -g watchdog watchdog
RUN usermod -aG docker watchdog  # 加入 docker 组，用于 docker stats
USER watchdog

# 健康检查：检查 PID 文件存在
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3     CMD python -c "import os, sys; sys.exit(0 if os.path.exists('/app/.watchdog.pid') else 1)"

# 默认命令
CMD ["python", "-u", "watchdog.py"]
