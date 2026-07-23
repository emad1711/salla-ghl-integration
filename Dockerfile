FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8010

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY salla_ghl ./salla_ghl
COPY alembic ./alembic
COPY scripts ./scripts

EXPOSE 8010

CMD ["sh", "scripts/start_web.sh"]
