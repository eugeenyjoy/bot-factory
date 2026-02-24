# 🤖 Bot Factory

Конструктор AI-ботов с базой знаний. Загрузи документы — получи умного бота.

## Возможности

- 💬 Чат с AI (OpenRouter API)
- 📄 Загрузка PDF / текстовых файлов как базы знаний
- 🧠 RAG — бот отвечает на основе твоих документов
- 🔧 Создание нескольких ботов с разными настройками

## Структура проекта

bot-factory/
├── app.py ← точка входа
├── engine.py ← движок
├── requirements.txt ← зависимости
├── core/ ← мозги (brain, memory, rag, config)
├── web/ ← фронтенд (html, css, js)
├── docs/ ← документация
└── setup/ ← установка и деплой
├── install_windows.bat
├── install_linux.sh
├── setup.py
├── Dockerfile
└── docker-compose.yml

## Установка

### Windows

1. Установи [Python 3.10+](https://www.python.org/downloads/) (галочка **Add to PATH**)
2. Скачай и распакуй проект
3. Двойной клик → `setup/install_windows.bat`
4. Открой http://localhost:8000

### Linux

```bash
git clone https://github.com/YOUR_USERNAME/bot-factory.git
cd bot-factory
bash setup/install_linux.sh
Открой http://localhost:8000

Docker
Bash

cd setup
docker compose up --build
Запуск (после установки)
Windows

venv\Scripts\activate.bat
python app.py
Linux
Bash

source venv/bin/activate
python app.py
Стек
Python 3 + FastAPI
OpenRouter API (OpenAI-совместимый)
sentence-transformers (эмбеддинги)
FAISS (векторный поиск)
PyTorch CPU-only (~200 МБ вместо 7 ГБ)
Лицензия
MIT
```
