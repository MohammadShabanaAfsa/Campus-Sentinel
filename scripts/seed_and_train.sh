#!/usr/bin/env bash
# seed_and_train.sh — seeds 30 days of synthetic data then trains ABD + RF models
# Usage: ./scripts/seed_and_train.sh [--days 30] [--synthetic]
set -e

DAYS=${1:-30}
BACKEND_CONTAINER="campus-sentinel-backend-1"

echo "=== Campus Sentinel: Data Seeding + Model Training ==="
echo ""

# Detect if running in Docker or locally
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$BACKEND_CONTAINER"; then
  EXEC="docker exec $BACKEND_CONTAINER"
  echo "[INFO] Running in Docker container: $BACKEND_CONTAINER"
else
  EXEC=""
  echo "[INFO] Running locally (no Docker detected)"
fi

echo ""
echo "[1/3] Seeding $DAYS days of synthetic behavior data..."
$EXEC python -m ai_engine.abd.data_seeder --days "$DAYS"

echo ""
echo "[2/3] Training ABD IsolationForest models..."
$EXEC python -c "
from ai_engine.abd.trainer import ABDTrainer
trainer = ABDTrainer()
trainer.train_all_zones()
print('ABD training complete')
"

echo ""
echo "[3/3] Training Threat Prediction RF model..."
$EXEC python -m ai_engine.prediction.model_trainer --model rf --hours-back "$((DAYS * 24))"

echo ""
echo "=== Done! ==="
echo "Models saved to /app/models/"
echo "You can now run the Campus Sentinel system with trained models."
