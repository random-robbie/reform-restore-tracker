FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY reform.db ./

# PORT is set by Render/Fly/Railway at runtime
ENV PORT=8125

EXPOSE 8125

CMD uvicorn api:app --host 0.0.0.0 --port ${PORT}
