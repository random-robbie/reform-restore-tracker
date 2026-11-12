FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY sync-all.sh reform.cron docker-entrypoint.sh ./

RUN chmod +x /app/sync-all.sh /app/docker-entrypoint.sh \
    && cp /app/reform.cron /etc/cron.d/reform \
    && chmod 0644 /etc/cron.d/reform

# PORT is set by Render/Fly/Railway at runtime
ENV PORT=8125
ENV TZ=Europe/London
# Self-hosted compose sets ENABLE_CRON=1; on Render the Mac mini owns the schedule
ENV ENABLE_CRON=0

EXPOSE 8125

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8125"]
