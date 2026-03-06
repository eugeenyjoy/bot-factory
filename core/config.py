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
    "bot_token": "",
    "api_key": "",
    "model": "mistralai/mistral-nemo",
    "system_prompt": "Ты — полезный AI ассистент.",
    "max_history": 20,
    "free_messages": 20,
    "stars_price": 50,
    "messages_per_purchase": 50,
    "is_running": False,
    "enable_telegram": False,
    "enable_groups": False,
    "vip_users": [],
    # RAG настройки
    "rag_chunk_size": 500,
    "rag_chunk_overlap": 50,
    "rag_top_k": 3,
}


# ============================================================
#  КАТАЛОГ МОДЕЛЕЙ OpenRouter — июль 2025
#
#  Уровни цензуры:
#    ✦ ZERO   = абсолютный ноль, отвечает на ВСЁ без предупреждений
#    🔓 НЕТ   = без цензуры, иногда мягкие оговорки
#    🔒 ДА    = есть отказы на опасные темы
#
#  Цена: вход→выход за 1M токенов
#  Рейтинг 1-10 внутри категории
# ============================================================

AVAILABLE_MODELS = [

    # ══════════════════════════════════════════
    #  💬 СОБЕСЕДНИК / ПСИХОЛОГИЯ / САМОАНАЛИЗ
    # ══════════════════════════════════════════

    {
        "id": "anthropic/claude-sonnet-4",
        "name": "Claude Sonnet 4 🔒",
        "price": "$3→$15",
        "censored": True,
        "category": "psychology",
        "rating": 10,
        "description": "Лучший для эмпатии и глубоких бесед. Дорогой.",
    },
    {
        "id": "openai/gpt-4o",
        "name": "GPT-4o 🔒",
        "price": "$2.50→$10",
        "censored": True,
        "category": "psychology",
        "rating": 9,
        "description": "Умный собеседник, хорошо понимает контекст.",
    },
    {
        "id": "x-ai/grok-3-fast",
        "name": "Grok 3 Fast 🔓",
        "price": "$0.30→$1.50",
        "censored": False,
        "category": "psychology",
        "rating": 9,
        "description": "Быстрый Grok. Без цензуры, с юмором.",
    },
    {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Claude 3.5 Haiku 🔒",
        "price": "$0.80→$4",
        "censored": True,
        "category": "psychology",
        "rating": 8,
        "description": "Дешёвый Claude. Быстрый, эмпатичный.",
    },
    {
        "id": "google/gemini-2.5-flash-preview",
        "name": "Gemini 2.5 Flash 🔒",
        "price": "$0.15→$0.60",
        "censored": True,
        "category": "psychology",
        "rating": 7,
        "description": "Очень дешёвый и умный. ⚠️ Нужен VPN из-за Google.",
    },
    {
        "id": "nousresearch/hermes-3-llama-3.1-70b",
        "name": "Hermes 70B 🔓",
        "price": "$0.40→$0.40",
        "censored": False,
        "category": "psychology",
        "rating": 7,
        "description": "Без цензуры. Для откровенных разговоров.",
    },
    {
        "id": "mistralai/mistral-nemo",
        "name": "Mistral Nemo 🔓",
        "price": "$0.03→$0.03",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "3 цента! Без цензуры. Самая дешёвая рабочая модель.",
    },
    {
        "id": "mistralai/mistral-small-3.1-24b-instruct",
        "name": "Mistral Small 24B 🔓",
        "price": "$0.10→$0.30",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "Без цензуры. Дешёвая и умная.",
    },
    {
        "id": "x-ai/grok-3-mini",
        "name": "Grok 3 Mini 🔓",
        "price": "$0.10→$0.50",
        "censored": False,
        "category": "psychology",
        "rating": 6,
        "description": "Дешёвый Grok. Без цензуры.",
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o Mini 🔒",
        "price": "$0.15→$0.60",
        "censored": True,
        "category": "psychology",
        "rating": 6,
        "description": "Дешёвый и быстрый. Хороший собеседник.",
    },
    {
        "id": "qwen/qwen3-8b:free",
        "name": "Qwen 3 8B (FREE) 🔒",
        "price": "FREE",
        "censored": True,
        "category": "psychology",
        "rating": 5,
        "description": "Бесплатный, хорош для русского. Для тестов.",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Llama 3.3 70B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "uncensored", 
        "rating": 5,
        "description": "Бесплатная 70B без цензуры.",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Llama 3.3 70B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "psychology",
        "rating": 4,
        "description": "Бесплатный, без цензуры. Простенький но работает.",
    },

    # ══════════════════════════════════════════
    #  💻 КОД / ПРОГРАММИРОВАНИЕ
    # ══════════════════════════════════════════

    {
        "id": "anthropic/claude-sonnet-4",
        "name": "Claude Sonnet 4 🔒",
        "price": "$3→$15",
        "censored": True,
        "category": "code",
        "rating": 10,
        "description": "Лучший для кода. Точный, мало ошибок.",
    },
    {
        "id": "x-ai/grok-4-0709",
        "name": "Grok 4 🔓",
        "price": "$3→$12",
        "censored": False,
        "category": "code",
        "rating": 10,
        "description": "Топ-модель от xAI. Без цензуры. Мощнейшая.",
    },
    {
        "id": "openai/gpt-4.1",
        "name": "GPT-4.1 🔒",
        "price": "$2→$8",
        "censored": True,
        "category": "code",
        "rating": 9,
        "description": "Новейшая GPT, отличный код и рефакторинг.",
    },
    {
        "id": "deepseek/deepseek-chat-v3-0324",
        "name": "DeepSeek V3 🔓",
        "price": "$0.14→$0.28",
        "censored": False,
        "category": "code",
        "rating": 9,
        "description": "Топ за свою цену! Без цензуры. Лучшая цена/качество.",
    },
    {
        "id": "deepseek/deepseek-r1",
        "name": "DeepSeek R1 🔓",
        "price": "$0.55→$2.19",
        "censored": False,
        "category": "code",
        "rating": 9,
        "description": "Думает пошагово. Для сложных алгоритмов.",
    },
    {
        "id": "x-ai/grok-4.1-fast",
        "name": "Grok 4.1 Fast 🔓",
        "price": "$0.20→$0.80",
        "censored": False,
        "category": "code",
        "rating": 8,
        "description": "Быстрый и дешёвый Grok. Без цензуры.",
    },
    {
        "id": "qwen/qwen3-32b",
        "name": "Qwen 3 32B 🔒",
        "price": "$0.07→$0.10",
        "censored": True,
        "category": "code",
        "rating": 8,
        "description": "Очень дешёвый! Хорош для Python и веб.",
    },
    {
        "id": "google/gemini-2.5-flash-preview",
        "name": "Gemini 2.5 Flash 🔒",
        "price": "$0.15→$0.60",
        "censored": True,
        "category": "code",
        "rating": 8,
        "description": "Дешёвый, быстрый, большой контекст. ⚠️ VPN.",
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o Mini 🔒",
        "price": "$0.15→$0.60",
        "censored": True,
        "category": "code",
        "rating": 7,
        "description": "Дёшево и быстро. Для простых скриптов.",
    },
    {
        "id": "mistralai/mistral-small-3.1-24b-instruct:free",
        "name": "Mistral Small 24B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "code",
        "rating": 4,
        "description": "Бесплатный, без цензуры. Простой код.",
    },

    # ══════════════════════════════════════════
    #  🎭 РОЛЕПЛЕЙ / КРЕАТИВ / ИСТОРИИ
    # ══════════════════════════════════════════

    {
        "id": "thedrummer/rocinante-12b",
        "name": "Rocinante 12B ✦ZERO",
        "price": "$0.05→$0.05",
        "censored": False,
        "category": "creative",
        "rating": 10,
        "description": "АБСОЛЮТНЫЙ НОЛЬ цензуры. Заточен под ролеплей. 5 центов!",
    },
    {
        "id": "nousresearch/hermes-3-llama-3.1-405b",
        "name": "Hermes 405B 🔓",
        "price": "$0.90→$0.90",
        "censored": False,
        "category": "creative",
        "rating": 10,
        "description": "Огромная 405B. Топ для ролеплея. Без цензуры.",
    },
    {
        "id": "mistralai/mistral-nemo",
        "name": "Mistral Nemo 🔓",
        "price": "$0.03→$0.03",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "3 цента! Без цензуры. Самая дешёвая рабочая модель.",
    },
    {
        "id": "mistralai/mistral-small-3.1-24b-instruct",
        "name": "Mistral Small 24B 🔓",
        "price": "$0.10→$0.30",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "Без цензуры. Дешёвая и умная.",
    },
    {
        "id": "x-ai/grok-3-fast",
        "name": "Grok 3 Fast 🔓",
        "price": "$0.30→$1.50",
        "censored": False,
        "category": "creative",
        "rating": 8,
        "description": "Grok без цензуры. Юмор, креатив.",
    },
    {
        "id": "nousresearch/hermes-3-llama-3.1-70b",
        "name": "Hermes 70B 🔓",
        "price": "$0.40→$0.40",
        "censored": False,
        "category": "creative",
        "rating": 9,
        "description": "Отличный ролеплей за дешёво. Живые персонажи.",
    },
    {
        "id": "eva-unit-01/eva-llama-3.33-70b",
        "name": "EVA 70B ✦ZERO",
        "price": "$0.40→$0.40",
        "censored": False,
        "category": "creative",
        "rating": 8,
        "description": "НОЛЬ цензуры. 70B модель, умная и без ограничений.",
    },
    {
        "id": "mistralai/mistral-large",
        "name": "Mistral Large 🔓",
        "price": "$2→$6",
        "censored": False,
        "category": "creative",
        "rating": 8,
        "description": "Креативный, красивый стиль текста.",
    },
    {
        "id": "mistralai/mixtral-8x7b-instruct",
        "name": "Mixtral 8x7B 🔓",
        "price": "$0.24→$0.24",
        "censored": False,
        "category": "creative",
        "rating": 7,
        "description": "Бюджетный креатив без цензуры.",
    },
    {
        "id": "nousresearch/hermes-3-llama-3.1-405b:free",
        "name": "Hermes 405B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "creative",
        "rating": 7,
        "description": "Бесплатная 405B! Без цензуры. Медленная но мощная.",
    },
    {
        "id": "nvidia/llama-3.1-nemotron-70b-instruct:free",
        "name": "Nemotron 70B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "creative",
        "rating": 6,
        "description": "Бесплатная! Большая модель, хороша для креатива.",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Llama 3.3 70B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "uncensored", 
        "rating": 5,
        "description": "Бесплатная 70B без цензуры.",
    },

    # ══════════════════════════════════════════
    #  📊 АНАЛИТИКА / ДОКУМЕНТЫ / RAG
    # ══════════════════════════════════════════

    {
        "id": "google/gemini-2.5-pro-preview",
        "name": "Gemini 2.5 Pro 🔒",
        "price": "$1.25→$10",
        "censored": True,
        "category": "analytics",
        "rating": 10,
        "description": "Контекст 1M токенов! Для огромных документов. ⚠️ VPN.",
    },
    {
        "id": "x-ai/grok-4-0709",
        "name": "Grok 4 🔓",
        "price": "$3→$12",
        "censored": False,
        "category": "analytics",
        "rating": 10,
        "description": "Мощнейшая модель xAI. Без цензуры.",
    },
    {
        "id": "google/gemini-2.5-flash-preview",
        "name": "Gemini 2.5 Flash 🔒",
        "price": "$0.15→$0.60",
        "censored": True,
        "category": "analytics",
        "rating": 9,
        "description": "Дешёвый, быстрый, контекст 1M. ⚠️ VPN.",
    },
    {
        "id": "deepseek/deepseek-chat-v3-0324",
        "name": "DeepSeek V3 🔓",
        "price": "$0.14→$0.28",
        "censored": False,
        "category": "analytics",
        "rating": 9,
        "description": "Дешёвый, большой контекст. Без цензуры.",
    },
    {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Claude 3.5 Haiku 🔒",
        "price": "$0.80→$4",
        "censored": True,
        "category": "analytics",
        "rating": 8,
        "description": "Точный и быстрый. Хорош для суммаризации.",
    },
    {
        "id": "x-ai/grok-4.1-fast",
        "name": "Grok 4.1 Fast 🔓",
        "price": "$0.20→$0.80",
        "censored": False,
        "category": "analytics",
        "rating": 8,
        "description": "Быстрый Grok для анализа. Без цензуры.",
    },
    {
        "id": "qwen/qwen3-32b",
        "name": "Qwen 3 32B 🔒",
        "price": "$0.07→$0.10",
        "censored": True,
        "category": "analytics",
        "rating": 7,
        "description": "Очень дешёвый, хорош для русских документов.",
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o Mini 🔒",
        "price": "$0.15→$0.60",
        "censored": True,
        "category": "analytics",
        "rating": 7,
        "description": "Дешёвый, быстрый. Для суммаризации.",
    },
    {
        "id": "qwen/qwen3-30b-a3b:free",
        "name": "Qwen 3 30B (FREE) 🔒",
        "price": "FREE",
        "censored": True,
        "category": "analytics",
        "rating": 5,
        "description": "Бесплатная. Для простого анализа текста.",
    },

    # ══════════════════════════════════════════
    #  🧮 ЛОГИКА / МАТЕМАТИКА / REASONING
    # ══════════════════════════════════════════

    {
        "id": "x-ai/grok-4-0709",
        "name": "Grok 4 🔓",
        "price": "$3→$12",
        "censored": False,
        "category": "reasoning",
        "rating": 10,
        "description": "Топ reasoning. Без цензуры. Самая мощная.",
    },
    {
        "id": "deepseek/deepseek-r1",
        "name": "DeepSeek R1 🔓",
        "price": "$0.55→$2.19",
        "censored": False,
        "category": "reasoning",
        "rating": 10,
        "description": "Думает пошагово. Без цензуры. Лучшая цена/качество.",
    },
    {
        "id": "openai/o4-mini",
        "name": "OpenAI o4 Mini 🔒",
        "price": "$1.10→$4.40",
        "censored": True,
        "category": "reasoning",
        "rating": 9,
        "description": "Reasoning от OpenAI. Логика, планирование.",
    },
    {
        "id": "x-ai/grok-3-mini",
        "name": "Grok 3 Mini 🔓",
        "price": "$0.10→$0.50",
        "censored": False,
        "category": "reasoning",
        "rating": 8,
        "description": "Дешёвый reasoning без цензуры.",
    },
    {
        "id": "mistralai/mistral-nemo",
        "name": "Mistral Nemo 🔓",
        "price": "$0.03→$0.03",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "3 цента! Без цензуры. Самая дешёвая рабочая модель.",
    },
    {
        "id": "mistralai/mistral-small-3.1-24b-instruct",
        "name": "Mistral Small 24B 🔓",
        "price": "$0.10→$0.30",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "Без цензуры. Дешёвая и умная.",
    },
    {
        "id": "qwen/qwen3-32b",
        "name": "Qwen 3 32B 🔒",
        "price": "$0.07→$0.10",
        "censored": True,
        "category": "reasoning",
        "rating": 7,
        "description": "Самый дешёвый для логики. 7 центов!",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Llama 3.3 70B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "reasoning",
        "rating": 5,
        "description": "Бесплатная большая модель. Без цензуры.",
    },
    {
        "id": "qwen/qwen3-30b-a3b:free",
        "name": "Qwen 3 30B (FREE) 🔒",
        "price": "FREE",
        "censored": True,
        "category": "reasoning",
        "rating": 5,
        "description": "Бесплатный. Простая математика.",
    },

    # ══════════════════════════════════════════
    #  🔥 АБСОЛЮТНО БЕЗ ЦЕНЗУРЫ (отдельная категория)
    # ══════════════════════════════════════════

    {
        "id": "thedrummer/rocinante-12b",
        "name": "Rocinante 12B ✦ZERO",
        "price": "$0.05→$0.05",
        "censored": False,
        "category": "uncensored",
        "rating": 10,
        "description": "АБСОЛЮТНЫЙ НОЛЬ. 5 центов. Ответит на ВСЁ без предупреждений.",
    },
    {
        "id": "mistralai/mistral-nemo",
        "name": "Mistral Nemo 🔓",
        "price": "$0.03→$0.03",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "3 цента! Без цензуры. Самая дешёвая рабочая модель.",
    },
    {
        "id": "mistralai/mistral-small-3.1-24b-instruct",
        "name": "Mistral Small 24B 🔓",
        "price": "$0.10→$0.30",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "Без цензуры. Дешёвая и умная.",
    },
    {
        "id": "eva-unit-01/eva-llama-3.33-70b",
        "name": "EVA 70B ✦ZERO",
        "price": "$0.40→$0.40",
        "censored": False,
        "category": "uncensored",
        "rating": 8,
        "description": "70B без цензуры. Умная + абсолютно без ограничений.",
    },
    {
        "id": "x-ai/grok-4-0709",
        "name": "Grok 4 🔓",
        "price": "$3→$12",
        "censored": False,
        "category": "uncensored",
        "rating": 10,
        "description": "Самая мощная uncensored. Grok от Маска.",
    },
    {
        "id": "x-ai/grok-4.1-fast",
        "name": "Grok 4.1 Fast 🔓",
        "price": "$0.20→$0.80",
        "censored": False,
        "category": "uncensored",
        "rating": 8,
        "description": "Быстрый Grok без цензуры. Отличная цена.",
    },
    {
        "id": "x-ai/grok-3-fast",
        "name": "Grok 3 Fast 🔓",
        "price": "$0.30→$1.50",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "Grok 3 без цензуры. С юмором.",
    },
    {
        "id": "x-ai/grok-3-mini",
        "name": "Grok 3 Mini 🔓",
        "price": "$0.10→$0.50",
        "censored": False,
        "category": "uncensored",
        "rating": 6,
        "description": "Самый дешёвый Grok. Без цензуры.",
    },
    {
        "id": "nousresearch/hermes-3-llama-3.1-405b",
        "name": "Hermes 405B 🔓",
        "price": "$0.90→$0.90",
        "censored": False,
        "category": "uncensored",
        "rating": 9,
        "description": "405B без цензуры. Мощная.",
    },
    {
        "id": "nousresearch/hermes-3-llama-3.1-70b",
        "name": "Hermes 70B 🔓",
        "price": "$0.40→$0.40",
        "censored": False,
        "category": "uncensored",
        "rating": 7,
        "description": "70B без цензуры. Дешёвая.",
    },
    {
        "id": "nousresearch/hermes-3-llama-3.1-405b:free",
        "name": "Hermes 405B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "uncensored",
        "rating": 6,
        "description": "Бесплатная 405B без цензуры!",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Llama 3.3 70B 🔓 (FREE)",
        "price": "FREE",
        "censored": False,
        "category": "uncensored", 
        "rating": 5,
        "description": "Бесплатная 70B без цензуры.",
    },
]

# категории для отображения в панели
MODEL_CATEGORIES = {
    "psychology": "💬 Собеседник / Психология / Самоанализ",
    "code":       "💻 Код / Программирование",
    "creative":   "🎭 Ролеплей / Креатив / Истории",
    "analytics":  "📊 Аналитика / Документы / RAG",
    "reasoning":  "🧮 Логика / Математика / Reasoning",
    "uncensored": "🔥 Без цензуры (ZERO)",
}


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

    for key, value in updates.items():
        if key in DEFAULT_CONFIG:
            config[key] = value

    save_config(bot_id, config)
    return config


def get_models() -> list:
    """Возвращает список доступных моделей"""
    return AVAILABLE_MODELS