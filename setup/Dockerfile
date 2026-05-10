FROM python:3.12-slim

WORKDIR /app

# Системные зависимости для torch, faiss и других пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Используем одинаковый requirements файл для консистентности
COPY requirements.docker.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.docker.txt

# Копируем приложение
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/models', timeout=5)" || exit 1

EXPOSE 8000

# Запуск с правильными параметрами
ENV BF_HOST=0.0.0.0
ENV BF_PORT=8000
CMD ["python", "app.py"]