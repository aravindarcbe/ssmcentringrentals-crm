#!/usr/bin/env bash
# One-command local setup: creates a virtualenv, installs dependencies,
# runs migrations, and starts the dev server.
# Usage: ./setup.sh

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "Applying database migrations..."
python manage.py migrate

if ! python manage.py shell -c "from django.contrib.auth.models import User; exit(0 if User.objects.filter(is_superuser=True).exists() else 1)" 2>/dev/null; then
    echo ""
    echo "No admin login exists yet. Let's create one:"
    python manage.py createsuperuser
fi

echo ""
echo "Starting the dev server at http://127.0.0.1:8000  (Ctrl+C to stop)"
echo "Admin/CRUD screens: http://127.0.0.1:8000/admin/"
python manage.py runserver
