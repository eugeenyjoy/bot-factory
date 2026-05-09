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

1. git clone https://github.com/eugeenyjoy/bot-factory.git
2. cd bot-factory
3. bash setup/install_linux.sh
4. Открой http://localhost:8000

### Docker:

- `cd setup`
- `docker compose up -d --build`

#### Мониторинг

- `docker ps` - статус
- `docker logs setup_bot-factory_1` - логи
- `docker stats` - интерактивный монитор
- `curl http://localhost:8000` - проверка на ответ
- `monitor.sh` - скрипт записи монитора docker stats
  `cat stats_log.csv | sort -t',' -k3 -rn | head -5` - Найти пиковые значения

##### Перезапуск

`docker-compose down`
`docker-compose up -d`

#### Остановка

`docker-compose down`

##### Чистка

`docker system prune -a`

## Запуск (после установки)

### Windows

- Двойной клик → Launch_Windows.bat

или:

- venv\Scripts\activate.bat
- python app.py

### Linux

- Двойной клик → Launch_Linux.sh

или:

- bash Launch_Windows.sh  
  или:
- source venv/bin/activate
- python app.py

### Терминал

# интерактивный выбор бота

python cli_chat.py

# конкретный бот по ID

python cli_chat.py --bot 63032ede14

# список всех ботов

python cli_chat.py --list

# с конкретным user ID (для разных сессий)

python cli_chat.py --bot 63032ede14 --user 42

Для удалённого сервера через SSH:

# подключаешься к серверу и запускаешь

ssh user@server "cd /path/to/bot-factory && source venv/bin/activate && python cli_chat.py"

# или tmux/screen чтобы не слетал

ssh user@server  
tmux new -s chat  
cd /path/to/bot-factory && source venv/bin/activate && python cli_chat.py

## Как это выглядит:

🤖 Bot Factory — Terminal Chat

══════════════════════════════════════════════════  
🤖 Мой бот  
Модель: deepseek/deepseek-chat-v3-0324  
Провайдер: openrouter  
══════════════════════════════════════════════════

Вы ▸ Привет, как дела?  
🤖 ▸ Привет! Всё отлично, спасибо! Чем могу помочь?

Вы ▸ /multi  
(многострочный режим — введите \end чтобы отправить)  
...│ Напиши функцию на Python  
...│ которая сортирует список  
...│ по убыванию  
...│ \end  
🤖 ▸ def sort_desc(lst):  
return sorted(lst, reverse=True)

Вы ▸ /clear  
🗑️ История очищена

Вы ▸ /quit  
👋 Пока!

## Команды в Telegram

/start — приветствие
/help — список всех команд
/reset — очистить историю чата
/balance — сколько сообщений осталось
/buy — купить сообщения за Stars

### Промпт (если включено user_can_add_prompt): чтобы /prompt работал

/prompt — показать текущие дополнения
/prompt Отвечай кратко — добавить инструкцию боту
/prompt_clear — удалить все дополнения

### Знания (если включено user_can_add_knowledge): чтобы /learn и загрузка файлов работали

/learn Офис работает с 9 до 18 — добавить текст в базу
/knowledge — инфо о базе знаний

- отправить файл (txt, md, json, py...) — загрузится автоматически

### Прочее (user_can_clear_history): чтобы /clear работал

/clear — то же что /reset
/stats — статистика бота

## Стек

- Python 3 + FastAPI
- OpenRouter API (OpenAI-совместимый)
- sentence-transformers (эмбеддинги)
- FAISS (векторный поиск)
- PyTorch CPU-only (~200 МБ вместо 7 ГБ)

###P.S. Вся ответственность за пользование данным инструментом полностью на вас, так как поведение ии не всегда можно полностью предсказать, а доступ он может получить чрезвычайный!!!

## Лицензия

MIT
