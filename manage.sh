#!/bin/bash

# Management script for Drive Health Parser Docker deployment

set -e

COMPOSE_FILE="docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

function print_error() {
    echo -e "${RED}✗${NC} $1"
}

function print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

function show_help() {
    cat << EOF
Drive Health Parser - Management Script

Usage: ./manage.sh [command]

Commands:
    setup           Initial setup (build, migrate, create superuser)
    start           Start all services
    stop            Stop all services
    restart         Restart all services
    logs            Show logs (use -f to follow)
    status          Show status of all services
    
    migrate         Run database migrations
    makemigrations  Create new migrations
    shell           Open Django shell
    dbshell         Open database shell
    
    worker-scale N  Scale celery workers to N instances
    worker-restart  Restart celery workers
    
    clean           Stop and remove all containers and volumes (DESTRUCTIVE!)
    backup          Backup database
    
    help            Show this help message

Examples:
    ./manage.sh setup
    ./manage.sh start
    ./manage.sh logs -f celery_worker
    ./manage.sh worker-scale 4

EOF
}

function initial_setup() {
    print_info "Starting initial setup..."
    
    # Create directories
    print_info "Creating directories..."
    mkdir -p media/results media/uploads media/errors temp staticfiles
    
    # Build and start services
    print_info "Building Docker images..."
    docker-compose build
    
    print_info "Starting services..."
    docker-compose up -d
    
    # Wait for database to be ready
    print_info "Waiting for database to be ready..."
    sleep 5
    
    # Run migrations
    print_info "Running migrations..."
    docker-compose exec -T web python manage.py makemigrations
    docker-compose exec -T web python manage.py migrate
    
    # Create django-celery-results tables
    docker-compose exec -T web python manage.py migrate django_celery_results
    
    print_success "Setup complete!"
    print_info "Create a superuser with: docker-compose exec web python manage.py createsuperuser"
    print_info "Access the application at: http://localhost:8000"
}

function start_services() {
    print_info "Starting services..."
    docker-compose up -d
    print_success "Services started"
    docker-compose ps
}

function stop_services() {
    print_info "Stopping services..."
    docker-compose down
    print_success "Services stopped"
}

function restart_services() {
    print_info "Restarting services..."
    docker-compose restart
    print_success "Services restarted"
    docker-compose ps
}

function show_logs() {
    shift
    docker-compose logs "$@"
}

function show_status() {
    docker-compose ps
    echo ""
    print_info "Celery workers:"
    docker-compose exec celery_worker celery -A drivehealth inspect stats 2>/dev/null || print_error "Could not connect to workers"
}

function run_migrations() {
    print_info "Running migrations..."
    docker-compose exec web python manage.py migrate
    print_success "Migrations complete"
}

function make_migrations() {
    print_info "Creating migrations..."
    docker-compose exec web python manage.py makemigrations
    print_success "Migrations created"
}

function open_shell() {
    docker-compose exec web python manage.py shell
}

function open_dbshell() {
    docker-compose exec db psql -U drivehealth drivehealth
}

function scale_workers() {
    local count=$2
    if [ -z "$count" ]; then
        print_error "Please specify number of workers"
        exit 1
    fi
    print_info "Scaling celery workers to $count instances..."
    docker-compose up -d --scale celery_worker=$count
    print_success "Workers scaled to $count"
}

function restart_workers() {
    print_info "Restarting celery workers..."
    docker-compose restart celery_worker
    print_success "Workers restarted"
}

function clean_all() {
    print_error "WARNING: This will remove all containers and volumes!"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" == "yes" ]; then
        print_info "Cleaning up..."
        docker-compose down -v
        print_success "Cleanup complete"
    else
        print_info "Cancelled"
    fi
}

function backup_db() {
    local backup_file="backup_$(date +%Y%m%d_%H%M%S).sql"
    print_info "Backing up database to $backup_file..."
    docker-compose exec -T db pg_dump -U drivehealth drivehealth > "$backup_file"
    print_success "Database backed up to $backup_file"
}

# Main command router
case "$1" in
    setup)
        initial_setup
        ;;
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    logs)
        show_logs "$@"
        ;;
    status)
        show_status
        ;;
    migrate)
        run_migrations
        ;;
    makemigrations)
        make_migrations
        ;;
    shell)
        open_shell
        ;;
    dbshell)
        open_dbshell
        ;;
    worker-scale)
        scale_workers "$@"
        ;;
    worker-restart)
        restart_workers
        ;;
    clean)
        clean_all
        ;;
    backup)
        backup_db
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac

