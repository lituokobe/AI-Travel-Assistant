Start Redis Service (mount the data in a local directory):
``` shell
docker run -d \
  --name redis \
  -p 6379:6379 \
  -p 8001:8001 \
  -v ./data/redis-data:/data \
  redis/redis-stack:latest
```
Start MongoDB Service (mount the data in a local directory):
``` shell
docker run -d \
  --name mongodb \
  -p 27017:27017 \
  -v ./data/mongodb-data:/data/db \
  mongo:latest
```