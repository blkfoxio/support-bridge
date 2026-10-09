#!/bin/bash
set -e
# Apply migrations before serving (Railway doesn't run a release step for this service).
python manage.py migrate --noinput
exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers 2
