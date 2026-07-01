#!/bin/bash

# ImperialReminder Bot + Dashboard Deployment Script
set -e  # Exit on any error

# Always run from the directory where this script lives (docker/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
BOT_CONTAINER="reminder"
DASH_CONTAINER="reminder-dashboard"
BOT_IMAGE="imperial-reminder"
DASH_IMAGE="imperial-reminder-dashboard"
BACKUP_TAG_BOT="imperial-reminder:backup"
BACKUP_TAG_DASH="imperial-reminder-dashboard:backup"
HEALTH_CHECK_TIMEOUT=120  # seconds to wait for health check

NO_CACHE=0
LOCAL=0
# Git branch to build from. Override at runtime with -b/--branch.
BRANCH=Dev
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--no-cache)
            NO_CACHE=1
            ;;
        -l|--local)
            LOCAL=1
            ;;
        -b|--branch)
            shift
            if [ -z "$1" ]; then
                echo "Error: -b/--branch requires a branch name"
                exit 1
            fi
            BRANCH="$1"
            ;;
        --branch=*)
            BRANCH="${1#*=}"
            ;;
        -h|--help)
            echo "Usage: $0 [-n|--no-cache] [-l|--local] [-b|--branch <name>]"
            echo "  -n, --no-cache       Build images from scratch (skip Docker layer cache)"
            echo "  -l, --local          Build + run from LOCAL files (bot + dashboard) via"
            echo "                       docker-compose.local.yml; no GitHub clone, no deploy key."
            echo "  -b, --branch <name>  Git branch to build from (default: Dev)"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 [-n|--no-cache] [-l|--local] [-b|--branch <name>]"
            exit 1
            ;;
    esac
    shift
done

# ── Local test mode ─────────────────────────────────────────────────────────
# Build and run the full stack (bot + dashboard) from the local working tree
# using docker-compose.local.yml. Runs in the foreground so Ctrl+C stops it, and
# deliberately skips the production backup / health-gate / rollback machinery.
if [ "$LOCAL" = "1" ]; then
    LOCAL_COMPOSE="docker-compose.local.yml"
    echo "==== ImperialReminder LOCAL test stack (bot + dashboard) ===="
    if ! command -v docker &> /dev/null; then
        echo "Docker is not installed or not in PATH"; exit 1
    fi
    if [ ! -f "$LOCAL_COMPOSE" ]; then
        echo "$LOCAL_COMPOSE not found in $SCRIPT_DIR"; exit 1
    fi
    if [ ! -f ".env.local" ]; then
        echo "Warning: .env.local not found - dev overrides (token, Mongo IP, dashboard) will be missing"
    fi
    if [ "$NO_CACHE" = "1" ]; then
        docker compose -f "$LOCAL_COMPOSE" build --no-cache
    fi
    echo "  Bot:       http://localhost:50014/health"
    echo "  Dashboard: http://localhost:54014"
    echo "Starting (Ctrl+C to stop)..."
    exec docker compose -f "$LOCAL_COMPOSE" up --build
fi

echo "==== Starting ImperialReminder Deployment ===="
echo "Timestamp: $(date)"
if [ "$NO_CACHE" = "1" ]; then
    echo "Mode: no-cache build"
else
    echo "Mode: cached build"
fi
echo "Branch: $BRANCH"
export GIT_REF=$BRANCH
# Source cloned inside container via Dockerfile (GIT_REF arg). No host-side git pull.

# Function to check container health
check_container_health() {
    local container=$1
    local timeout=$HEALTH_CHECK_TIMEOUT
    local elapsed=0
    local interval=5

    echo "Checking $container health..."

    while [ $elapsed -lt $timeout ]; do
        local status
        status=$(docker inspect "$container" --format='{{.State.Health.Status}}' 2>/dev/null || echo "not_found")

        if [ "$status" = "healthy" ]; then
            echo "  $container is healthy!"
            return 0
        elif [ "$status" = "unhealthy" ]; then
            echo "  $container is unhealthy!"
            return 1
        else
            echo "  Waiting for $container... (${elapsed}s/${timeout}s)"
            sleep $interval
            elapsed=$((elapsed + interval))
        fi
    done

    echo "  Health check timeout for $container"
    return 1
}

