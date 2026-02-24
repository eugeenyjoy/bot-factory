# 🤖 Bot Factory

Платформа для создания AI-ботов с базой знаний (RAG).

## Возможности

- 🏗️ Создание нескольких ботов из одной панели
- 🧠 Каждый бот — своя личность, модель, память
- 📚 База знаний (RAG) — загружай документы, бот отвечает по ним
- 💬 Веб-чат с историей
- 💰 Система лимитов и монетизации
- ☑️ Управление историей (выбор и удаление как в Telegram)

## Быстрый старт

### 1. Клонируй

```bash
git clone https://github.com/ТВОЙ_ЮЗЕРНЕЙМ/bot-factory.git
cd bot-factory
2. Создай виртуальное окружение
Bash

python3 -m venv venv
source venv/bin/activate
3. Установи зависимости
Bash

pip install -r requirements.txt
4. Запусти
Bash

python app.py
5. Открой

http://localhost:8000
Как пользоваться
Нажми “+ Создать бота”
Укажи имя, API ключ (OpenRouter), модель, промпт
Нажми “▶ Запустить”
Нажми “💬 Чат” — общайся
Нажми “📚 Знания” — загрузи документы
API ключ
Получи бесплатный ключ на OpenRouter

Структура

bot-factory/
├── app.py              # FastAPI сервер + API
├── engine.py           # Движок управления ботами
├── core/
│   ├── brain.py        # Мозг бота (AI + RAG)
│   ├── memory.py       # Память (SQLite)
│   ├── config.py       # Конфигурация
│   └── rag.py          # База знаний (FAISS)
├── web/
│   ├── index.html      # Панель управления
│   ├── chat.html       # Веб-чат
│   ├── style.css       # Стили
│   ├── app.js          # Логика панели
│   └── chat.js         # Логика чата
├── bots/               # Данные ботов (создаются автоматически)
├── requirements.txt
└── README.md
Лицензия
MIT
MDEOF
```
