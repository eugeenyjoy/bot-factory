# ⚡ Bot Factory - Быстрый старт

## 📦 Установка и запуск

### На локальной машине (разработка)

```bash
# 1. Клонируем/открываем проект
cd bot-factory

# 2. Запускаем скрипт установки
bash setup/deploy.sh

# 3. Запускаем приложение
source venv/bin/activate
python app.py
```

Откройте браузер: **http://localhost:8000**

---

### На сервере (production)

```bash
# Самый простой способ - Docker
cd setup
docker-compose up -d

# Проверить что всё работает
docker-compose logs -f
```

Приложение будет доступно на **http://server-ip:8000**

Если нужно закрыть доступ только для локального запуска в Nginx - смотрите [DEPLOYMENT.md](DEPLOYMENT.md)

---

## ✅ Что исправили в версии

| Проблема                       | Решение                                                        |
| ------------------------------ | -------------------------------------------------------------- |
| ❌ `aiogram` в requirements    | ✅ Заменено на `python-telegram-bot==21.8`                     |
| ❌ Несовместимые версии        | ✅ Синхронизированы requirements.txt и requirements.docker.txt |
| ❌ Нет документации по конфигу | ✅ Добавлен `.env.example` с примерами                         |
| ❌ Сложно разворачивать        | ✅ Добавлены `deploy.sh` скрипт и `DEPLOYMENT.md`              |
| ❌ Нет здоровья контейнера     | ✅ Добавлены health checks в Docker                            |

---

## 🔧 Конфигурация

При необходимости отредактируйте `.env`:

```bash
cp .env.example .env
nano .env
```

**Для production на сервере:**

- `BF_ALLOW_REMOTE=1` - если нужен удалённый доступ
- `BF_ADMIN_TOKEN=secret-key` - для защиты API

---

## 📚 Подробная документация

Смотрите [DEPLOYMENT.md](DEPLOYMENT.md) для:

- Systemd сервис конфигурация
- Nginx reverse proxy
- Решение проблем
- Мониторинг

---

## 🚀 Для быстрого тестирования

```bash
# Docker (самый быстрый способ)
cd setup && docker-compose up -d

# Или локально с Python
bash setup/deploy.sh
source venv/bin/activate
python app.py
```

**Готово!** 🎉

---

## ❓ Часто встречаемые ошибки

**`ModuleNotFoundError: No module named 'telegram'`**

```bash
pip install --force-reinstall python-telegram-bot==21.8
```

**`Port 8000 already in use`**

```bash
# Используйте другой порт
export BF_PORT=8001
python app.py
```

**На Docker: ошибка при установке зависимостей**

```bash
docker-compose build --no-cache
```

Если проблема persists - проверьте `docker-compose logs`

---

Нужна помощь? Проверьте [DEPLOYMENT.md](DEPLOYMENT.md) 📖
