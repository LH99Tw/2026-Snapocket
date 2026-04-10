#!/bin/bash
set -e

# Start FastAPI backend
cd /app/backend
uvicorn main:app --host 0.0.0.0 --port 8000 &

# Start Next.js frontend
cd /app/frontend
HOSTNAME=0.0.0.0 node server.js &

# Wait for any process to exit
wait -n

# Exit with the status of the first exited process
exit $?
