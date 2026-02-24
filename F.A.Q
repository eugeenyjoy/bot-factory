📨 Сообщения:
   save_message()        — сохранить
   get_history()         — получить историю
   clear_history()       — очистить чат
   clear_user_history()  — очистить юзера
   clear_all_history()   — очистить всё

🧠 Факты:
   add_fact()            — запомнить факт
   get_facts()           — получить факты
   clear_facts()         — забыть всё о юзере

💰 Монетизация:
   can_send()            — можно писать?
   use_message()         — засчитать сообщение
   add_purchased()       — добавить купленные
   get_remaining()       — сколько осталось

👑 VIP:
   set_vip()             — дать/забрать VIP
   get_all_vip()         — список VIP

📊 Статистика:
   get_stats()           — общая стата
   get_all_users()       — все юзеры
   get_payments()        — история платежей

🗑️ Очистка:
   reset_user()          — сброс юзера
   reset_all()           — сброс всего


Что умеет Brain:

💬 chat()               — юзер пишет → бот отвечает
🧠 _build_context()     — собирает промпт + факты + историю
🔍 _try_extract_facts() — автоматически запоминает факты
📊 get_stats()          — статистика
⚙️ update_model()       — сменить модель на лету
⚙️ update_prompt()      — сменить личность на лету
⚙️ update_free_limit()  — изменить лимиты
👑 set_vip()            — управление VIP
🗑️ clear_all()          — сброс


Что умеет config:

📋 list_bots()      — список всех ботов
📖 load_config()    — загрузить настройки бота
💾 save_config()    — сохранить настройки
🆕 create_bot()     — создать нового бота
🗑️ delete_bot()     — удалить бота + все данные
✏️ update_bot()     — изменить настройки частично
🤖 get_models()     — список моделей для панели

Пример config.json бота:

{
  "bot_id": "7123456",
  "name": "Бро",
  "bot_token": "7123456:ABC...",
  "api_key": "sk-or-...",
  "model": "mistralai/mistral-nemo",
  "system_prompt": "Ты лучший друг...",
  "max_history": 20,
  "free_messages": 20,
  "stars_price": 50,
  "messages_per_purchase": 50,
  "is_running": false,
  "enable_groups": false,
  "enable_web_chat": false,
  "vip_users": []
}


Что умеет Engine:

🟢 start_bot()       — запустить бота в отдельном потоке
🔴 stop_bot()        — остановить
🔄 restart_bot()     — перезапустить
♻️ reload_bot()      — обновить настройки на лету
📊 get_status()      — статус бота
📋 get_all_statuses() — статусы всех ботов
🚀 start_all()       — автозапуск всех
⛔ stop_all()        — остановить всех
🧠 get_brain()       — доступ к мозгу (для веб-чата)



Все API эндпоинты:

БОТЫ:
  GET    /api/bots              — список ботов
  POST   /api/bots              — создать бота
  GET    /api/bots/{id}         — настройки бота
  PUT    /api/bots/{id}         — обновить бота
  DELETE /api/bots/{id}         — удалить бота

УПРАВЛЕНИЕ:
  POST   /api/bots/{id}/start   — запустить
  POST   /api/bots/{id}/stop    — остановить
  POST   /api/bots/{id}/restart — перезапустить

ЮЗЕРЫ:
  GET    /api/bots/{id}/users   — список юзеров
  POST   /api/bots/{id}/vip     — VIP управление
  DELETE /api/bots/{id}/users/X — сброс юзера

ПАМЯТЬ:
  DELETE /api/bots/{id}/history     — очистить историю
  DELETE /api/bots/{id}/history/X   — очистить чат
  DELETE /api/bots/{id}/reset       — полный сброс

СТАТИСТИКА:
  GET    /api/bots/{id}/stats    — стата
  GET    /api/bots/{id}/payments — платежи

ВЕБ ЧАТ:
  POST   /api/bots/{id}/chat     — сообщение боту

МОДЕЛИ:
  GET    /api/models             — список моделей

ПАНЕЛЬ:
  GET    /                       — панель управления
  GET    /chat/{id}              — веб-чат с ботом




После запуска можно тестировать Доступ к базе знаний через API:

Bash

# загрузить файл
curl -X POST http://localhost:8000/api/bots/ВАШ_ID/knowledge/file \
  -F "file=@test.txt"

# добавить текст
curl -X POST http://localhost:8000/api/bots/ВАШ_ID/knowledge/text \
  -H "Content-Type: application/json" \
  -d '{"name": "info", "text": "Наша компания основана в 2020 году..."}'

# посмотреть базу
curl http://localhost:8000/api/bots/ВАШ_ID/knowledge

# поиск
curl -X POST http://localhost:8000/api/bots/ВАШ_ID/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "когда основана компания"}'


Что умеет веб-чат:

✅ Уникальный user_id (сохраняется в localStorage)
✅ Одна история с Telegram (один brain)
✅ Индикатор "бот печатает"
✅ Предупреждение когда мало сообщений
✅ Обработка ошибок (бот выключен, лимит, сервер)
✅ Enter для отправки
✅ Адаптивный дизайн