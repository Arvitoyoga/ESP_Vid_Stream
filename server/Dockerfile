FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
COPY static/ ./static/

USER 65532:65532
EXPOSE 8080
# Koneksi kamera dan frame terakhir disimpan dalam memori satu worker.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--log-level", "warning", "--no-access-log"]
