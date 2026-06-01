FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    MEETING_DB_PATH=/data/meeting.db \
    ROOMS_CONFIG_PATH=/data/rooms.json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py models.py ad_service.py rooms.json meeting.db ./
COPY templates ./templates
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh && mkdir -p /data

EXPOSE 5000
VOLUME ["/data"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "waitress-serve --host=0.0.0.0 --port=${PORT} app:app"]
