# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    --timeout=120 \
    --retries=10 \
    --prefer-binary \
    -r requirements.txt

COPY shared/ ./shared/
COPY data_generator/ ./data_generator/
COPY pipeline/ ./pipeline/
COPY agent/ ./agent/
COPY api/ ./api/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
