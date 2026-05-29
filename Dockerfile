# Stage 1: Build frontend
FROM node:20-slim AS frontend
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ .
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY ming_sim/ ming_sim/
COPY content/ content/
COPY web_app.py .
COPY main.py .
COPY .agno_skills/ .agno_skills/

# 从 frontend stage 复制构建产物
COPY --from=frontend /web/dist web/dist/

# 数据目录（Railway 持久卷挂载点）
RUN mkdir -p /data
ENV MING_SIM_DATA_DIR=/data

# 暴露端口
EXPOSE 8010

# 启动命令
CMD ["python", "-m", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8010", "--timeout-keep-alive", "300"]
