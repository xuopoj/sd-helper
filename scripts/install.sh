#!/bin/bash
# Run on the server to install sd-helper into a virtualenv from offline wheels.
# Usage: bash install.sh [--wheels <path>] [--venv <path>] [--archive <path>]
#
# Examples:
#   bash install.sh
#   bash install.sh --archive /tmp/sd-helper-offline.tar.gz
#   bash install.sh --venv /opt/sd-helper --wheels ./my-wheels

set -e

ARCHIVE="sd-helper-offline.tar.gz"
WHEELS_DIR="wheels"
VENV_DIR="$HOME/.venv/sd-helper"

while [[ $# -gt 0 ]]; do
    case $1 in
        --archive) ARCHIVE="$2"; shift 2 ;;
        --wheels) WHEELS_DIR="$2"; shift 2 ;;
        --venv) VENV_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Extract archive if provided and wheels dir doesn't exist yet
if [[ ! -d "$WHEELS_DIR" ]]; then
    if [[ ! -f "$ARCHIVE" ]]; then
        echo "Error: archive not found: $ARCHIVE"
        echo "Transfer it first: scp sd-helper-offline.tar.gz user@server:/tmp/"
        exit 1
    fi
    echo "Extracting ${ARCHIVE} ..."
    tar -xzf "$ARCHIVE"
fi

# Create venv
echo "Creating virtualenv at ${VENV_DIR} ..."
python3 -m venv "$VENV_DIR"

# Install
echo "Installing sd-helper-cli ..."
"$VENV_DIR/bin/pip" install --no-index --find-links "$WHEELS_DIR" sd-helper-cli

echo ""
echo "Done. Activate with:"
echo "  source ${VENV_DIR}/bin/activate"
echo ""
echo "Then run:"
echo "  sd-helper --version"
