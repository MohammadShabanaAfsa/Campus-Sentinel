#!/usr/bin/env bash
# deploy-local.sh — Full local macOS deploy for Campus Sentinel
# Installs deps, starts Postgres + Redis, seeds DB, boots backend + frontend
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
BLUE="\033[34m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
LOG_DIR="$ROOT/logs"
PID_DIR="$ROOT/.pids"

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${RESET} $*"; }
ok()   { echo -e "${GREEN}✓${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
fail() { echo -e "${RED}✗${RESET} $*"; exit 1; }
step() { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${RESET}"; }

mkdir -p "$LOG_DIR" "$PID_DIR"

# ─── 0. Detect OS ────────────────────────────────────────────────────────────
[[ "$(uname)" == "Darwin" ]] || fail "This script is for macOS only."

# ─── 1. Homebrew dependencies ────────────────────────────────────────────────
step "1/8  Homebrew dependencies"

if ! command -v brew &>/dev/null; then
  fail "Homebrew not found. Install from https://brew.sh"
fi

for pkg in postgresql@15 redis python@3.11; do
  if brew list "$pkg" &>/dev/null; then
    ok "$pkg already installed"
  else
    log "Installing $pkg..."
    brew install "$pkg"
  fi
done

PSQL="$(brew --prefix postgresql@15)/bin/psql"
PGCTL="$(brew --prefix postgresql@15)/bin/pg_ctl"
PG_DATA="$(brew --prefix postgresql@15)/var/postgresql@15"

# ─── 2. Start Postgres & Redis ───────────────────────────────────────────────
step "2/8  Start Postgres & Redis"

# PostgreSQL
if ! "$PSQL" -U "$(whoami)" -c '\q' postgres &>/dev/null; then
  log "Starting PostgreSQL..."
  brew services start postgresql@15
  sleep 3
fi
ok "PostgreSQL running"

# Redis (no password for local dev)
if ! redis-cli ping &>/dev/null 2>&1; then
  log "Starting Redis..."
  brew services start redis
  sleep 2
fi
ok "Redis running"

# ─── 3. Create DB + user ─────────────────────────────────────────────────────
step "3/8  Database setup"

DB_USER="cs_admin"
DB_PASS="cs_secure_pass_2024"
DB_NAME="campus_sentinel"

"$PSQL" -U "$(whoami)" postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" \
  | grep -q 1 || {
    log "Creating DB user $DB_USER..."
    "$PSQL" -U "$(whoami)" postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS' CREATEDB;"
  }

"$PSQL" -U "$(whoami)" postgres -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" \
  | grep -q 1 || {
    log "Creating database $DB_NAME..."
    "$PSQL" -U "$(whoami)" postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
  }

# Apply schema via init.sql
log "Applying schema..."
"$PSQL" -U "$DB_USER" -d "$DB_NAME" -f "$ROOT/infrastructure/postgres/init.sql" \
  > "$LOG_DIR/db-init.log" 2>&1 && ok "Schema applied" || warn "Schema may already be applied (check $LOG_DIR/db-init.log)"

ok "Database ready"

# ─── 4. Write .env ───────────────────────────────────────────────────────────
step "4/8  Environment configuration"

if [[ ! -f "$ROOT/.env" ]]; then
  cat > "$ROOT/.env" <<EOF
APP_NAME=Campus Sentinel
ENVIRONMENT=development
DEBUG=true

SECRET_KEY=$(openssl rand -hex 32)

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=$DB_NAME
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=$DB_PASS

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

YOLO_MODEL_PATH=yolov8n.pt
YOLO_CONFIDENCE_THRESHOLD=0.5
YOLO_DEVICE=cpu
FRAME_SKIP=3
MAX_CAMERAS=16

LOITERING_THRESHOLD_SECS=300
CROWD_DENSITY_THRESHOLD=20
RUNNING_SPEED_THRESHOLD=3.0
ALERT_COOLDOWN_SECS=60

MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM=alerts@campus-sentinel.local
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
MAIL_STARTTLS=true
MAIL_SSL_TLS=false
FRONTEND_URL=http://localhost:3000

NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
EOF
  ok ".env created"
else
  ok ".env already exists"
fi

export $(grep -v '^#' "$ROOT/.env" | xargs)

# ─── 5. Python virtual environment + deps ────────────────────────────────────
step "5/8  Python environment"

PYTHON="/opt/homebrew/bin/python3.11"
[[ -x "$PYTHON" ]] || fail "Python 3.11 not found at $PYTHON"

if [[ ! -d "$VENV" ]]; then
  log "Creating virtualenv with Python 3.11..."
  "$PYTHON" -m venv "$VENV"
fi
source "$VENV/bin/activate"

log "Installing Python packages (this may take a few minutes)..."
pip install --quiet --upgrade pip

