#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

FREE5GC_DIR="$ROOT/free5gc/free5gc-helm"
PACKETRUSHER_DIR="$ROOT/packetrusher/repo"

FREE5GC_COMMIT="6f67ec11512e8c6b4eb6b3237f46e71fec5bdda2"
PACKETRUSHER_COMMIT="194ae987ee2bacfae2cf57d435b475e54076679e"

SCHEME="https:"
FREE5GC_URL="${SCHEME}//github.com/free5gc/free5gc-helm.git"
PACKETRUSHER_URL="${SCHEME}//github.com/HewlettPackard/PacketRusher.git"

clone_or_update() {
    local name="$1"
    local url="$2"
    local directory="$3"
    local commit="$4"

    echo "=== Preparing $name ==="

    if [ -d "$directory/.git" ]; then
        git -C "$directory" remote set-url origin "$url"
        git -C "$directory" fetch origin --tags --prune
    elif [ -e "$directory" ]; then
        echo "ERROR: $directory exists but is not a Git repository"
        exit 1
    else
        mkdir -p "$(dirname "$directory")"
        git clone "$url" "$directory"
    fi

    git -C "$directory" fetch origin "$commit"
    git -C "$directory" checkout --detach "$commit"

    actual="$(git -C "$directory" rev-parse HEAD)"

    if [ "$actual" != "$commit" ]; then
        echo "ERROR: $name commit verification failed"
        exit 1
    fi

    echo "[OK] $name at $actual"
}

cd "$ROOT"

echo "=== Initializing Open5GLoS submodule ==="

git submodule sync --recursive
git submodule update --init --recursive

clone_or_update \
    "free5GC Helm" \
    "$FREE5GC_URL" \
    "$FREE5GC_DIR" \
    "$FREE5GC_COMMIT"

clone_or_update \
    "PacketRusher" \
    "$PACKETRUSHER_URL" \
    "$PACKETRUSHER_DIR" \
    "$PACKETRUSHER_COMMIT"

echo
echo "[OK] Source dependencies are available at verified commits"
echo
echo "Open5GLoS=$(git -C "$ROOT/open5glos/repo" rev-parse HEAD)"
echo "free5GC=$(git -C "$FREE5GC_DIR" rev-parse HEAD)"
echo "PacketRusher=$(git -C "$PACKETRUSHER_DIR" rev-parse HEAD)"
