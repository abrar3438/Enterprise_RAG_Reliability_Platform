FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf_cache

# curl is only needed for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch FIRST, so sentence-transformers finds torch already installed
# and does not pull the multi-GB CUDA build from PyPI
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

# Download both models at build time (needs network here, not at runtime)
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# From here on the app must never call the Hugging Face Hub
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY app/ ./app/
COPY scripts/ ./scripts/

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app /opt/hf_cache
USER appuser

EXPOSE 8000

# start-period is long because startup loads two models and builds the BM25 index
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

# exec makes uvicorn PID 1 so it receives stop signals; keep ONE worker (each loads all models)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
