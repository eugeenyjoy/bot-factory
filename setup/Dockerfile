FROM python:3.12-slim

WORKDIR /app

# Используем облегчённый requirements для Docker
COPY requirements.docker.txt .
RUN pip install --no-cache-dir -r requirements.docker.txt

COPY . .

EXPOSE 8000

CMD ["python", "app.py"]