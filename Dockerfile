FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（编译 psycopg2 等需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p data logs

# 复制并设置入口脚本
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
