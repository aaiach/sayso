# sayso relay: keyless, stateless (mailboxes live in memory for 5 minutes).
# Build from this folder (e.g. Railway "root directory" = relay/), or: docker build -t sayso-relay relay/
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/relay/requirements.txt
RUN pip install --no-cache-dir -r /app/relay/requirements.txt
COPY . /app/relay
USER nobody
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn relay.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
