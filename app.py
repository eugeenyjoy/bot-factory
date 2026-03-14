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
    update_bot, get_models, get_providers, BOTS_DIR
)

# логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# корневая папка
ROOT_DIR = Path(__file__).parent

# FastAPI приложение
app = FastAPI(title="Bot Factory", version="2.0")

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
    provider: Optional[str] = "openrouter"
    custom_base_url: Optional[str] = ""


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
    enable_web_chat: Optional[bool] = None
    provider: Optional[str] = None
    custom_base_url: Optional[str] = None
    tools_enabled: Optional[bool] = None
    tool_permissions: Optional[dict] = None
    allowed_paths: Optional[list] = None
    blocked_paths: Optional[list] = None


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
        system_prompt=req.system_prompt,
        provider=req.provider,
        custom_base_url=req.custom_base_url
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
    updates = {}
    for k, v in req.dict().items():
        if v is not None:
            updates[k] = v
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
    success = engine.activate_bot(bot_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to activate bot")
    return {"ok": True}


@app.post("/api/bots/{bot_id}/stop")
def api_stop_bot(bot_id: str):
    engine.deactivate_bot(bot_id)
    return {"ok": True}


@app.post("/api/bots/{bot_id}/restart")
def api_restart_bot(bot_id: str):
    engine.deactivate_bot(bot_id)
    time.sleep(1)
    engine.activate_bot(bot_id)
    return {"ok": True}


# ====================================================
# API — TELEGRAM (опционально)
# ====================================================

@app.post("/api/bots/{bot_id}/telegram/start")
def api_start_telegram(bot_id: str):
    success = engine.start_telegram(bot_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed. Check bot token.")
    return {"ok": True}


@app.post("/api/bots/{bot_id}/telegram/stop")
def api_stop_telegram(bot_id: str):
    engine.stop_telegram(bot_id)
    return {"ok": True}


# ====================================================
# API — ВЕБ ЧАТ
# ====================================================

@app.post("/api/bots/{bot_id}/chat")
def api_web_chat(bot_id: str, req: ChatRequest):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active. Click Start first.")

    result = brain.chat(
        chat_id=req.user_id,
        user_id=req.user_id,
        message=req.message
    )

    if not result["ok"] and result.get("error") == "limit":
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
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    return brain.memory.get_history_with_index(chat_id)


@app.delete("/api/bots/{bot_id}/messages/{msg_id}")
def api_delete_one_message(bot_id: str, msg_id: int):
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
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    return brain.rag.get_info()


class UploadFileRequest(BaseModel):
    filename: str
    content_base64: str
    source: Optional[str] = "admin"  # "admin" или "user"


@app.post("/api/bots/{bot_id}/knowledge/file")
def api_upload_file(bot_id: str, req: UploadFileRequest):
    """Единый эндпоинт загрузки файлов — панель и чат"""
    import base64
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")

    # проверяем права для юзеров
    if req.source == "user":
        perms = brain.permissions
        if not perms.get("user_can_add_knowledge", False):
            return {"ok": False, "error": "Загрузка знаний отключена администратором"}

    try:
        raw = base64.b64decode(req.content_base64)
    except Exception:
        return {"ok": False, "error": "Ошибка декодирования"}

    filename = req.filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
    text = ""

    # текстовые форматы
    text_exts = {'txt', 'md', 'csv', 'json', 'html', 'xml', 'yml', 'yaml',
                 'py', 'js', 'ts', 'css', 'log', 'ini', 'cfg', 'toml',
                 'c', 'cpp', 'h', 'java', 'go', 'rs', 'rb', 'php', 'sh'}

    if ext in text_exts:
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = raw.decode('cp1251')
            except:
                return {"ok": False, "error": "Не удалось прочитать файл"}

    elif ext == 'pdf':
        try:
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
        except ImportError:
            return {"ok": False, "error": "PDF не поддерживается (pip install PyMuPDF)"}
        except Exception as e:
            return {"ok": False, "error": f"Ошибка PDF: {e}"}

    elif ext in ('doc', 'docx'):
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(raw))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            return {"ok": False, "error": "DOCX не поддерживается (pip install python-docx)"}
        except Exception as e:
            return {"ok": False, "error": f"Ошибка DOCX: {e}"}
    else:
        try:
            text = raw.decode('utf-8')
        except:
            return {"ok": False, "error": f"Формат .{ext} не поддерживается"}

    if not text.strip():
        return {"ok": False, "error": "Файл пустой"}

    # добавляем source в имя для разделения
    source_prefix = "📋" if req.source == "admin" else "👤"
    display_name = f"{source_prefix} {filename}"

    try:
        result = brain.rag.add_text(display_name, text)
        if isinstance(result, dict):
            result["source"] = req.source
            return result
        return {"ok": True, "filename": display_name, "chunks": result, "size": len(text), "source": req.source}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class AddTextRequest(BaseModel):
    name: str
    text: str
    source: Optional[str] = "admin"


@app.post("/api/bots/{bot_id}/knowledge/text")
def api_add_text(bot_id: str, req: AddTextRequest):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")

    if req.source == "user":
        perms = brain.permissions
        if not perms.get("user_can_add_knowledge", False):
            return {"ok": False, "error": "Загрузка знаний отключена"}

    source_prefix = "📋" if req.source == "admin" else "👤"
    display_name = f"{source_prefix} {req.name}"

    result = brain.rag.add_text(display_name, req.text)
    if isinstance(result, dict):
        return result
    return {"ok": True, "chunks": result}


@app.delete("/api/bots/{bot_id}/knowledge/{filename:path}")
def api_delete_knowledge_file(bot_id: str, filename: str):
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    brain.rag.remove_file(filename)
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/knowledge")
def api_clear_knowledge(bot_id: str):
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
    brain = engine.get_brain(bot_id)
    if not brain:
        raise HTTPException(status_code=400, detail="Bot not active")
    results = brain.rag.search(req.query, req.top_k)
    return {"results": results}
    
# ====================================================
# API — МОДЕЛИ И ПРОВАЙДЕРЫ
# ====================================================

@app.get("/api/models")
def api_get_models():
    return get_models()


@app.get("/api/providers")
def api_get_providers():
    return get_providers()

# ====================================================
# API — ФАЙЛОВЫЙ МЕНЕДЖЕР
# ====================================================

from fastapi import Query
import os

ALLOWED_EXTENSIONS = {'.txt', '.md', '.json', '.py', '.csv', '.html', '.yml', '.yaml', '.cfg', '.ini', '.log'}

@app.get("/api/bots/{bot_id}/files")
def api_list_files(bot_id: str, path: str = ""):
    """Список файлов и папок бота"""
    bot_dir = BOTS_DIR / f"bot_{bot_id}"
    if not bot_dir.exists():
        raise HTTPException(status_code=404, detail="Bot not found")

    target = bot_dir / path
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    # защита от выхода за пределы папки бота
    try:
        target.resolve().relative_to(bot_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if target.is_file():
        # возвращаем содержимое файла
        ext = target.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return {"type": "binary", "name": target.name, "size": target.stat().st_size}
        try:
            content = target.read_text(encoding='utf-8')
            return {"type": "file", "name": target.name, "content": content, "size": len(content)}
        except Exception:
            return {"type": "binary", "name": target.name, "size": target.stat().st_size}

    # список файлов в папке
    items = []
    for item in sorted(target.iterdir()):
        rel = item.relative_to(bot_dir)
        if item.is_dir():
            items.append({
                "name": item.name,
                "type": "dir",
                "path": str(rel),
            })
        else:
            items.append({
                "name": item.name,
                "type": "file",
                "path": str(rel),
                "size": item.stat().st_size,
                "ext": item.suffix.lower(),
            })

    return {"type": "dir", "path": path, "items": items}


class FileWriteRequest(BaseModel):
    path: str
    content: str


@app.put("/api/bots/{bot_id}/files")
def api_write_file(bot_id: str, req: FileWriteRequest):
    """Записать/создать файл"""
    bot_dir = BOTS_DIR / f"bot_{bot_id}"
    if not bot_dir.exists():
        raise HTTPException(status_code=404, detail="Bot not found")

    target = bot_dir / req.path

    # защита
    try:
        target.resolve().relative_to(bot_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    # не даём редактировать бинарники
    ext = target.suffix.lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Cannot edit {ext} files")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding='utf-8')
    return {"ok": True, "size": len(req.content)}


class FileDeleteRequest(BaseModel):
    path: str


@app.delete("/api/bots/{bot_id}/files")
def api_delete_file(bot_id: str, req: FileDeleteRequest):
    """Удалить файл"""
    bot_dir = BOTS_DIR / f"bot_{bot_id}"
    target = bot_dir / req.path

    try:
        target.resolve().relative_to(bot_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if target.is_dir():
        import shutil
        shutil.rmtree(target)
    else:
        target.unlink()

    return {"ok": True}


# ====================================================
# API — СИСТЕМНЫЕ ФАЙЛЫ ПРОЕКТА (только чтение)
# ====================================================

@app.get("/api/system/files")
def api_system_files(path: str = ""):
    """Просмотр файлов проекта (read-only)"""
    target = ROOT_DIR / path

    try:
        target.resolve().relative_to(ROOT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    # скрываем чувствительные папки
    hidden = {'venv', '__pycache__', '.git', 'node_modules', '.env'}

    if target.is_file():
        ext = target.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS and ext not in {'.py', '.js', '.css', '.html', '.sh', '.bat'}:
            return {"type": "binary", "name": target.name, "size": target.stat().st_size}
        try:
            content = target.read_text(encoding='utf-8')
            return {"type": "file", "name": target.name, "content": content, "size": len(content), "readonly": True}
        except Exception:
            return {"type": "binary", "name": target.name, "size": target.stat().st_size}

    items = []
    for item in sorted(target.iterdir()):
        if item.name in hidden or item.name.startswith('.'):
            continue
        rel = item.relative_to(ROOT_DIR)
        if item.is_dir():
            items.append({"name": item.name, "type": "dir", "path": str(rel)})
        else:
            items.append({
                "name": item.name, "type": "file",
                "path": str(rel), "size": item.stat().st_size,
                "ext": item.suffix.lower()
            })

    return {"type": "dir", "path": path, "items": items}
    
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
    logger.info("🚀 Bot Factory v2.0 starting...")
    engine.start_all()
    logger.info("✅ Bot Factory ready")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down...")
    engine.stop_all()


if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  🤖 Bot Factory v2.0")
    print("  📍 http://localhost:8000")
    print("  ⛔ Ctrl+C чтобы остановить")
    print("=" * 50)
    print()

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")