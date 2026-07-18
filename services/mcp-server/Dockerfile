FROM python:3.10-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN pip install "mcp>=1.2" "uvicorn>=0.30"
COPY app ./app

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 9000
CMD ["python", "-m", "app.server"]
