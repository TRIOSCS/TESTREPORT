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

# Create necessary directories
RUN mkdir -p media/results media/errors temp staticfiles

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Set entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command (can be overridden)
CMD ["gunicorn", "drivehealth.wsgi:application", "--bind", "0.0.0.0:8000"]
