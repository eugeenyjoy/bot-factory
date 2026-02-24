"""
Конфигурация — загрузка/сохранение настроек ботов
Каждый бот хранит свои настройки в bots/bot_xxx/config.json
"""

import json
from pathlib import Path


# корневая папка проекта
ROOT_DIR = Path(__file__).parent.parent

# папка где живут все боты
BOTS_DIR = ROOT_DIR / "bots"


# дефолтные настройки нового бота
DEFAULT_CONFIG = {
    "bot_id": "",
    "name": "Новый бот",
    "bot_token": "",               # пустой = без Telegram
    "api_key": "",
    "model": "mistralai/mistral-nemo",
    "system_prompt": "Ты — полезный AI ассистент.",
    "max_history": 20,
    "free_messages": 20,
    "stars_price": 50,
    "messages_per_purchase": 50,
    "is_running": False,
    "enable_telegram": False,       # ← НОВОЕ
    "enable_groups": False,
    "vip_users": [],
     # RAG настройки
    "rag_chunk_size": 500,       # размер чанка (символов)
    "rag_chunk_overlap": 50,     # перекрытие чанков
    "rag_top_k": 3,              # сколько чанков искать
}

# доступные модели для выбора в панели
AVAILABLE_MODELS = [
    {"id": "mistralai/mistral-nemo", "name": "Mistral Nemo", "price": "$0.13/1M", "censored": False},
    {"id": "nousresearch/hermes-3-llama-3.1-405b", "name": "Hermes 405B", "price": "$0.90/1M", "censored": False},
    {"id": "nousresearch/hermes-3-llama-3.1-70b", "name": "Hermes 70B", "price": "$0.40/1M", "censored": False},
    {"id": "meta-llama/llama-3.1-8b-instruct", "name": "Llama 3.1 8B", "price": "$0.05/1M", "censored": False},
    {"id": "mistralai/mixtral-8x7b-instruct", "name": "Mixtral 8x7B", "price": "$0.24/1M", "censored": False},
    {"id": "google/gemini-2.0-flash-lite-001", "name": "Gemini Flash Lite", "price": "$0.075/1M", "censored": True},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "price": "$0.15/1M", "censored": True},
    {"id": "anthropic/claude-3.5-haiku", "name": "Claude 3.5 Haiku", "price": "$0.25/1M", "censored": True},
]


def list_bots() -> list:
    """Список всех ботов (читает папки в bots/)"""
    BOTS_DIR.mkdir(parents=True, exist_ok=True)
    bots = []
    for bot_dir in sorted(BOTS_DIR.iterdir()):
        if bot_dir.is_dir() and bot_dir.name.startswith("bot_"):
            config = load_config(bot_dir.name.replace("bot_", ""))
            if config:
                bots.append(config)
    return bots


def load_config(bot_id: str) -> dict:
    """Загружает конфиг бота из JSON"""
    config_path = BOTS_DIR / f"bot_{bot_id}" / "config.json"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        # добавляем недостающие поля из дефолта
        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = value
        return config
    except Exception:
        return None


def save_config(bot_id: str, config: dict):
    """Сохраняет конфиг бота в JSON"""
    bot_dir = BOTS_DIR / f"bot_{bot_id}"
    bot_dir.mkdir(parents=True, exist_ok=True)
    config_path = bot_dir / "config.json"
    config["bot_id"] = bot_id
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def create_bot(name: str, bot_token: str, api_key: str, model: str = None,
               system_prompt: str = None) -> dict:
    """Создаёт нового бота"""
    # ID из токена или из имени
    if bot_token and ":" in bot_token:
        bot_id = bot_token.split(":")[0]
    else:
        import hashlib
        bot_id = hashlib.md5(name.encode()).hexdigest()[:10]

    config = DEFAULT_CONFIG.copy()
    config["bot_id"] = bot_id
    config["name"] = name
    config["bot_token"] = bot_token or ""
    config["api_key"] = api_key

    if model:
        config["model"] = model
    if system_prompt:
        config["system_prompt"] = system_prompt

    save_config(bot_id, config)
    return config


def delete_bot(bot_id: str):
    """Удаляет бота и все его данные"""
    import shutil
    bot_dir = BOTS_DIR / f"bot_{bot_id}"
    if bot_dir.exists():
        shutil.rmtree(bot_dir)


def update_bot(bot_id: str, updates: dict) -> dict:
    """Обновляет настройки бота (частично)"""
    config = load_config(bot_id)
    if not config:
        return None

    # обновляем только переданные поля
    for key, value in updates.items():
        if key in DEFAULT_CONFIG:
            config[key] = value

    save_config(bot_id, config)
    return config


def get_models() -> list:
    """Возвращает список доступных моделей"""
    return AVAILABLE_MODELS