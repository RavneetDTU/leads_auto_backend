#!/bin/bash
echo "Restarting leads_auto service..."
sudo systemctl daemon-reload
sudo systemctl restart leads_auto.service
sudo systemctl status leads_auto.service --no-pager
echo "Service restarted."
