# 軽量なPython Alpineイメージを採用（数十MB程度で超軽量・高速）
FROM python:3.12-alpine

WORKDIR /app

# ソースコードと静的ファイルをコピー
COPY server.py ./
COPY static/ ./static/

# データベース保存用ディレクトリを作成
RUN mkdir -p /app/data

# データベースファイルのパスをDockerボリューム内に指定
ENV DB_PATH=/app/data/nomikai_tuke.db
ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["python", "server.py", "8765"]
