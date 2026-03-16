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

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
