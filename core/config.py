"""
Конфигурация — загрузка/сохранение настроек ботов
Каждый бот хранит свои настройки в bots/bot_xxx/config.json
Модели фетчатся с OpenRouter API автоматически
"""

import json
import time
import logging
import os
import requests
from pathlib import Path

logger = logging.getLogger("config")

# корневая папка проекта
ROOT_DIR = Path(__file__).parent.parent

# папка где живут все боты
BOTS_DIR = ROOT_DIR / "bots"


# ============================================================
#  ПРОВАЙДЕРЫ AI — разные API endpoint'ы
# ============================================================

AI_PROVIDERS = {
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models_url": "https://openrouter.ai/api/v1/models",
        "key_prefix": "sk-or-",
        "description": "Универсальный. Доступ ко всем моделям через один ключ.",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models_url": "https://api.openai.com/v1/models",
        "key_prefix": "sk-",
        "description": "Прямой доступ к GPT-4, o4-mini и др.",
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "models_url": None,
        "key_prefix": "sk-ant-",
        "description": "Прямой доступ к Claude Sonnet, Haiku.",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models_url": None,
        "key_prefix": "",
        "description": "Прямой доступ к DeepSeek V3, R1.",
    },
    "xai": {
        "name": "xAI (Grok)",
        "base_url": "https://api.x.ai/v1",
        "models_url": None,
        "key_prefix": "xai-",
        "description": "Прямой доступ к Grok 4, Grok 3.",
    },
    "google": {
        "name": "Google AI Studio",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models_url": None,
        "key_prefix": "AI",
        "description": "Прямой доступ к Gemini. ⚠️ Нужен VPN из РФ.",
    },
    "custom": {
        "name": "Свой API (OpenAI-совместимый)",
        "base_url": "",
        "models_url": None,
        "key_prefix": "",
        "description": "Любой OpenAI-совместимый API. Укажите base_url.",
    },
    "local": {
        "base_url": "http://localhost:11434/v1",
        "name": "Local (Ollama)"
    },
}


# ============================================================
#  ДЕФОЛТНЫЙ КОНФИГ БОТА
# ============================================================

DEFAULT_CONFIG = {
    "bot_id": "",
    "name": "Новый бот",
    "bot_token": "",
    "api_key": "",
    "provider": "openrouter",
    "custom_base_url": "",
    "model": "mistralai/mistral-nemo",
    "system_prompt": "Ты — полезный AI ассистент.",
    "max_history": 20,
    "free_messages": 20,
    "stars_price": 50,
    "messages_per_purchase": 50,
    "purchase_options": [
        {"messages": 50, "stars": 50}
    ],
    "is_running": False,
    "enable_telegram": False,
    "enable_groups": False,
    "enable_web_chat": False,
    "vip_users": [],
    # RAG
    "rag_chunk_size": 500,
    "rag_chunk_overlap": 50,
    "rag_top_k": 3,
    # TOOLS — инструменты агента
    "tools_enabled": True,
    "tool_permissions": {
        "execute_commands": True,
        "write_files": True,
        "delete_files": False,
        "network": False,
        "install_packages": False,
        # пользовательские права
        "user_can_add_prompt": False,    # юзер может добавлять системный промпт
        "user_can_add_knowledge": False, # юзер может загружать знания
        "user_can_clear_history": True,  # юзер может очищать свою историю
    },
    "access_mode": "sandbox",       # sandbox | full | project | custom
    "working_directory": "",         # кастомная рабочая папка (для full/custom)
    "allowed_paths": [],
    "blocked_paths": [],
    "max_tool_rounds": 15,
}


# ============================================================
#  АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ КАТЕГОРИЙ
#  Ключевые слова в названии/id модели → категория
# ============================================================

CATEGORY_RULES = {
    "reasoning": {
        "keywords": ["o1", "o3", "o4", "r1", "r1-", "reason", "think", "qwq"],
        "label": "🧮 Логика / Математика / Reasoning",
    },
    "code": {
        "keywords": ["code", "codex", "coder", "starcoder", "codestral", "devstral"],
        "label": "💻 Код / Программирование",
    },
    "creative": {
        "keywords": ["roleplay", "rp", "creative", "story", "hermes", "mytho",
                      "rocinante", "lumimaid", "noromaid", "psyfighter",
                      "fimbulvetr", "midnight", "nemotron"],
        "label": "🎭 Ролеплей / Креатив / Истории",
    },
    "uncensored": {
        "keywords": ["dolphin", "abliterated", "uncensored"],
        "label": "🔥 Без цензуры (ZERO)",
    },
    "analytics": {
        "keywords": ["gemini", "search", "online"],
        "label": "📊 Аналитика / Документы / RAG",
    },
}

