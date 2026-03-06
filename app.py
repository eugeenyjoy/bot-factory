"""
Точка входа — локальный сервер
Запускает панель управления + API + движок ботов
python app.py → открывай localhost:8000
"""

import uvicorn
import webbrowser
import threading
import time
import logging

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from engine import Engine
from core.config import (
    list_bots, load_config, create_bot, delete_bot,
    update_bot, get_models, BOTS_DIR
)

# логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# корневая папка
ROOT_DIR = Path(__file__).parent

# FastAPI приложение
app = FastAPI(title="Bot Factory", version="1.0")

# движок ботов
engine = Engine()


# ====================================================
# МОДЕЛИ ЗАПРОСОВ (что приходит от панели)
# ====================================================

class CreateBotRequest(BaseModel):
    name: str
    bot_token: Optional[str] = ""
    api_key: str
    model: Optional[str] = "mistralai/mistral-nemo"
    system_prompt: Optional[str] = "Ты — полезный AI ассистент."


class UpdateBotRequest(BaseModel):
    name: Optional[str] = None
    bot_token: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    max_history: Optional[int] = None
    free_messages: Optional[int] = None
    stars_price: Optional[int] = None
    messages_per_purchase: Optional[int] = None
    enable_telegram: Optional[bool] = None
    enable_groups: Optional[bool] = None


class VipRequest(BaseModel):
    user_id: int
    is_vip: bool


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[int] = 0


# ====================================================
# API — БОТЫ
# ====================================================

@app.get("/api/bots")
def api_list_bots():
    return engine.get_all_statuses()


@app.post("/api/bots")
def api_create_bot(req: CreateBotRequest):
    config = create_bot(
        name=req.name,
        bot_token=req.bot_token,
        api_key=req.api_key,
        model=req.model,
        system_prompt=req.system_prompt
    )
    return {"ok": True, "bot": config}


@app.get("/api/bots/{bot_id}")
def api_get_bot(bot_id: str):
    config = load_config(bot_id)
    if not config:
        raise HTTPException(status_code=404, detail="Bot not found")
    status = engine.get_status(bot_id)
    return {"config": config, "status": status}


