# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

# libgomp is required by torch; curl is used by the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 passwd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CPU-only torch keeps the image around 1.5 GB instead of ~7 GB with CUDA.
# Pinned so a future torch release cannot break the embedding stack.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image: the container then starts and serves
# without any outbound HuggingFace traffic. First build needs network; rebuilds
# reuse this layer.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app ./app
COPY scripts ./scripts

RUN mkdir -p /data/uploads \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /models /data

USER appuser

ENV DATABASE_URL=sqlite:////data/spoiler_shield.db \
    UPLOAD_DIR=/data/uploads

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# Single worker on purpose: the embedding model costs ~1 GB RSS per process and
# SQLite is single-node. Scale up by sizing the box, not by adding workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