# модели которые точно без цензуры
UNCENSORED_IDS = {
    "x-ai/", "grok",
    "nousresearch/hermes",
    "deepseek/",
    "mistralai/mistral-nemo", "mistralai/mistral-small",
    "mistralai/mistral-large", "mistralai/mixtral",
    "meta-llama/",
    "thedrummer/", "eva-unit",
    "cognitivecomputations/dolphin",
}

# модели которые точно С цензурой
CENSORED_IDS = {
    "openai/gpt", "openai/o1", "openai/o3", "openai/o4",
    "anthropic/claude",
    "google/gemini", "google/gemma",
    "qwen/",
}


# ============================================================
#  КЭШ МОДЕЛЕЙ — обновляется раз в час
# ============================================================

_models_cache = {
    "data": [],
    "timestamp": 0,
    "ttl": 3600,  # 1 час
}


def fetch_models_from_openrouter() -> list:
    """Фетчит модели с OpenRouter API и парсит в наш формат"""

    now = time.time()

    # возвращаем из кэша если свежий
    if _models_cache["data"] and (now - _models_cache["timestamp"]) < _models_cache["ttl"]:
        return _models_cache["data"]

    try:
        logger.info("Fetching models from OpenRouter...")
        resp = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Accept": "application/json"},
            timeout=15
        )
        resp.raise_for_status()
        raw_models = resp.json().get("data", [])
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        # если кэш есть — возвращаем старый
        if _models_cache["data"]:
            return _models_cache["data"]
        # иначе возвращаем хардкод-минимум
        return _get_fallback_models()

    parsed = []

    for m in raw_models:
        model_id = m.get("id", "")
        name = m.get("name", model_id)

        # пропускаем устаревшие и тестовые
        if any(skip in model_id for skip in [":beta", ":extended", "/auto", "openrouter/"]):
            continue

        # цена
        prompt_price = float(m.get("pricing", {}).get("prompt", 0)) * 1_000_000
        completion_price = float(m.get("pricing", {}).get("completion", 0)) * 1_000_000
        is_free = (prompt_price == 0 and completion_price == 0)

        if is_free:
            price_str = "FREE"
        else:
            price_str = f"${prompt_price:.2f}→${completion_price:.2f}"

        # контекст
        context = m.get("context_length", 0)

        # определяем цензуру
        censored = _detect_censorship(model_id, name)

        # определяем категорию
        category = _detect_category(model_id, name)

        # рейтинг на основе цены и контекста
        rating = _calc_rating(prompt_price, completion_price, context, model_id)

        # метка цензуры в имени
        if not censored:
            censor_tag = " 🔓"
        else:
            censor_tag = ""

        if is_free:
            free_tag = " (FREE)"
        else:
            free_tag = ""

        # описание
        desc_parts = []
        if context >= 1_000_000:
            desc_parts.append(f"Контекст {context // 1_000_000}M токенов")
        elif context >= 100_000:
            desc_parts.append(f"Контекст {context // 1000}K")

        if not censored:
            desc_parts.append("Без цензуры")
        if is_free:
            desc_parts.append("Бесплатная")

        description = ". ".join(desc_parts) if desc_parts else ""

        parsed.append({
            "id": model_id,
            "name": f"{name}{censor_tag}{free_tag}",
            "price": price_str,
            "censored": censored,
            "category": category,
            "rating": rating,
            "description": description,
            "context_length": context,
            "is_free": is_free,
            "prompt_price": prompt_price,
            "completion_price": completion_price,
        })

    # сортируем: сначала дешёвые, потом дорогие
    parsed.sort(key=lambda x: (x["category"], -x["rating"], x["prompt_price"]))

    # обновляем кэш
    _models_cache["data"] = parsed
    _models_cache["timestamp"] = now

    logger.info(f"Loaded {len(parsed)} models from OpenRouter")
    return parsed


