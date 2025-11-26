# Trio Test Report Parser

Django application for parsing and analyzing hard disk diagnostic test reports from HTML, TXT, and PDF formats.

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL (via Docker)
- Redis (via Docker)

## Quick Start

### Using Docker (Recommended)

1. **Setup and run:**
   ```bash
   ./manage.sh setup
   ```

2. **Create superuser:**
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

3. **Access application:**
   - Web: http://localhost:8080
   - Admin: http://localhost:8080/admin

### Using Docker Compose directly

```bash
# Start services
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser
```

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Setup database:**
   ```bash
   python manage.py migrate
   ```

3. **Create superuser:**
   ```bash
   python manage.py createsuperuser
   ```

4. **Run development server:**
   ```bash
   python manage.py runserver
   ```

5. **Run Celery worker (in separate terminal):**
   ```bash
   celery -A drivehealth worker --loglevel=info
   ```

## Management Commands

```bash
./manage.sh start          # Start all services
./manage.sh stop           # Stop all services
./manage.sh logs -f        # View logs
./manage.sh migrate        # Run migrations
./manage.sh shell          # Django shell
```

## Features

- Parse hard disk diagnostic reports from HTML, TXT, and PDF formats
- Support for ZIP file uploads with automatic extraction
- Background job processing with Celery
- Duplicate drive detection and removal
- Export results to Excel and CSV formats
- Real-time job status tracking
- Parse error reporting and logging

## Services

- **Web**: Django application (port 8080)
- **PostgreSQL**: Database (port 5433)
- **Redis**: Celery broker (port 6380)
- **Celery Worker**: Background task processing
- **Celery Beat**: Scheduled tasks

## Environment Variables

- `DEBUG`: Debug mode (default: True)
- `SECRET_KEY`: Django secret key
- `DATABASE_URL`: PostgreSQL connection string
- `CELERY_BROKER_URL`: Redis connection string

## Supported File Formats

- **HTML**: Hard Disk Sentinel reports
- **TXT**: SCSI Toolbox and text-based diagnostic reports
- **PDF**: PDF diagnostic reports (using pdfminer.six)
- **ZIP**: Compressed archives containing any of the above formats
