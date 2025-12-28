#!/usr/bin/env bash

PROJECT_PATH="${1:-/home/df/projects/mcf}"
OFFLINE_PACKAGES_DIR="$PROJECT_PATH/offline_packages"

source "$PROJECT_PATH/.venv/bin/activate"

"$PROJECT_PATH/.venv/bin/pip" download -r "$PROJECT_PATH/requirements.txt" --dest "$OFFLINE_PACKAGES_DIR"
uv build --wheel
cp "$PROJECT_PATH/dist/"*.whl "$OFFLINE_PACKAGES_DIR/install.whl"

cat << EOF > "$OFFLINE_PACKAGES_DIR/install.sh"
pip install --no-index --find-links=./ install.whl
EOF
