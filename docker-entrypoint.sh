#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

echo "Creating necessary directories and setting permissions..."
mkdir -p /app/media/uploads /app/media/results /app/media/errors /app/temp /app/staticfiles
chown -R appuser:appuser /app/media /app/temp /app/staticfiles 2>/dev/null || true

echo "Running migrations as appuser..."
su appuser -c "python manage.py migrate --noinput"

echo "Starting application..."
exec "$@"

