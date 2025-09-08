# Docker Configuration for Literature Database Service

This document explains how to run the Literature Database service using Docker, both for development and production environments.

## 🐳 Docker Files Overview

- **`Dockerfile`** - Multi-stage build with development and production targets
- **`docker-compose.yml`** - Development environment with SQLite
- **`docker-compose.prod.yml`** - Production environment with PostgreSQL
- **`docker-compose.override.yml`** - Environment-specific overrides
- **`.dockerignore`** - Excludes unnecessary files from build context
- **`docker-entrypoint.sh`** - Service initialization script

## 🚀 Quick Start

### Development with SQLite (Recommended for local development)

```bash
# Start the service with Redis
docker-compose up -d

# View logs
docker-compose logs -f literature-database

# Stop services
docker-compose down
```

### Development with PostgreSQL

```bash
# Start with PostgreSQL profile
docker-compose --profile postgres up -d

# Or use the override configuration
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

### Production Deployment

```bash
# Copy environment file
cp .env.docker .env
# Edit .env with production values

# Start production services
docker-compose -f docker-compose.prod.yml up -d

# View production logs
docker-compose -f docker-compose.prod.yml logs -f
```

## 🔧 Configuration

### Environment Variables

Key environment variables for Docker deployment:

```bash
# Service Configuration
SERVICE_NAME=literature-database
SERVICE_PORT=8001
SERVICE_HOST=0.0.0.0

# Database Configuration
DATABASE_URL=sqlite:///data/metadata/literature.db
# OR for PostgreSQL:
# DATABASE_URL=postgresql://user:password@postgres:5432/literature_db

# Redis Configuration
REDIS_URL=redis://redis:6379
REDIS_ENABLED=true

# Development Settings
DEBUG=true
RELOAD=true
LOG_LEVEL=DEBUG

# Production Settings (override in production)
DEBUG=false
RELOAD=false
LOG_LEVEL=INFO
```

### Volume Mounts

The service uses the following volumes:

- **`./data:/app/data`** - Database and file storage (persistent)
- **`./logs:/app/logs`** - Application logs
- **`../../shared:/app/shared:ro`** - Shared types from monorepo (read-only)

## 📊 Database Options

### SQLite (Default)
- **Pros**: Simple, no external dependencies, good for development
- **Cons**: Not suitable for high concurrency
- **Config**: `DATABASE_URL=sqlite:///data/metadata/literature.db`

### PostgreSQL (Recommended for Production)
- **Pros**: Full ACID compliance, high concurrency, scalable
- **Cons**: Requires additional container
- **Config**: `DATABASE_URL=postgresql://user:password@postgres:5432/literature_db`

## 🛠️ Development Workflow

### Building the Image

```bash
# Build development image
docker build --target development -t literature-database:dev .

# Build production image
docker build --target production -t literature-database:prod .
```

### Running Tests

```bash
# Run tests in container
docker-compose exec literature-database python run_tests.py

# Or run tests during build
docker run --rm literature-database:dev test
```

### Interactive Development

```bash
# Start development environment
docker-compose up -d

# Get interactive shell
docker-compose exec literature-database bash

# View real-time logs
docker-compose logs -f literature-database
```

### Hot Reload Development

The development configuration includes volume mounts for hot-reload:

```yaml
volumes:
  - ./src:/app/src          # Source code changes
  - ./config:/app/config    # Configuration changes
  - ./.env:/app/.env        # Environment changes
```

## 🔒 Security Considerations

### Production Security

1. **Change default passwords** in `.env`:
   ```bash
   POSTGRES_PASSWORD=your_secure_password
   REDIS_PASSWORD=your_redis_password
   ```

2. **Restrict CORS origins**:
   ```bash
   CORS_ORIGINS='["https://your-frontend-domain.com"]'
   ```

3. **Use non-root user**: The Docker image runs as `appuser`

4. **Resource limits**: Production compose includes resource constraints

### Network Security

- Services communicate over internal Docker networks
- External access only through defined ports
- Redis and PostgreSQL are not exposed externally by default

## 🌐 Monorepo Integration

### Network Configuration

The service connects to the monorepo network:

```yaml
networks:
  monorepo-net:
    external: true
    name: research-monorepo-network
```

### Shared Types Integration

Shared types are mounted from the monorepo:

```yaml
volumes:
  - ../../shared:/app/shared:ro
```

### Service Discovery

Within the monorepo, the service is accessible at:
- **Internal**: `http://literature-database:8001`
- **External**: `http://localhost:8001`

## 🐛 Troubleshooting

### Common Issues

1. **Port already in use**:
   ```bash
   # Check what's using port 8001
   lsof -i :8001
   
   # Change port in docker-compose.yml
   ports:
     - "8002:8001"  # Use port 8002 externally
   ```

2. **Database connection issues**:
   ```bash
   # Check database container status
   docker-compose ps postgres
   
   # View database logs
   docker-compose logs postgres
   ```

3. **Shared types not found**:
   ```bash
   # Verify shared directory mount
   docker-compose exec literature-database ls -la /app/shared
   
   # Check path in docker-compose.yml
   ```

4. **Permission issues**:
   ```bash
   # Fix volume permissions
   sudo chown -R $USER:$USER ./data ./logs
   ```

### Health Checks

```bash
# Check service health
curl http://localhost:8001/health

# Check all container health
docker-compose ps
```

### Logs and Debugging

```bash
# View all service logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f literature-database
docker-compose logs -f postgres
docker-compose logs -f redis

# Debug inside container
docker-compose exec literature-database bash
```

## 📈 Performance Tuning

### Resource Allocation

Adjust resource limits in production:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'      # Increase for heavy workloads
      memory: 2G       # Increase for large databases
    reservations:
      cpus: '1.0'
      memory: 1G
```

### Database Optimization

For PostgreSQL:
```yaml
environment:
  POSTGRES_SHARED_PRELOAD_LIBRARIES: 'pg_stat_statements'
  POSTGRES_MAX_CONNECTIONS: '200'
  POSTGRES_SHARED_BUFFERS: '256MB'
```

## 🔄 Updates and Maintenance

### Updating the Service

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Database Backups

```bash
# SQLite backup
docker-compose exec literature-database cp /app/data/metadata/literature.db /app/data/backup_$(date +%Y%m%d).db

# PostgreSQL backup
docker-compose exec postgres pg_dump -U literature_user literature_db > backup_$(date +%Y%m%d).sql
```

## 🎯 Production Checklist

- [ ] Set secure passwords in `.env`
- [ ] Configure proper CORS origins
- [ ] Set up SSL/TLS termination (reverse proxy)
- [ ] Configure log rotation
- [ ] Set up database backups
- [ ] Monitor resource usage
- [ ] Configure health check endpoints
- [ ] Set up monitoring and alerting

---

**Ready to run the Literature Database service in Docker! 🐳**