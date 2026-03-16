#!/bin/bash
exec celery -A config.celery worker --beat --loglevel=info
