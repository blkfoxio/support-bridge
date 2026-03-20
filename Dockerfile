## Stage 1: Build the embeddable chat widget
FROM node:20-alpine AS widget-builder

WORKDIR /widget
COPY widget/package.json widget/package-lock.json* ./
RUN npm ci
COPY widget/ .
RUN npm run build

## Stage 2: Python application
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

COPY . .

# Copy built widget bundle from stage 1
COPY --from=widget-builder /widget/dist/ /app/widget/dist/

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