def _detect_censorship(model_id: str, name: str) -> bool:
    """True = цензура есть, False = без цензуры"""
    mid = model_id.lower()
    nlow = name.lower()

    # точно без цензуры
    for pattern in UNCENSORED_IDS:
        if pattern in mid:
            return False

    # точно с цензурой
    for pattern in CENSORED_IDS:
        if pattern in mid:
            return True

    # ключевые слова
    uncensored_words = ["uncensored", "abliterated", "dolphin", "hermes",
                        "roleplay", "nsfw", "unfiltered"]
    for word in uncensored_words:
        if word in mid or word in nlow:
            return False

    # по умолчанию — цензура есть
    return True


def _detect_category(model_id: str, name: str) -> str:
    """Определяет категорию модели по ключевым словам"""
    mid = model_id.lower()
    nlow = name.lower()
    combined = f"{mid} {nlow}"

    for cat_key, cat_info in CATEGORY_RULES.items():
        for keyword in cat_info["keywords"]:
            if keyword in combined:
                return cat_key

    # по умолчанию — собеседник
    return "psychology"


def _calc_rating(prompt_price: float, completion_price: float,
                 context: int, model_id: str) -> int:
    """Рейтинг 1-10 на основе цены и возможностей"""

    # топовые модели
    top_models = ["claude-sonnet-4", "gpt-4.1", "gpt-4o", "grok-4",
                  "deepseek-r1", "deepseek-chat-v3", "hermes-3-llama-3.1-405b"]
    for top in top_models:
        if top in model_id:
            return 10

    # хорошие модели
    good_models = ["claude-3.5-haiku", "grok-3", "grok-4.1-fast",
                   "mistral-large", "qwen3-32b", "llama-3.3-70b",
                   "hermes-3-llama-3.1-70b", "gemini-2.5"]
    for good in good_models:
        if good in model_id:
            return 8

    total_price = prompt_price + completion_price

    if total_price == 0:
        return 5  # бесплатные — средний рейтинг
    elif total_price < 0.5:
        return 7  # дешёвые
    elif total_price < 2:
        return 6
    elif total_price < 10:
        return 8
    else:
        return 9  # дорогие обычно лучше

    return 5


# категории для отображения в панели
MODEL_CATEGORIES = {
    "uncensored": "🔥 Без цензуры",
    "psychology": "💬 Собеседник / Универсальная",
    "code":       "💻 Код / Программирование",
    "creative":   "🎭 Ролеплей / Креатив / Истории",
    "analytics":  "📊 Аналитика / Документы / RAG",
    "reasoning":  "🧮 Логика / Математика / Reasoning",
}


def _get_fallback_models() -> list:
    """Хардкод моделей на случай если OpenRouter недоступен"""
    return [
        {"id": "mistralai/mistral-nemo", "name": "Mistral Nemo 🔓",
         "price": "$0.03→$0.03", "censored": False, "category": "psychology",
         "rating": 7, "description": "Дешёвая, без цензуры.", "is_free": False,
         "context_length": 128000, "prompt_price": 0.03, "completion_price": 0.03},
        {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B 🔓 (FREE)",
         "price": "FREE", "censored": False, "category": "psychology",
         "rating": 5, "description": "Бесплатная, без цензуры.", "is_free": True,
         "context_length": 131072, "prompt_price": 0, "completion_price": 0},
        {"id": "qwen/qwen3-8b:free", "name": "Qwen 3 8B (FREE)",
         "price": "FREE", "censored": True, "category": "psychology",
         "rating": 4, "description": "Бесплатная.", "is_free": True,
         "context_length": 32768, "prompt_price": 0, "completion_price": 0},
    ]


def get_models() -> list:
    """Возвращает список моделей — автоматически с OpenRouter"""
    return fetch_models_from_openrouter()


def get_providers() -> dict:
    """Возвращает список провайдеров"""
    return AI_PROVIDERS


# ============================================================
#  УПРАВЛЕНИЕ БОТАМИ
# ============================================================

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
    # На Unix ограничиваем доступ только владельцем (секреты: api_key, bot_token)
    if os.name != "nt":
        try:
            os.chmod(bot_dir, 0o700)
            os.chmod(config_path, 0o600)
        except OSError:
            pass


def create_bot(name: str, bot_token: str, api_key: str, model: str = None,
               system_prompt: str = None, provider: str = "openrouter",
               custom_base_url: str = "") -> dict:
    """Создаёт нового бота"""
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
    config["provider"] = provider
    config["custom_base_url"] = custom_base_url

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
    config = load_config(bot_id)
    if not config:
        return None

    for key, value in updates.items():
        if key in DEFAULT_CONFIG or key in config:
            config[key] = value

    save_config(bot_id, config)
    return config
