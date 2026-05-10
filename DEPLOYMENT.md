# Bot Factory - Развертывание на сервере

## 🚀 Быстрый старт

### Вариант 1: Docker (рекомендуется)

```bash
cd setup
docker-compose up -d
```

Готово! Приложение доступно на `http://localhost:8000`

---

### Вариант 2: Native Python (Linux/Mac)

```bash
# 1. Запустить скрипт развертывания
bash setup/deploy.sh

# 2. Отредактировать конфиг (при необходимости)
nano .env

# 3. Запустить приложение
source venv/bin/activate
python app.py
```

---

### Вариант 3: Systemd сервис (для production)

Создайте `/etc/systemd/system/bot-factory.service`:

```ini
[Unit]
Description=Bot Factory Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/bot-factory
Environment="PATH=/path/to/bot-factory/venv/bin"
Environment="BF_HOST=127.0.0.1"
Environment="BF_PORT=8000"
ExecStart=/path/to/bot-factory/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Затем:

```bash
sudo systemctl enable bot-factory
sudo systemctl start bot-factory
sudo systemctl status bot-factory
```

---

## ⚙️ Конфигурация

Скопируйте и отредактируйте `.env`:

```bash
cp .env.example .env
nano .env
```

**Ключевые переменные:**

| Переменная                   | Значение    | Описание                                 |
| ---------------------------- | ----------- | ---------------------------------------- |
| `BF_HOST`                    | `0.0.0.0`   | Адрес запуска (0.0.0.0 = все интерфейсы) |
| `BF_PORT`                    | `8000`      | Порт приложения                          |
| `BF_ALLOW_REMOTE`            | `0` или `1` | Разрешить удалённый доступ к API         |
| `BF_ADMIN_TOKEN`             | `*token*`   | Токен для API (если ALLOW_REMOTE=1)      |
| `BF_ENABLE_SYSTEM_FILES_API` | `0`         | Доступ к системным файлам                |

---

## 🔧 Nginx Reverse Proxy

Если используете Nginx перед приложением:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Для долгих запросов (loading model)
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

---

## 📋 Требования

- **Python 3.10+**
- **8GB RAM** (минимум)
- **20GB** свободного места (для моделей AI)
- **Linux/Mac** или **Docker**

---

## 🐳 Docker особенности

```bash
# Собрать образ заново (если обновлены dependencies)
docker-compose build --no-cache

# Посмотреть логи
docker-compose logs -f

# Остановить контейнер
docker-compose down

# Перезапустить
docker-compose restart
```

**Данные сохраняются в:**

- `bots/` — конфиги ботов
- `ollama_data/` — кэш моделей

---

## 🐛 Решение проблем

**Ошибка при импорте `telegram`:**

```bash
# Проверьте, что установлена правильная версия
pip list | grep telegram

# Переустановите
pip install --force-reinstall python-telegram-bot==21.8
```

**Ошибка `Port already in use`:**

```bash
# Найти процесс на порту 8000
lsof -i :8000

# Убить процесс
kill -9 <PID>

# Или использовать другой порт
export BF_PORT=8001
```

**Проблема с памятью:**

```bash
# Проверить использование памяти
docker stats

# Увеличить лимит в docker-compose.yml
mem_limit: 1g  # Вместо 512m
```

---

## ✅ Проверка установки

```bash
# Проверить работу
curl http://localhost:8000

# Проверить бэкэнд API (локально)
curl http://localhost:8000/api/bots

# С токеном (если BF_ALLOW_REMOTE=1)
curl -H "x-api-token: your-token" http://localhost:8000/api/bots
```

---

## 📊 Мониторинг

Логи доступны в:

- **Docker:** `docker-compose logs`
- **Systemd:** `sudo journalctl -u bot-factory -f`
- **Direct:** Вывод в консоль при запуске через `python app.py`

---

## 🔐 Безопасность для production

1. **Используйте токен:** `export BF_ADMIN_TOKEN=very-long-random-string`
2. **Ограничьте доступ:** `BF_ALLOW_REMOTE=0` (используйте reverse proxy локально)
3. **SSL/TLS:** Используйте Nginx с Let's Encrypt
4. **Firewall:** Разрешите только необходимые порты

---

## 📞 Поддержка

Если возникли проблемы:

1. Проверьте логи (`docker-compose logs`)
2. Убедитесь что установлены все зависимости
3. Проверьте переменные окружения в `.env`
