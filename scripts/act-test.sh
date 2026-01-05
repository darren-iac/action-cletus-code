#!/usr/bin/env bash
# Helper script to run act for local GitHub Actions testing
# Usage: ./scripts/act-test.sh [options]
#
# Options:
#   -n, --dry-run    Show what would run without executing
#   -v, --verbose    Enable verbose output
#   -j, --job        Run specific job (default: test-unit, use test-local for full test)
#   -h, --help       Show this help message
#
# Requirements:
#   1. act installed: brew install act
#   2. Colima running: colima start
#   3. .secrets file configured (copy from .secrets.example) - only needed for test-local job

set -euo pipefail

# Default values
DRY_RUN=""
VERBOSE=""
JOB="test-unit"  # Default to unit test which doesn't require secrets
SECRET_FILE=".secrets"

# Detect Colima socket and set DOCKER_HOST
detect_docker_host() {
  if command -v colima &> /dev/null; then
    local colima_socket
    # colima status outputs "unix:///path/to/docker.sock" - extract just the path
    colima_socket=$(colima status 2>&1 | grep "docker socket" | awk '{print $NF}' | tr -d '"')
    # Remove the unix:// prefix for file existence check, keep for DOCKER_HOST
    local socket_path="${colima_socket#unix://}"
    if [[ -n "$socket_path" && -S "$socket_path" ]]; then
      export DOCKER_HOST="$colima_socket"
      echo "   Using Colima socket: $DOCKER_HOST"
      return 0
    fi
  fi
  return 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--dry-run)
      DRY_RUN="-n"
      shift
      ;;
    -v|--verbose)
      VERBOSE="-v"
      shift
      ;;
    -j|--job)
      JOB="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^# //g' | sed 's/^#//g'
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Check prerequisites
echo "🔍 Checking prerequisites..."

# Detect and set DOCKER_HOST for Colima FIRST
detect_docker_host

# Check if act is installed
if ! command -v act &> /dev/null; then
  echo "❌ act is not installed. Install with: brew install act"
  exit 1
fi
echo "✅ act is installed: $(act --version | head -1)"

# Check if docker is running
if ! docker info &> /dev/null; then
  echo "❌ Docker is not running. Start Colima with: colima start"
  exit 1
fi
echo "✅ Docker is running"

# Only check secrets for test-local job
if [[ "$JOB" == "test-local" ]]; then
  # Check if secrets file exists
  if [[ ! -f "$SECRET_FILE" ]]; then
    echo "❌ Secrets file not found: $SECRET_FILE"
    echo "   Copy .secrets.example to $SECRET_FILE and fill in your values:"
    echo "   cp .secrets.example $SECRET_FILE"
    echo ""
    echo "   Or run the unit test instead (no secrets required):"
    echo "   ./scripts/act-test.sh -j test-unit"
    exit 1
  fi
  echo "✅ Secrets file found: $SECRET_FILE"

  # Validate secrets file has required values
  if ! grep -q "GITHUB_TOKEN=ghp_" "$SECRET_FILE" 2>/dev/null; then
    echo "⚠️  Warning: GITHUB_TOKEN in $SECRET_FILE doesn't look like a valid token"
  fi

  if ! grep -q "ANTHROPIC_API_KEY=sk-ant-" "$SECRET_FILE" 2>/dev/null; then
    echo "⚠️  Warning: ANTHROPIC_API_KEY in $SECRET_FILE doesn't look like a valid key"
  fi
fi

echo ""
echo "🚀 Running act locally..."
echo "   Job: $JOB"
[[ "$JOB" == "test-local" ]] && echo "   Secrets: $SECRET_FILE"
[[ -n "$DRY_RUN" ]] && echo "   Mode: DRY RUN"
echo ""

# Build act command
if [[ "$JOB" == "test-local" ]]; then
  ACT_CMD="act -j $JOB --secret-file $SECRET_FILE $DRY_RUN $VERBOSE"
else
  ACT_CMD="act -j $JOB $DRY_RUN $VERBOSE"
fi

# Run act
echo "Executing: $ACT_CMD"
echo ""

exec $ACT_CMD
