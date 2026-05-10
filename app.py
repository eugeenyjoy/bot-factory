"""
Точка входа — локальный сервер
Запускает панель управления + API + движок ботов
python app.py → открывай localhost:8000
"""

import uvicorn
import webbrowser
import threading
import time
import base64
import shutil
import os
import logging
import aiohttp
import platform
import shutil
import asyncio
import hmac

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, validator
from typing import Optional, List
from pathlib import Path

from engine import Engine
from core import ollama_catalog

from core.config import (
    list_bots, load_config, create_bot, delete_bot,
    update_bot, get_models, get_providers, BOTS_DIR
)

# ====================================================
# ЛОГИРОВАНИЕ
# ====================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("app")

# корневая папка
ROOT_DIR = Path(__file__).parent

# FastAPI
app = FastAPI(title="Bot Factory", version="2.1")


# ====================================================
# БЕЗОПАСНОСТЬ API
# ====================================================

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
ALLOW_REMOTE = os.getenv("BF_ALLOW_REMOTE", "").lower() in {"1", "true", "yes", "on"}
ADMIN_TOKEN = os.getenv("BF_ADMIN_TOKEN", "").strip()
ENABLE_SYSTEM_FILES_API = os.getenv("BF_ENABLE_SYSTEM_FILES_API", "").lower() in {"1", "true", "yes", "on"}


def _is_local_client(request: Request) -> bool:
    client_host = request.client.host if request.client else ""
    return client_host in LOCAL_HOSTS


def _token_valid(request: Request) -> bool:
    if not ADMIN_TOKEN:
        return True
    given = request.headers.get("x-api-token", "")
    return hmac.compare_digest(given, ADMIN_TOKEN)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path

    # Ограничиваем API только локальным доступом (по умолчанию)
    if path.startswith("/api/") and not ALLOW_REMOTE and not _is_local_client(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "Remote API access disabled. Set BF_ALLOW_REMOTE=1 to allow."}
        )

    # Опциональная API-токен защита
    if path.startswith("/api/") and not _token_valid(request):
        return JSONResponse(status_code=401, content={"detail": "Invalid API token"})

    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

# движок
engine = Engine()

# инициализация каталога Ollama
ollama_catalog.init()


# ====================================================
# ХЕЛПЕРЫ
# ====================================================

def get_brain_or_fail(bot_id: str):
    """Получить brain или кинуть 400"""
    brain = engine.get_brain(bot_id)
    if not brain:
        logger.warning(f"Brain not found for bot {bot_id}")
        raise HTTPException(status_code=400, detail="Bot not active. Click Start first.")
    return brain


def decode_file_content(raw: bytes, filename: str) -> str:
    """Декодирует содержимое файла в текст"""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'

    TEXT_EXTS = {
        'txt', 'md', 'csv', 'json', 'html', 'xml', 'yml', 'yaml',
        'py', 'js', 'ts', 'css', 'log', 'ini', 'cfg', 'toml',
        'c', 'cpp', 'h', 'java', 'go', 'rs', 'rb', 'php', 'sh'
    }

    if ext in TEXT_EXTS:
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return raw.decode('cp1251')
            except UnicodeDecodeError as e:
                raise ValueError(f"Не удалось декодировать: {e}")

    elif ext == 'pdf':
        try:
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        except ImportError:
            raise ValueError("PDF не поддерживается (pip install PyMuPDF)")
        except Exception as e:
            raise ValueError(f"Ошибка PDF: {e}")

    elif ext in ('doc', 'docx'):
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise ValueError("DOCX не поддерживается (pip install python-docx)")
        except Exception as e:
            raise ValueError(f"Ошибка DOCX: {e}")

    else:
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError(f"Формат .{ext} не поддерживается")


def safe_resolve_path(base: Path, user_path: str) -> Path:
    """Безопасное разрешение пути — защита от path traversal"""
    target = (base / user_path).resolve()
    base_resolved = base.resolve()
    if not str(target).startswith(str(base_resolved)):
        raise HTTPException(status_code=403, detail="Access denied")
    return target


# ====================================================
# МОДЕЛИ ЗАПРОСОВ с валидацией
# ====================================================

