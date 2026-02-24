FROM python:3.12-slim

WORKDIR /app

# копируем requirements из корня проекта
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# копируем весь проект
COPY . .

EXPOSE 8000

CMD ["python", "app.py"]
