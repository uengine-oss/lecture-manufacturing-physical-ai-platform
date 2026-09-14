FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hydops ./hydops
COPY labplatform ./labplatform
COPY skills ./skills
COPY sql ./sql
COPY scripts ./scripts
COPY tests ./tests
COPY data/reduced ./data/reduced
EXPOSE 8800 8910
