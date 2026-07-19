FROM python:3.10-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 HF_HOME=/app/.hf

RUN pip install --no-cache-dir uv

# full deps via uv sync (respects the CPU-only torch index in pyproject) — the
# P0 requirements.txt is not used for the deployable image, which needs the
# retrieval + agent stack (torch/sentence-transformers/langgraph/mcp/psycopg).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# bake the embedding model so there's no cold download on first request (the
# cross-encoder reranker is off by default, so it is NOT baked — saves ~2GB).
RUN mkdir -p /app/.hf && uv run python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-large-en-v1.5', device='cpu')"

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').getcode()==200 else 1)"

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