# Install a lighter requirements set first (skip torch, ultralytics for speed)
pip install --quiet \
  fastapi==0.111.0 \
  uvicorn[standard]==0.30.1 \
  websockets==12.0 \
  python-multipart==0.0.9 \
  httpx==0.27.0 \
  sqlalchemy==2.0.30 \
  alembic==1.13.1 \
  asyncpg==0.29.0 \
  psycopg2-binary==2.9.9 \
  redis==5.0.4 \
  celery==5.4.0 \
  python-jose[cryptography]==3.3.0 \
  passlib[bcrypt]==1.7.4 \
  python-dotenv==1.0.1 \
  pydantic==2.7.1 \
  pydantic-settings==2.3.0 \
  email-validator==2.1.1 \
  numpy==1.26.4 \
  Pillow==10.3.0 \
  scikit-learn==1.5.0 \
  loguru==0.7.2 \
  prometheus-client==0.20.0 \
  prometheus-fastapi-instrumentator==7.0.0 \
  fastapi-mail==1.4.1 \
  python-dateutil==2.9.0 \
  pytz==2024.1 \
  tenacity==8.3.0 \
  aiofiles==23.2.1 \
  2>&1 | tail -3

# Install CV packages separately (may take longer)
log "Installing computer vision packages..."
pip install --quiet \
  opencv-python-headless==4.9.0.80 \
  ultralytics==8.2.18 \
  2>&1 | tail -3 || warn "CV packages failed — stream features will be limited"

ok "Python environment ready"

# ─── 6. Start backend ─────────────────────────────────────────────────────────
step "6/8  Start backend (FastAPI)"

cd "$ROOT/backend"

# Set PYTHONPATH so ai_engine and agents are importable
export PYTHONPATH="$ROOT/backend:$ROOT/ai-engine:$ROOT/agents:$ROOT"

PID_FILE="$PID_DIR/backend.pid"
LOG_FILE="$LOG_DIR/backend.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  warn "Backend already running (PID $(cat "$PID_FILE"))"
else
  log "Starting FastAPI on port 8000..."
  # --reload-dir scopes the file watcher to actual source directories only —
  # without it, uvicorn defaults to watching the whole cwd recursively,
  # which includes backend/.venv (hundreds of thousands of files) and
  # triggers constant spurious reloads.
  nohup "$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 --port 8000 \
    --reload \
    --reload-dir app \
    --reload-dir ../ai-engine \
    --reload-dir ../agents \
    --log-level info \
    > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 4

  # Health check
  for i in {1..10}; do
    if curl -sf http://localhost:8000/health > /dev/null; then
      ok "Backend healthy at http://localhost:8000"
      break
    fi
    [[ $i -eq 10 ]] && { warn "Backend not responding — check $LOG_FILE"; }
    sleep 2
  done
fi

# ─── 7. Start Celery worker (best-effort) ─────────────────────────────────────
step "7/8  Start Celery worker"

PID_FILE="$PID_DIR/celery.pid"
LOG_FILE="$LOG_DIR/celery.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  warn "Celery already running (PID $(cat "$PID_FILE"))"
else
  log "Starting Celery worker..."
  nohup "$VENV/bin/celery" -A app.core.celery_app.celery_app worker \
    --loglevel=info \
    --queues=ai_tasks,alerts,analytics \
    --concurrency=2 \
    > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 3
  if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    ok "Celery worker started"
  else
    warn "Celery worker failed to start — check $LOG_FILE"
  fi
fi

# ─── 8. Start frontend (Next.js) ─────────────────────────────────────────────
step "8/8  Start frontend (Next.js)"

cd "$ROOT/frontend"

PID_FILE="$PID_DIR/frontend.pid"
LOG_FILE="$LOG_DIR/frontend.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  warn "Frontend already running (PID $(cat "$PID_FILE"))"
else
  log "Installing npm packages..."
  npm install --legacy-peer-deps --loglevel warn > "$LOG_DIR/npm-install.log" 2>&1

  log "Building Next.js app (dev mode)..."
  nohup npm run dev > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 6

  for i in {1..12}; do
    if curl -sf http://localhost:3000 > /dev/null; then
      ok "Frontend ready at http://localhost:3000"
      break
    fi
    [[ $i -eq 12 ]] && warn "Frontend not responding yet — check $LOG_FILE"
    sleep 3
  done
fi

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔═══════════════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║      Campus Sentinel — Running Locally            ║${RESET}"
echo -e "${GREEN}${BOLD}╚═══════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Dashboard:   ${BLUE}http://localhost:3000${RESET}"
echo -e "  API docs:    ${BLUE}http://localhost:8000/api/docs${RESET}"
echo -e "  Health:      ${BLUE}http://localhost:8000/health${RESET}"
echo ""
echo -e "  Login:  ${YELLOW}admin@campus-sentinel.local${RESET} / ${YELLOW}Admin@123${RESET}"
echo ""
echo -e "  Logs:  $LOG_DIR/"
echo -e "  Stop:  ${BOLD}./scripts/stop-local.sh${RESET}"
echo ""
