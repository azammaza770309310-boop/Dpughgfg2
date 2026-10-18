# CrowdCloud container image
# Build:  docker build -t crowdcloud:latest .
# Run:    docker run -p 5000:5000 -v crowdcloud-data:/data crowdcloud:latest
# Or use: docker compose up --build

FROM python:3.12-slim

# http.server is used only by the container healthcheck
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CROWDCLOUD_DB=/data/crowdcloud.db \
    CROWDCLOUD_UPLOADS=/data/uploads \
    BUSY_THRESHOLD=8 \
    HIGH_THRESHOLD=16 \
    AUTO_SERVE=0

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/
COPY run.py .

# SQLite data lives on a mounted volume so tickets survive restarts
VOLUME ["/data"]

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=4).status == 200 else 1)"

# 4 worker processes x 2 threads: enough parallelism for the demo load
# while staying a single small container (see report, scalability W6).
CMD ["gunicorn", "--workers", "4", "--threads", "2", \
     "--bind", "0.0.0.0:5000", "--access-logfile", "-", \
     "--timeout", "60", "run:app"]
