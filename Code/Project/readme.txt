#To start the frontend 
docker compose -f docker-compose.frontend.yml build   # build succeeds
docker compose -f docker-compose.frontend.yml up -d   # start/restart
# → browse to http://localhost:6080