@app.put("/api/bots/{bot_id}")
def api_update_bot(bot_id: str, req: UpdateBotRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    config = update_bot(bot_id, updates)
    if not config:
        raise HTTPException(status_code=404, detail="Bot not found")
    engine.reload_bot(bot_id)
    return {"ok": True, "config": config}


@app.delete("/api/bots/{bot_id}")
def api_delete_bot(bot_id: str):
    engine.deactivate_bot(bot_id)
    delete_bot(bot_id)
    return {"ok": True}


# ====================================================
# API — УПРАВЛЕНИЕ (активация бота + веб-чат)
# ====================================================

@app.post("/api/bots/{bot_id}/start")
def api_start_bot(bot_id: str):
    """Активировать бота (веб-чат работает сразу)"""
    success = engine.activate_bot(bot_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to activate bot")
    return {"ok": True}


@app.post("/api/bots/{bot_id}/stop")
def api_stop_bot(bot_id: str):
    """Деактивировать бота"""
    engine.deactivate_bot(bot_id)
    return {"ok": True}


@app.post("/api/bots/{bot_id}/restart")
def api_restart_bot(bot_id: str):
    """Перезапустить бота"""
    engine.deactivate_bot(bot_id)
    time.sleep(1)
    engine.activate_bot(bot_id)
    return {"ok": True}


# ====================================================
# API — TELEGRAM (опционально)
# ====================================================

@app.post("/api/bots/{bot_id}/telegram/start")
def api_start_telegram(bot_id: str):
    """Подключить Telegram"""
    success = engine.start_telegram(bot_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed. Check bot token.")
    return {"ok": True}


@app.post("/api/bots/{bot_id}/telegram/stop")
def api_stop_telegram(bot_id: str):
    """Отключить Telegram"""
    engine.stop_telegram(bot_id)
    return {"ok": True}


# ====================================================
# API — ВЕБ ЧАТ (работает всегда если бот активен)
# ====================================================

@app.post("/api/bots/{bot_id}/chat")
def api_web_chat(bot_id: str, req: ChatRequest):
    """Чат с ботом через веб"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active. Click Start first.")

    result = brain.chat(
        chat_id=req.user_id,
        user_id=req.user_id,
        message=req.message
    )

    # если лимит — добавляем понятное сообщение
    if not result["ok"] and result.get("error") == "limit":
        remaining = result.get("remaining", 0)
        result["reply"] = (
            f"📭 Лимит сообщений исчерпан!\n\n"
            f"Использовано все доступные сообщения.\n"
            f"Подключите Telegram чтобы купить ещё (/buy)."
        )

    return result


# ====================================================
# API — ПОЛЬЗОВАТЕЛИ
# ====================================================

@app.get("/api/bots/{bot_id}/users")
def api_get_users(bot_id: str):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not running")
    return brain.get_users()


@app.post("/api/bots/{bot_id}/vip")
def api_set_vip(bot_id: str, req: VipRequest):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not running")
    brain.set_vip(req.user_id, req.is_vip)
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/users/{user_id}")
def api_clear_user(bot_id: str, user_id: int):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not running")
    brain.clear_user(user_id)
    return {"ok": True}


# ====================================================
# API — ПАМЯТЬ
# ====================================================

@app.delete("/api/bots/{bot_id}/history")
def api_clear_all_history(bot_id: str):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not running")
    brain.memory.clear_all_history()
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/history/{chat_id}")
def api_clear_chat(bot_id: str, chat_id: int):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not running")
    brain.clear_chat(chat_id)
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/reset")
def api_reset_bot(bot_id: str):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not running")
    brain.clear_all()
    return {"ok": True}

# ====================================================
# API — ИСТОРИЯ ЧАТА (просмотр и удаление)
# ====================================================

@app.get("/api/bots/{bot_id}/history/{chat_id}")
def api_get_history(bot_id: str, chat_id: int):
    """Получить историю чата с ID сообщений"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    return brain.memory.get_history_with_index(chat_id)


@app.delete("/api/bots/{bot_id}/messages/{msg_id}")
def api_delete_one_message(bot_id: str, msg_id: int):
    """Удалить одно сообщение по ID"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    success = brain.memory.delete_message_by_id(msg_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}


class DeleteMessagesRequest(BaseModel):
    msg_ids: list


@app.post("/api/bots/{bot_id}/messages/delete")
def api_delete_messages(bot_id: str, req: DeleteMessagesRequest):
    """Удалить несколько сообщений по списку ID"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    deleted = brain.memory.delete_messages_by_ids(req.msg_ids)
    return {"ok": True, "deleted": deleted}

# ====================================================
# API — СТАТИСТИКА
# ====================================================

@app.get("/api/bots/{bot_id}/stats")
def api_get_stats(bot_id: str):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not running")
    return brain.get_stats()


@app.get("/api/bots/{bot_id}/payments")
def api_get_payments(bot_id: str):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not running")
    return brain.memory.get_payments()

# ====================================================
# API — БАЗА ЗНАНИЙ (RAG)
# ====================================================

@app.get("/api/bots/{bot_id}/knowledge")
def api_get_knowledge(bot_id: str):
    """Информация о базе знаний"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    return brain.rag.get_info()


class UploadFileRequest(BaseModel):
    filename: str
    content_base64: str


@app.post("/api/bots/{bot_id}/knowledge/file")
def api_upload_file(bot_id: str, req: UploadFileRequest):
    """Загрузить файл в базу знаний (base64)"""
    import base64
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    try:
        content = base64.b64decode(req.content_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64")
    return brain.rag.add_file(req.filename, content)


class AddTextRequest(BaseModel):
    name: str
    text: str


@app.post("/api/bots/{bot_id}/knowledge/text")
def api_add_text(bot_id: str, req: AddTextRequest):
    """Добавить текст в базу знаний"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    return brain.rag.add_text(req.name, req.text)


@app.delete("/api/bots/{bot_id}/knowledge/{filename}")
def api_delete_knowledge_file(bot_id: str, filename: str):
    """Удалить файл из базы знаний"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    brain.rag.remove_file(filename)
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/knowledge")
def api_clear_knowledge(bot_id: str):
    """Очистить всю базу знаний"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    brain.rag.clear()
    return {"ok": True}


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 3


@app.post("/api/bots/{bot_id}/knowledge/search")
def api_search_knowledge(bot_id: str, req: SearchRequest):
    """Поиск по базе знаний"""
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    results = brain.rag.search(req.query, req.top_k)
    return {"results": results}


# ====================================================
# API — МОДЕЛИ
# ====================================================

@app.get("/api/models")
def api_get_models():
    return get_models()


# ====================================================
# СТАТИКА — ПАНЕЛЬ УПРАВЛЕНИЯ
# ====================================================

web_dir = ROOT_DIR / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/")
def serve_panel():
    index = web_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Bot Factory API running. Put index.html in web/ folder."}


@app.get("/chat/{bot_id}")
def serve_chat(bot_id: str):
    chat_page = web_dir / "chat.html"
    if chat_page.exists():
        return FileResponse(str(chat_page))
    return {"message": "chat.html not found in web/ folder"}


# ====================================================
# ЗАПУСК
# ====================================================

def open_browser():
    time.sleep(2)
    webbrowser.open("http://localhost:8000")


@app.on_event("startup")
async def on_startup():
    logger.info("🚀 Bot Factory starting...")
    engine.start_all()
    logger.info("✅ Bot Factory ready")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down...")
    engine.stop_all()


if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  🤖 Bot Factory v1.0")
    print("  📍 http://localhost:8000")
    print("  ⛔ Ctrl+C чтобы остановить")
    print("=" * 50)
    print()

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")