class CreateBotRequest(BaseModel):
    name: str
    bot_token: Optional[str] = ""
    api_key: str
    model: Optional[str] = "mistralai/mistral-nemo"
    system_prompt: Optional[str] = "Ты — полезный AI ассистент."
    provider: Optional[str] = "openrouter"
    custom_base_url: Optional[str] = ""

    @validator('name')
    def name_not_empty(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Name cannot be empty')
        if len(v) > 100:
            raise ValueError('Name too long (max 100)')
        return v

    @validator('api_key')
    def api_key_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('API key cannot be empty')
        return v.strip()
    
    @validator('model')
    def model_valid(cls, v):
        if not v or not v.strip():
            raise ValueError('Model cannot be empty')
        if len(v) > 200:
            raise ValueError('Model name too long')
        # Проверяем формат: должен быть либо "provider/model" либо простое имя
        if not all(c.isalnum() or c in '/-_.' for c in v):
            raise ValueError('Invalid model name format')
        return v.strip()
    
    @validator('system_prompt')
    def prompt_valid(cls, v):
        if v and len(v) > 5000:
            raise ValueError('System prompt too long (max 5000 chars)')
        return v
    
    @validator('provider')
    def provider_valid(cls, v):
        valid = {'openrouter', 'ollama', 'custom'}
        if v not in valid:
            raise ValueError(f'Provider must be one of: {valid}')
        return v


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
    purchase_options: Optional[list] = None
    enable_telegram: Optional[bool] = None
    enable_groups: Optional[bool] = None
    enable_web_chat: Optional[bool] = None
    provider: Optional[str] = None
    custom_base_url: Optional[str] = None
    tools_enabled: Optional[bool] = None
    tool_permissions: Optional[dict] = None
    vip_features: Optional[dict] = None
    allowed_paths: Optional[list] = None
    blocked_paths: Optional[list] = None

    @validator('max_history')
    def max_history_range(cls, v):
        if v is not None and (v < 1 or v > 200):
            raise ValueError('max_history must be 1-200')
        return v

    @validator('free_messages')
    def free_messages_range(cls, v):
        if v is not None and v < 0:
            raise ValueError('free_messages must be >= 0')
        return v

    @validator('purchase_options')
    def purchase_options_valid(cls, v):
        if v is None:
            return v
        if not isinstance(v, list):
            raise ValueError('purchase_options must be a list')
        if len(v) > 20:
            raise ValueError('purchase_options max 20 items')
        clean = []
        for item in v:
            if not isinstance(item, dict):
                raise ValueError('each purchase option must be an object')
            msgs = int(item.get('messages', 0))
            stars = int(item.get('stars', 0))
            if msgs <= 0 or stars <= 0:
                raise ValueError('messages and stars must be > 0')
            clean.append({'messages': msgs, 'stars': stars})
        return clean

    @validator('vip_features')
    def vip_features_valid(cls, v):
        if v is None:
            return v
        if not isinstance(v, dict):
            raise ValueError('vip_features must be an object')
        allowed = {"unlimited_messages", "can_add_prompt", "can_add_knowledge", "can_clear_history"}
        for key, value in v.items():
            if key not in allowed:
                raise ValueError(f'Unknown vip feature: {key}')
            if not isinstance(value, bool):
                raise ValueError(f'vip feature "{key}" must be boolean')
        return v


class VipRequest(BaseModel):
    user_id: int
    is_vip: bool

    @validator('user_id')
    def user_id_positive(cls, v):
        if v < 0:
            raise ValueError('user_id must be >= 0')
        return v


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[int] = 0

    @validator('message')
    def message_valid(cls, v):
        if not v or not v.strip():
            raise ValueError('Message cannot be empty')
        if len(v) > 15000:
            raise ValueError('Message too long (max 15000 chars)')
        return v.strip()

    @validator('user_id')
    def user_id_valid(cls, v):
        if v < 0:
            raise ValueError('user_id must be >= 0')
        return v


class UploadFileRequest(BaseModel):
    filename: str
    content_base64: str
    source: Optional[str] = "admin"

    @validator('filename')
    def filename_valid(cls, v):
        if not v or not v.strip():
            raise ValueError('Filename cannot be empty')
        if len(v) > 255:
            raise ValueError('Filename too long')
        # защита от path traversal
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError('Invalid filename')
        return v.strip()

    @validator('content_base64')
    def content_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Content cannot be empty')
        # лимит 20MB в base64
        if len(v) > 20 * 1024 * 1024 * 4 // 3:
            raise ValueError('File too large (max 20MB)')
        return v

    @validator('source')
    def source_valid(cls, v):
        if v not in ('admin', 'user'):
            raise ValueError('Source must be "admin" or "user"')
        return v


class AddTextRequest(BaseModel):
    name: str
    text: str
    source: Optional[str] = "admin"

    @validator('name')
    def name_valid(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()

    @validator('text')
    def text_valid(cls, v):
        if not v or not v.strip():
            raise ValueError('Text cannot be empty')
        if len(v) > 5_000_000:
            raise ValueError('Text too large (max 5MB)')
        return v


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 3

    @validator('query')
    def query_valid(cls, v):
        if not v or not v.strip():
            raise ValueError('Query cannot be empty')
        return v.strip()

    @validator('top_k')
    def top_k_range(cls, v):
        if v is not None and (v < 1 or v > 20):
            raise ValueError('top_k must be 1-20')
        return v


class DeleteMessagesRequest(BaseModel):
    msg_ids: List[int]


class FileWriteRequest(BaseModel):
    path: str
    content: str


class FileDeleteRequest(BaseModel):
    path: str


# ====================================================
# API — БОТЫ
# ====================================================

@app.get("/api/bots")
def api_list_bots():
    return engine.get_all_statuses()


@app.post("/api/bots")
def api_create_bot(req: CreateBotRequest):
    try:
        config = create_bot(
            name=req.name,
            bot_token=req.bot_token,
            api_key=req.api_key,
            model=req.model,
            system_prompt=req.system_prompt,
            provider=req.provider,
            custom_base_url=req.custom_base_url
        )
        logger.info(f"✅ Bot created: {config.get('bot_id')} ({req.name})")
        return {"ok": True, "bot": config}
    except Exception as e:
        logger.error(f"Failed to create bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    logger.info(f"♻️ Bot {bot_id} updated: {list(updates.keys())}")
    return {"ok": True, "config": config}


@app.delete("/api/bots/{bot_id}")
def api_delete_bot(bot_id: str):
    engine.deactivate_bot(bot_id)
    delete_bot(bot_id)
    logger.info(f"🗑️ Bot {bot_id} deleted")
    return {"ok": True}


# ====================================================
# API — УПРАВЛЕНИЕ
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
# API — TELEGRAM
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
    brain = get_brain_or_fail(bot_id)

    logger.debug(f"Chat {bot_id}: user={req.user_id} msg={req.message[:50]}...")

    try:
        result = brain.chat(
            chat_id=req.user_id,
            user_id=req.user_id,
            message=req.message
        )
    except Exception as e:
        logger.error(f"Chat error {bot_id}: {type(e).__name__}: {e}")
        return {"ok": False, "reply": "⚠️ Внутренняя ошибка. Попробуйте ещё раз.", "error": "internal_error"}

    if not result.get("ok") and result.get("error") == "limit":
        result["reply"] = (
            "📭 Лимит сообщений исчерпан!\n\n"
            "Использовано все доступные сообщения.\n"
            "Подключите Telegram чтобы купить ещё (/buy)."
        )

    return result


# ====================================================
# API — ПОЛЬЗОВАТЕЛИ
# ====================================================

@app.get("/api/bots/{bot_id}/users")
def api_get_users(bot_id: str):
    brain = get_brain_or_fail(bot_id)
    return brain.get_users()


@app.post("/api/bots/{bot_id}/vip")
def api_set_vip(bot_id: str, req: VipRequest):
    brain = get_brain_or_fail(bot_id)
    brain.set_vip(req.user_id, req.is_vip)
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/users/{user_id}")
def api_clear_user(bot_id: str, user_id: int):
    brain = get_brain_or_fail(bot_id)
    brain.clear_user(user_id)
    return {"ok": True}


# ====================================================
# API — ПАМЯТЬ
# ====================================================

@app.delete("/api/bots/{bot_id}/history")
def api_clear_all_history(bot_id: str):
    brain = get_brain_or_fail(bot_id)
    brain.memory.clear_all_history()
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/history/{chat_id}")
def api_clear_chat(bot_id: str, chat_id: int):
    brain = get_brain_or_fail(bot_id)
    brain.clear_chat(chat_id)
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/reset")
def api_reset_bot(bot_id: str):
    brain = get_brain_or_fail(bot_id)
    brain.clear_all()
    return {"ok": True}


# ====================================================
# API — ИСТОРИЯ ЧАТА
# ====================================================

@app.get("/api/bots/{bot_id}/history/{chat_id}")
def api_get_history(bot_id: str, chat_id: int):
    brain = get_brain_or_fail(bot_id)
    return brain.memory.get_history_with_index(chat_id)


@app.delete("/api/bots/{bot_id}/messages/{msg_id}")
def api_delete_one_message(bot_id: str, msg_id: int):
    brain = get_brain_or_fail(bot_id)
    success = brain.memory.delete_message_by_id(msg_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}


@app.post("/api/bots/{bot_id}/messages/delete")
def api_delete_messages(bot_id: str, req: DeleteMessagesRequest):
    brain = get_brain_or_fail(bot_id)
    deleted = brain.memory.delete_messages_by_ids(req.msg_ids)
    return {"ok": True, "deleted": deleted}


# ====================================================
# API — СТАТИСТИКА
# ====================================================

@app.get("/api/bots/{bot_id}/stats")
def api_get_stats(bot_id: str):
    brain = get_brain_or_fail(bot_id)
    return brain.get_stats()


@app.get("/api/bots/{bot_id}/payments")
def api_get_payments(bot_id: str):
    brain = get_brain_or_fail(bot_id)
    return brain.memory.get_payments()


# ====================================================
# API — БАЗА ЗНАНИЙ (RAG)
# ====================================================

@app.get("/api/bots/{bot_id}/knowledge")
def api_get_knowledge(bot_id: str):
    brain = get_brain_or_fail(bot_id)
    return brain.rag.get_info()


@app.post("/api/bots/{bot_id}/knowledge/file")
def api_upload_file(bot_id: str, req: UploadFileRequest):
    """Единый эндпоинт загрузки файлов — панель и чат"""
    brain = get_brain_or_fail(bot_id)

    # проверка прав для юзеров
    if req.source == "user":
        if not brain.can_user_feature(None, "add_knowledge"):
            return {"ok": False, "error": "Загрузка знаний отключена администратором"}

    try:
        raw = base64.b64decode(req.content_base64)
    except Exception as e:
        logger.error(f"Base64 decode error: {e}")
        return {"ok": False, "error": "Ошибка декодирования файла"}

    try:
        text = decode_file_content(raw, req.filename)
    except ValueError as e:
        logger.warning(f"File decode failed {req.filename}: {e}")
        return {"ok": False, "error": str(e)}

    if not text.strip():
        return {"ok": False, "error": "Файл пустой"}

    source_prefix = "📋" if req.source == "admin" else "👤"
    display_name = f"{source_prefix} {req.filename}"

    try:
        result = brain.rag.add_text(display_name, text)
        chunks = result if isinstance(result, int) else result.get("chunks", 0)
        logger.info(f"📚 Knowledge added: {display_name} → {chunks} chunks")
        return {"ok": True, "filename": display_name, "chunks": chunks, "size": len(text), "source": req.source}
    except Exception as e:
        logger.error(f"RAG add error: {type(e).__name__}: {e}")
        return {"ok": False, "error": f"Ошибка добавления: {str(e)[:200]}"}


@app.post("/api/bots/{bot_id}/knowledge/text")
def api_add_text(bot_id: str, req: AddTextRequest):
    brain = get_brain_or_fail(bot_id)

    if req.source == "user":
        if not brain.can_user_feature(None, "add_knowledge"):
            return {"ok": False, "error": "Загрузка знаний отключена"}

    source_prefix = "📋" if req.source == "admin" else "👤"
    display_name = f"{source_prefix} {req.name}"

    try:
        result = brain.rag.add_text(display_name, req.text)
        chunks = result if isinstance(result, int) else result.get("chunks", 0)
        return {"ok": True, "chunks": chunks}
    except Exception as e:
        logger.error(f"RAG text add error: {e}")
        return {"ok": False, "error": str(e)}


@app.delete("/api/bots/{bot_id}/knowledge/{filename:path}")
def api_delete_knowledge_file(bot_id: str, filename: str):
    brain = get_brain_or_fail(bot_id)
    brain.rag.remove_file(filename)
    return {"ok": True}


@app.delete("/api/bots/{bot_id}/knowledge")
def api_clear_knowledge(bot_id: str):
    brain = get_brain_or_fail(bot_id)
    brain.rag.clear()
    return {"ok": True}


@app.post("/api/bots/{bot_id}/knowledge/search")
def api_search_knowledge(bot_id: str, req: SearchRequest):
    brain = get_brain_or_fail(bot_id)
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
# ЛОКАЛЬНЫЕ МОДЕЛИ (OLLAMA)
# ====================================================

OLLAMA_BASE = "http://localhost:11434"

# ====================================================
# ====================================================
# КАТАЛОГ OLLAMA — динамический с кешем
# ====================================================

@app.get("/api/local/catalog")
async def local_catalog(q: str = "", limit: int = 50):
    """Поиск моделей в каталоге Ollama"""
    return ollama_catalog.search(q, limit)

@app.get("/api/local/catalog/{model_name}/tags")
async def local_catalog_tags(model_name: str):
    """Все теги конкретной модели"""
    tags = ollama_catalog.get_model_tags(model_name)
    if not tags:
        raise HTTPException(404, f"Model {model_name} not found")
    return {"model": model_name, "tags": tags, "total": len(tags)}

@app.post("/api/local/catalog/refresh")
async def local_catalog_refresh():
    """Принудительное обновление каталога"""
    return ollama_catalog.force_update()



def find_ollama_binary():
    """Find ollama binary path"""
    # 1. shutil.which
    path = shutil.which("ollama")
    if path:
        return path
    # 2. common locations
    for p in ["/usr/local/bin/ollama", "/usr/bin/ollama", os.path.expanduser("~/bin/ollama")]:
        if os.path.isfile(p):
            return p
    return None

@app.get("/api/local/status")
async def local_status():
    """Проверяет доступность Ollama и список моделей"""
    binary = find_ollama_binary()

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3)
        ) as session:
            async with session.get(f"{OLLAMA_BASE}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "available": True,
                        "installed": True,
                        "running": True,
                        "binary": binary,
                        "models": [
                            {
                                "name": m.get("name", ""),
                                "size": m.get("size", 0),
                                "modified": m.get("modified_at", ""),
                            }
                            for m in data.get("models", [])
                        ]
                    }
    except aiohttp.ClientConnectorError:
        logger.warning(f"Ollama connection failed: {OLLAMA_BASE}")
    except asyncio.TimeoutError:
        logger.debug("Ollama status check timeout")
    except Exception as e:
        logger.error(f"Ollama status error: {type(e).__name__}: {e}")

    return {
        "available": False,
        "installed": binary is not None,
        "running": False,
        "binary": binary,
        "models": []
    }


@app.post("/api/local/install")
async def local_install():
    """Устанавливает Ollama через графический запрос пароля"""
    system = platform.system().lower()

    # может уже установлена?
    binary = find_ollama_binary()
    if binary:
        return {"ok": True, "message": f"Ollama уже установлена: {binary}"}

    try:
        if system in ("linux", "darwin"):
            # скачиваем скрипт
            script_path = '/tmp/ollama_install.sh'

            proc_dl = await asyncio.create_subprocess_shell(
                f"curl -fsSL https://ollama.com/install.sh -o {script_path} && chmod +x {script_path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc_dl.communicate(), timeout=60
            )

            if proc_dl.returncode != 0:
                return {"ok": False, "error": f"Не удалось скачать: {stderr.decode()[:300]}"}

            # запускаем через pkexec (графический sudo)
            proc = await asyncio.create_subprocess_exec(
                'pkexec', 'bash', script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=300
            )

            stdout_text = stdout.decode() if stdout else ''
            stderr_text = stderr.decode() if stderr else ''
            print(f"[OLLAMA INSTALL] code: {proc.returncode}")
            print(f"[OLLAMA INSTALL] stdout: {stdout_text[:500]}")
            print(f"[OLLAMA INSTALL] stderr: {stderr_text[:500]}")

            # чистим скрипт
            try:
                os.remove(script_path)
            except Exception:
                pass

            # проверяем
            binary = find_ollama_binary()
            if binary:
                return {"ok": True, "message": f"Ollama установлена: {binary} ✅"}

            if proc.returncode == 126:
                return {"ok": False, "error": "Отменено — вы не ввели пароль"}
            if proc.returncode == 127:
                return {"ok": False, "error": "pkexec не найден. Установите: sudo apt install policykit-1"}

            return {
                "ok": False,
                "error": f"Код {proc.returncode}: {stderr_text[:300]}"
            }

        elif system == "windows":
            proc = await asyncio.create_subprocess_shell(
                'powershell -Command "'
                'Invoke-WebRequest -Uri https://ollama.com/download/OllamaSetup.exe '
                '-OutFile $env:TEMP\\OllamaSetup.exe; '
                'Start-Process $env:TEMP\\OllamaSetup.exe -ArgumentList \'/S\' -Wait -Verb RunAs"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=600
            )
            binary = find_ollama_binary()
            if binary:
                return {"ok": True, "message": "Ollama установлена ✅"}
            return {"ok": False, "error": stderr.decode()[:500]}

        return {"ok": False, "error": f"ОС {system} не поддерживается"}

    except asyncio.TimeoutError:
        return {"ok": False, "error": "Таймаут (5 мин)"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

@app.post("/api/local/start")
async def local_start_ollama():
    """Запускает Ollama как обычный процесс, модели в папке проекта"""

    project_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(project_dir, 'ollama_data', 'models')
    os.makedirs(models_dir, exist_ok=True)

    binary = find_ollama_binary()
    if not binary:
        return {"ok": False, "error": "Ollama не найдена. Установите через панель."}

    # Проверяем — если уже работает, но запущена системным сервисом,
    # останавливаем и перезапускаем с нашим OLLAMA_MODELS
    already_running = False
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3)
        ) as session:
            async with session.get(f"{OLLAMA_BASE}/api/tags") as resp:
                if resp.status == 200:
                    already_running = True
    except Exception:
        pass

    if already_running:
        # Проверяем — наш ли это процесс (по env OLLAMA_MODELS)
        our_process = False
        try:
            for proc_info in __import__('psutil').process_iter(['pid', 'name', 'environ']):
                if 'ollama' in (proc_info.info.get('name') or '').lower():
                    penv = proc_info.info.get('environ') or {}
                    if penv.get('OLLAMA_MODELS') == models_dir:
                        our_process = True
                        break
        except Exception:
            # psutil не установлен — проверяем через /proc
            try:
                import subprocess as _sp
                pids = _sp.check_output(['pgrep', '-f', 'ollama serve'], text=True).strip().split()
                for pid in pids:
                    try:
                        env_data = open(f'/proc/{pid}/environ', 'r').read()
                        if f'OLLAMA_MODELS={models_dir}' in env_data:
                            our_process = True
                            break
                    except Exception:
                        pass
            except Exception:
                pass

        if our_process:
            return {"ok": True, "message": "Ollama уже работает ✅"}
        else:
            # Чужой процесс — останавливаем
            print("[OLLAMA] Обнаружен чужой процесс Ollama, перезапускаем с нашим OLLAMA_MODELS")
            try:
                system = platform.system().lower()
                if system == "windows":
                    await asyncio.create_subprocess_shell('taskkill /F /IM ollama.exe')
                else:
                    # Стоп системный сервис
                    await asyncio.create_subprocess_shell('sudo systemctl stop ollama 2>/dev/null; pkill -f "ollama serve" 2>/dev/null')
                await asyncio.sleep(2)
            except Exception:
                pass

    try:
        env = os.environ.copy()
        env['OLLAMA_HOST'] = '127.0.0.1:11434'
        env['OLLAMA_MODELS'] = models_dir

        proc = await asyncio.create_subprocess_exec(
            binary, 'serve',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            start_new_session=True
        )

        for i in range(20):
            await asyncio.sleep(1)
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as session:
                    async with session.get(f"{OLLAMA_BASE}/api/tags") as resp:
                        if resp.status == 200:
                            return {"ok": True, "message": "Ollama запущена ✅ (модели: ollama_data/)"}
            except Exception:
                continue

        return {"ok": False, "error": f"Ollama не отвечает. Попробуйте: {binary} serve"}

    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/local/stop")
