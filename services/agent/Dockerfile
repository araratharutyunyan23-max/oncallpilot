FROM python:3.10-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# deps first for layer caching (requirements.txt is generated from pyproject via
# `uv export` — see ops/Makefile / DECISIONS.md)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').getcode()==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
