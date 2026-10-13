FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgomp1 = OpenMP runtime required by XGBoost
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && mkdir -p /app/models

EXPOSE 8000

# entrypoint: wait for postgres -> seed demo data + train models -> serve API
ENTRYPOINT ["./entrypoint.sh"]
