#!/bin/bash
# Campus Sentinel — First-time setup script

set -e
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Campus Sentinel — Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check dependencies
command -v docker &>/dev/null || { echo "Docker is required"; exit 1; }
command -v docker-compose &>/dev/null || command -v docker compose &>/dev/null || { echo "Docker Compose is required"; exit 1; }

# Create .env from example
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✓ .env created — please update SECRET_KEY and passwords before production use"
fi

# Create snapshots directory
mkdir -p backend/snapshots
mkdir -p backend/models/weights
mkdir -p backend/models/abd
mkdir -p backend/models/prediction

echo "✓ Directories created"

# Pull and build containers
echo "Building Docker containers..."
docker compose build

# Start infrastructure first
docker compose up -d postgres redis
echo "Waiting for database to be ready..."
sleep 10

# Run migrations / schema
echo "Database schema will be applied via docker-entrypoint-initdb.d/init.sql on first start"

# Start all services
docker compose up -d
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Campus Sentinel is running!"
echo ""
echo " Dashboard:   http://localhost:3000"
echo " API Docs:    http://localhost:8000/api/docs"
echo " Grafana:     http://localhost:3001  (admin / admin123)"
echo " Flower:      http://localhost:5555"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
