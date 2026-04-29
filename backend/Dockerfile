FROM python:3.11-slim AS builder

WORKDIR /app

# System deps for pymupdf, opencv, pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential libpq-dev libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Cache mount keeps the pip cache across builds so only new/changed
# packages are downloaded. This is the key to beating the timeout.
RUN pip install --no-compile -r requirements.txt

# ── Runtime stage: copy only installed packages + app code ──
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN mkdir -p uploads

CMD flask db upgrade && gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 300 --worker-class gthread --threads 4 --preload
