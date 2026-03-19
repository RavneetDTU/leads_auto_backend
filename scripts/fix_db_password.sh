#!/bin/bash
sudo -u postgres psql -c "ALTER USER leads_user WITH PASSWORD 'leads_password';"
echo "Password for leads_user updated to 'leads_password'."
