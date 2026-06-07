FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn

COPY . /app/attack_server/

ENV PYTHONPATH=/app
ENV BASE_URL=http://localhost:8080

EXPOSE 8080

CMD ["uvicorn", "attack_server.server:app", "--host", "0.0.0.0", "--port", "8080"]
