#!/bin/bash
# Run on a machine with internet access to prepare offline install package.
# Usage: bash download_wheels.sh [--platform <platform>] [--python-version <version>]
#
# Platforms:
#   manylinux2014_aarch64   ARM64 Linux (default)
#   manylinux2014_x86_64    x86_64 Linux
#
# Examples:
#   bash download_wheels.sh
#   bash download_wheels.sh --platform manylinux2014_x86_64 --python-version 3.10

set -e

PLATFORM="manylinux2014_aarch64"
PYTHON_VERSION="3.9"

while [[ $# -gt 0 ]]; do
    case $1 in
        --platform) PLATFORM="$2"; shift 2 ;;
        --python-version) PYTHON_VERSION="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

WHEELS_DIR="wheels"
OUTPUT="sd-helper-offline.tar.gz"

echo "Downloading wheels for Python ${PYTHON_VERSION} / ${PLATFORM} ..."
rm -rf "$WHEELS_DIR"
pip download sd-helper-cli \
    --python-version "$PYTHON_VERSION" \
    --platform "$PLATFORM" \
    --only-binary=:all: \
    -d "$WHEELS_DIR"

echo "Packaging ..."
tar -czf "$OUTPUT" "$WHEELS_DIR"
rm -rf "$WHEELS_DIR"

echo ""
echo "Done: ${OUTPUT}"
echo ""
echo "Transfer to server:"
echo "  scp ${OUTPUT} user@server:/tmp/"
echo ""
echo "Then on the server run:"
echo "  bash install.sh"
