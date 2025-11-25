FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libmagic1 \
        libxml2-dev \
        libxslt-dev \
        gcc \
        g++ \
        netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Copy and set permissions for entrypoint
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create a non-root user first
RUN adduser --disabled-password --gecos '' appuser

# Create necessary directories
RUN mkdir -p media/results media/errors media/uploads temp staticfiles
RUN chown -R appuser:appuser /app

# Keep running as root - entrypoint will handle permissions and switch user for Django

# Expose port
EXPOSE 8000

# Set entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command (can be overridden) - run as appuser
CMD ["su", "appuser", "-c", "gunicorn drivehealth.wsgi:application --bind 0.0.0.0:8000"]
