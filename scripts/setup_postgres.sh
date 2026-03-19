#!/bin/bash
set -e

# Create database and user
sudo -u postgres psql -c "CREATE DATABASE leads_auto_db;" || true
sudo -u postgres psql -c "CREATE USER leads_user WITH PASSWORD 'leads_password';" || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE leads_auto_db TO leads_user;" || true

echo "Database setup complete."