async def local_stop_ollama():
    """Останавливает Ollama"""
    system = platform.system().lower()

    try:
        if system == "windows":
            cmd = 'taskkill /F /IM ollama.exe 2>nul'
        else:
            cmd = 'pkill -f "ollama serve" 2>/dev/null; pkill ollama 2>/dev/null'

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)

        # проверяем что остановилась
        await asyncio.sleep(1)
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=2)
            ) as session:
                async with session.get(f"{OLLAMA_BASE}/api/tags") as resp:
                    if resp.status == 200:
                        return {"ok": False, "error": "Ollama всё ещё работает"}
        except Exception:
            pass

        return {"ok": True, "message": "Ollama остановлена"}

    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/local/pull")
async def local_pull(body: dict):
    """Скачивает модель"""
    model = body.get("model", "")
    if not model:
        raise HTTPException(400, "model required")

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=1800)
        ) as session:
            async with session.post(
                f"{OLLAMA_BASE}/api/pull",
                json={"name": model, "stream": False}
            ) as resp:
                if resp.status == 200:
                    return {"ok": True, "model": model}
                else:
                    error = (await resp.text())[:200]
                    return {"ok": False, "error": error}
    except aiohttp.ClientConnectorError:
        return {"ok": False, "error": "Ollama не запущена. Нажмите 'Запустить'."}
    except TimeoutError:
        return {"ok": False, "error": "Таймаут — модель большая, попробуйте ещё раз"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.delete("/api/local/model")
async def local_delete_model(body: dict):
    """Удаляет одну модель"""
    model = body.get("model", "")
    if not model:
        raise HTTPException(400, "model required")

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            async with session.request(
                'DELETE',
                f"{OLLAMA_BASE}/api/delete",
                json={"name": model}
            ) as resp:
                if resp.status == 200:
                    return {"ok": True}
                else:
                    return {"ok": False, "error": (await resp.text())[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.delete("/api/local/uninstall")
async def local_uninstall():
    """Удаляет Ollama через графический запрос пароля"""
    system = platform.system().lower()

    # останавливаем
    try:
        await local_stop_ollama()
    except Exception:
        pass

    await asyncio.sleep(1)

    if system == "linux":
        # удаляем модели (без sudo)
        ollama_home = os.path.expanduser('~/.ollama')
        if os.path.exists(ollama_home):
            try:
                shutil.rmtree(ollama_home)
            except Exception:
                pass

        # удаляем бинарник через pkexec
        binary = find_ollama_binary()
        if binary:
            try:
                os.remove(binary)
            except PermissionError:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        'pkexec', 'rm', '-f', binary,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await asyncio.wait_for(proc.communicate(), timeout=30)
                except Exception:
                    pass

        # удаляем сервис и пользователя
        try:
            proc = await asyncio.create_subprocess_exec(
                'pkexec', 'bash', '-c',
                'systemctl stop ollama 2>/dev/null; '
                'systemctl disable ollama 2>/dev/null; '
                'rm -f /etc/systemd/system/ollama.service; '
                'rm -rf /usr/share/ollama; '
                'userdel ollama 2>/dev/null; '
                'groupdel ollama 2>/dev/null',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
        except Exception:
            pass

        # проверяем
        binary = find_ollama_binary()
        if not binary:
            return {"ok": True, "message": "Ollama полностью удалена ✅"}
        return {"ok": True, "message": "Модели удалены. Бинарник может остаться."}

    elif system == "darwin":
        for path in [os.path.expanduser('~/.ollama')]:
            if os.path.exists(path):
                shutil.rmtree(path, ignore_errors=True)

        binary = find_ollama_binary()
        if binary:
            try:
                os.remove(binary)
            except PermissionError:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        'pkexec', 'rm', '-f', binary,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await asyncio.wait_for(proc.communicate(), timeout=30)
                except Exception:
                    pass

        return {"ok": True, "message": "Ollama удалена ✅"}

    elif system == "windows":
        for p in [
            os.path.expandvars(r'%LOCALAPPDATA%\Ollama'),
            os.path.expandvars(r'%USERPROFILE%\.ollama'),
        ]:
            if os.path.exists(p):
                shutil.rmtree(p, ignore_errors=True)
        return {"ok": True, "message": "Ollama удалена ✅"}

    return {"ok": False, "error": "Неизвестная ОС"}

# ====================================================
# API — ФАЙЛОВЫЙ МЕНЕДЖЕР
# ====================================================

ALLOWED_EXTENSIONS = {
    '.txt', '.md', '.json', '.py', '.csv', '.html',
    '.yml', '.yaml', '.cfg', '.ini', '.log'
}


@app.get("/api/bots/{bot_id}/files")
def api_list_files(bot_id: str, path: str = ""):
    bot_dir = BOTS_DIR / f"bot_{bot_id}"
    if not bot_dir.exists():
        raise HTTPException(status_code=404, detail="Bot not found")

    target = safe_resolve_path(bot_dir, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if target.is_file():
        ext = target.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return {"type": "binary", "name": target.name, "size": target.stat().st_size}
        try:
            content = target.read_text(encoding='utf-8')
            return {"type": "file", "name": target.name, "content": content, "size": len(content)}
        except (UnicodeDecodeError, OSError) as e:
            logger.warning(f"Cannot read file {target}: {e}")
            return {"type": "binary", "name": target.name, "size": target.stat().st_size}

    items = []
    try:
        for item in sorted(target.iterdir()):
            rel = item.relative_to(bot_dir)
            if item.is_dir():
                items.append({"name": item.name, "type": "dir", "path": str(rel)})
            else:
                items.append({
                    "name": item.name, "type": "file",
                    "path": str(rel), "size": item.stat().st_size,
                    "ext": item.suffix.lower(),
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return {"type": "dir", "path": path, "items": items}


@app.put("/api/bots/{bot_id}/files")
def api_write_file(bot_id: str, req: FileWriteRequest):
    bot_dir = BOTS_DIR / f"bot_{bot_id}"
    if not bot_dir.exists():
        raise HTTPException(status_code=404, detail="Bot not found")

    target = safe_resolve_path(bot_dir, req.path)

    ext = target.suffix.lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Cannot edit {ext} files")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding='utf-8')
    return {"ok": True, "size": len(req.content)}


@app.delete("/api/bots/{bot_id}/files")
def api_delete_file(bot_id: str, req: FileDeleteRequest):
    bot_dir = BOTS_DIR / f"bot_{bot_id}"
    target = safe_resolve_path(bot_dir, req.path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    return {"ok": True}


# ====================================================
# API — СИСТЕМНЫЕ ФАЙЛЫ (read-only)
# ====================================================

HIDDEN_DIRS = {'venv', '__pycache__', '.git', 'node_modules', '.env'}
CODE_EXTENSIONS = {'.py', '.js', '.css', '.html', '.sh', '.bat'}


@app.get("/api/system/files")
def api_system_files(path: str = ""):
    if not ENABLE_SYSTEM_FILES_API:
        raise HTTPException(
            status_code=403,
            detail="System files API is disabled. Set BF_ENABLE_SYSTEM_FILES_API=1 to enable."
        )

    target = safe_resolve_path(ROOT_DIR, path)

    if target.is_file():
        ext = target.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS and ext not in CODE_EXTENSIONS:
            return {"type": "binary", "name": target.name, "size": target.stat().st_size}
        try:
            content = target.read_text(encoding='utf-8')
            return {"type": "file", "name": target.name, "content": content,
                    "size": len(content), "readonly": True}
        except (UnicodeDecodeError, OSError):
            return {"type": "binary", "name": target.name, "size": target.stat().st_size}

    items = []
    try:
        for item in sorted(target.iterdir()):
            if item.name in HIDDEN_DIRS or item.name.startswith('.'):
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
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return {"type": "dir", "path": path, "items": items}


# ====================================================
# СТАТИКА
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
    logger.info("🚀 Bot Factory v2.1 starting...")
    engine.start_all()
    logger.info("✅ Bot Factory ready")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down...")
    engine.stop_all()


if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  🤖 Bot Factory v2.1")
    print("  📍 http://localhost:8000")
    print("  ⛔ Ctrl+C чтобы остановить")
    print("=" * 50)
    print()

    threading.Thread(target=open_browser, daemon=True).start()
    host = os.getenv("BF_HOST", "127.0.0.1")
    port = int(os.getenv("BF_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")

# ─── HuggingFace GGUF поиск ───

@app.get("/api/hf/search")
async def hf_search(q: str = "", limit: int = 20):
    """Ищет GGUF модели на HuggingFace"""
    if not q or len(q) < 2:
        return {"models": []}

    search_q = f"{q} gguf"
    url = (
        f"https://huggingface.co/api/models"
        f"?search={search_q}&filter=gguf"
        f"&sort=downloads&direction=-1&limit={limit}"
    )

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {"models": [], "error": f"HF API: {resp.status}"}
                data = await resp.json()

        results = []
        for m in data:
            model_id = m.get("id", "")
            tags = m.get("tags", [])
            downloads = m.get("downloads", 0)

            # определяем размер по тегам
            size_hint = ""
            for t in tags:
                if "b-" in t.lower() or t.lower().endswith("b"):
                    pass
                if any(x in t.lower() for x in ["1b", "3b", "7b", "8b", "14b", "27b", "35b", "70b"]):
                    for part in t.replace("-", " ").split():
                        if part.lower().endswith("b") and part[:-1].replace(".", "").isdigit():
                            size_hint = part.upper()
                            break

            # размер из имени модели
            if not size_hint:
                import re as _re
                sz = _re.search(r'(\d+\.?\d*)[Bb]', model_id)
                if sz:
                    size_hint = sz.group(0).upper()

            is_uncensored = any(
                x in model_id.lower() or x in " ".join(tags).lower()
                for x in ["abliterate", "uncensor", "lexi", "dolphin"]
            )

            results.append({
                "hf_id": model_id,
                "ollama_id": f"hf.co/{model_id}",
                "name": model_id.split("/")[-1].replace("-GGUF", "").replace("-gguf", ""),
                "downloads": downloads,
                "size_hint": size_hint,
                "uncensored": is_uncensored,
                "tags": [t for t in tags if t in ["chat", "conversational", "abliterated", "uncensored"]],
            })

        return {"models": results}

    except Exception as e:
        return {"models": [], "error": str(e)[:200]}
