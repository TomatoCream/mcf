
## Development Guide

### How to Add New Packages

To add a new production dependency (e.g., 'requests'):
```bash
uv add requests
```

To add a new development dependency (e.g., 'ipdb'):
```bash
uv add --dev ipdb
```

After adding dependencies, always re-generate requirements.txt:
```bash
uv pip compile pyproject.toml -o requirements.txt
```

### How to Build Packages

To build your project's distributable packages (.whl, .tar.gz):
```bash
python -m build
```

Or using the virtual environment directly:
```bash
./venv/bin/python -m build
```

### Offline Build

To build offline packages for deployment:
```bash
./dev_scripts/build_offline.sh
```

This will create offline_packages/ with all dependencies and install.sh
