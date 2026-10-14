FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv==0.10.3

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
RUN mkdir -p /app/data /app/backups \
    && chown 10001:10001 /app/data /app/backups

ENV PATH="/app/backend/.venv/bin:$PATH" \
    AI26_DATA_ROOT=/app/data \
    AI26_SOURCE_ROOT=/app/data/sources \
    AI26_FOOTAGE_ROOT=/mnt/footage

USER 10001:10001
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
