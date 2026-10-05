version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: lendflow-postgres
    environment:
      POSTGRES_DB: ${DB_NAME:-lendflow}
      POSTGRES_USER: ${DB_USER:-lendflow}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-lendflow}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-lendflow}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: lendflow-redis
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  web:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: lendflow-web
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120
    environment:
      - DJANGO_ENV=production
      - DB_HOST=postgres
      - DB_PORT=5432
      - REDIS_URL=redis://redis:6379/0
      - RATE_LIMIT_REDIS_URL=redis://redis:6379/1
      - SESSION_REDIS_URL=redis://redis:6379/2
      - CELERY_BROKER_URL=redis://redis:6379/3
      - CELERY_RESULT_BACKEND=redis://redis:6379/4
    env_file:
      - ../.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"
    volumes:
      - media_data:/app/media
      - static_data:/app/staticfiles

  celery-worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: lendflow-celery-worker
    command: celery -A config worker --loglevel=info --concurrency=4
    environment:
      - DJANGO_ENV=production
      - DB_HOST=postgres
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/3
      - CELERY_RESULT_BACKEND=redis://redis:6379/4
    env_file:
      - ../.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  celery-beat:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: lendflow-celery-beat
    command: celery -A config beat --loglevel=info
    environment:
      - DJANGO_ENV=production
      - DB_HOST=postgres
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/3
      - CELERY_RESULT_BACKEND=redis://redis:6379/4
    env_file:
      - ../.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  nginx:
    image: nginx:1.25-alpine
    container_name: lendflow-nginx
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/sites/lendflow.conf:/etc/nginx/conf.d/lendflow.conf:ro
      - static_data:/static:ro
      - media_data:/media:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - web

volumes:
  postgres_data:
  redis_data:
  media_data:
  static_data: