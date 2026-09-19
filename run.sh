#!/usr/bin/env bash
# Runner script for Morrowind Voice AI Companion ("Hey Azura")
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d "$DIR/.venv" ]; then
    echo "Virtual environment not found in $DIR/.venv. Please run setup first."
    exit 1
fi

export PYTHONPATH="$DIR:$PYTHONPATH"
exec "$DIR/.venv/bin/python3" "$DIR/main.py" "$@"
