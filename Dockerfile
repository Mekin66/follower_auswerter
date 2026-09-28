# Container für die Web-Version (Flask + gunicorn).
#   docker build -t follower-auswertung .
#   docker run -p 8000:8000 -v follower-daten:/data -e SECRET_KEY=... follower-auswertung
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATEN_ORDNER=/data \
    PORT=8000

WORKDIR /app
COPY web/requirements.txt web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt

COPY core core
COPY web web

RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000

# GENAU 1 Worker (laufende Entfolgen-Abläufe liegen im Arbeitsspeicher), dafür mehrere Threads.
CMD gunicorn --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:${PORT} --forwarded-allow-ips="*" web.app:app