# Function to rollback to previous version
rollback() {
    echo "Rolling back to previous version..."

    docker compose down 2>/dev/null || true

    # Restore bot backup
    if docker images "$BACKUP_TAG_BOT" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "$BACKUP_TAG_BOT"; then
        docker rmi -f "$BOT_IMAGE" 2>/dev/null || true
        docker tag "$BACKUP_TAG_BOT" "$BOT_IMAGE"
    fi

    # Restore dashboard backup
    if docker images "$BACKUP_TAG_DASH" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "$BACKUP_TAG_DASH"; then
        docker rmi -f "$DASH_IMAGE" 2>/dev/null || true
        docker tag "$BACKUP_TAG_DASH" "$DASH_IMAGE"
    fi

    docker compose up -d

    local rollback_ok=true
    check_container_health "$BOT_CONTAINER" || rollback_ok=false
    check_container_health "$DASH_CONTAINER" || rollback_ok=false

    if $rollback_ok; then
        echo "Rollback completed successfully"
    else
        echo "Rollback failed - one or more containers unhealthy"
        exit 1
    fi
}

# Pre-deployment checks
echo ""
echo "--- Pre-deployment checks ---"

if ! command -v docker &> /dev/null; then
    echo "Docker is not installed or not in PATH"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "docker compose is not installed or not in PATH"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo ".env file not found in $SCRIPT_DIR"
    exit 1
fi

# Backup current images if they exist
echo ""
echo "--- Backing up current images ---"

if docker images "$BOT_IMAGE" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "$BOT_IMAGE"; then
    docker tag "$BOT_IMAGE" "$BACKUP_TAG_BOT" 2>/dev/null && echo "  Backed up $BOT_IMAGE" || echo "  Warning: Failed to backup $BOT_IMAGE"
fi

if docker images "$DASH_IMAGE" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "$DASH_IMAGE"; then
    docker tag "$DASH_IMAGE" "$BACKUP_TAG_DASH" 2>/dev/null && echo "  Backed up $DASH_IMAGE" || echo "  Warning: Failed to backup $DASH_IMAGE"
fi

# Step 1: Graceful shutdown
echo ""
echo "--- Stopping containers ---"

if docker ps --filter "name=$BOT_CONTAINER" --filter "name=$DASH_CONTAINER" --format "{{.Names}}" | grep -qE "$BOT_CONTAINER|$DASH_CONTAINER"; then
    docker compose down --timeout 30 || {
        echo "Warning: Graceful shutdown failed, forcing stop..."
        docker kill "$BOT_CONTAINER" "$DASH_CONTAINER" 2>/dev/null || true
        docker rm -f "$BOT_CONTAINER" "$DASH_CONTAINER" 2>/dev/null || true
    }
else
    echo "  No containers were running"
fi

# Step 2: Clean up old images
echo ""
echo "--- Cleaning up old images ---"
docker rmi -f "$BOT_IMAGE" 2>/dev/null || echo "  No old $BOT_IMAGE to remove"
docker rmi -f "$DASH_IMAGE" 2>/dev/null || echo "  No old $DASH_IMAGE to remove"

# Step 3: Build and start
echo ""
echo "--- Building and starting containers ---"

if [ "$NO_CACHE" = "1" ]; then
    echo "Building (no cache)..."
    docker compose build --no-cache
    BUILD_CMD="docker compose up -d"
else
    BUILD_CMD="docker compose up --build -d"
fi

if $BUILD_CMD; then
    echo ""
    echo "--- Waiting for health checks ---"

    all_healthy=true
    check_container_health "$BOT_CONTAINER" || all_healthy=false
    check_container_health "$DASH_CONTAINER" || all_healthy=false

    if $all_healthy; then
        echo ""
        echo "==== Deployment Successful! ===="
        echo "Timestamp: $(date)"
        echo ""
        echo "  Bot:       $BOT_CONTAINER (port 50014)"
        echo "  Dashboard: $DASH_CONTAINER (port 54014)"

        # Clean up backup images
        docker rmi -f "$BACKUP_TAG_BOT" 2>/dev/null || true
        docker rmi -f "$BACKUP_TAG_DASH" 2>/dev/null || true

        echo ""
        echo "Following logs (Ctrl+C to exit):"
        echo "================================="
        docker compose logs -f
    else
        echo ""
        echo "Health check failed, initiating rollback..."
        rollback
        exit 1
    fi
else
    echo ""
    echo "Failed to build/start containers, initiating rollback..."
    rollback
    exit 1
fi
