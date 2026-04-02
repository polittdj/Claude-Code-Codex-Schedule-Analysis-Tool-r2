#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Dependency checks ──────────────────────────────────────────────────────────
check_python() {
  if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.11+ from https://python.org" >&2
    exit 1
  fi
  py_ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  required="3.11"
  if python3 -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)"; then
    echo "✓ Python $py_ver"
  else
    echo "ERROR: Python 3.11+ required (found $py_ver). Upgrade from https://python.org" >&2
    exit 1
  fi
}

check_java() {
  if ! command -v java &>/dev/null; then
    echo "ERROR: Java not found. Install JDK 11+ from https://adoptium.net" >&2
    exit 1
  fi
  java_ver=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d. -f1)
  if [ "$java_ver" -ge 11 ] 2>/dev/null; then
    echo "✓ Java $java_ver"
  else
    echo "ERROR: Java 11+ required (found version $java_ver). Install from https://adoptium.net" >&2
    exit 1
  fi
}

check_node() {
  if ! command -v node &>/dev/null; then
    echo "ERROR: Node.js not found. Install Node 18+ from https://nodejs.org" >&2
    exit 1
  fi
  node_ver=$(node -e 'process.stdout.write(process.version.slice(1).split(".")[0])')
  if [ "$node_ver" -ge 18 ] 2>/dev/null; then
    echo "✓ Node $node_ver"
  else
    echo "ERROR: Node.js 18+ required (found v$node_ver). Install from https://nodejs.org" >&2
    exit 1
  fi
}

echo "Checking prerequisites..."
check_python
check_java
check_node
echo ""

# ── Backend setup ──────────────────────────────────────────────────────────────
VENV_DIR="$REPO_ROOT/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet -r "$REPO_ROOT/backend/requirements.txt"
echo "✓ Python dependencies installed"

# ── Frontend setup ─────────────────────────────────────────────────────────────
echo "Installing Node.js dependencies..."
cd "$REPO_ROOT/frontend" && npm ci --silent
echo "✓ Node.js dependencies installed"
cd "$REPO_ROOT"

# ── Launch ─────────────────────────────────────────────────────────────────────
echo ""
echo "Starting Schedule Forensics Tool..."

# Start backend
"$VENV_DIR/bin/uvicorn" backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend dev server
cd "$REPO_ROOT/frontend" && npm run dev &
FRONTEND_PID=$!
cd "$REPO_ROOT"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

sleep 2
echo ""
echo "=========================================="
echo " Schedule Forensics Tool running at:"
echo " http://localhost:5173"
echo "=========================================="
echo "(Press Ctrl+C to stop)"

wait
