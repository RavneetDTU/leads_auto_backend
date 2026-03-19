#!/bin/bash

# Create User
sudo -u postgres psql -c "CREATE USER leads_user WITH PASSWORD 'leads_password';" || {
    echo "User creation failed (might already exist), trying to reset password..."
    sudo -u postgres psql -c "ALTER USER leads_user WITH PASSWORD 'leads_password';"
}

# Create Database
sudo -u postgres psql -c "CREATE DATABASE leads_auto_db OWNER leads_user;" || echo "Database might already exist."

# Grant Privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE leads_auto_db TO leads_user;"

echo "Database setup script finished."
