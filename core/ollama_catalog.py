"""
Каталог Ollama — кеш + live фетч
- При старте загружает из ollama_catalog_full.json (если есть)
- Раз в 24 часа обновляет в фоне
- При поиске конкретной модели — фетчит на лету если нет в кеше
"""

import re
import json
import time
import logging
import threading
import urllib.request
from pathlib import Path

logger = logging.getLogger("ollama_catalog")

ROOT_DIR = Path(__file__).parent.parent
CACHE_FILE = ROOT_DIR / "ollama_catalog_full.json"
CATALOG_URL = "https://ollama.com/library"
TAGS_URL = "https://ollama.com/library/{model}/tags"

# Кеш: { model: { tag: {size, ctx, ram, vram} } }
_cache = {}
_cache_timestamp = 0
_cache_ttl = 86400  # 24 часа
_model_list = []    # список имён моделей
_model_list_ts = 0
_updating = False


def _parse_size_gb(s: str) -> float:
    m = re.match(r'([\d.]+)(GB|MB|KB)', s.strip())
    if not m: return 0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == 'GB': return round(val, 2)
    if unit == 'MB': return round(val / 1024, 2)
    return 0


def _parse_context(s: str) -> int:
    m = re.match(r'([\d.]+)(K|M)', s.strip())
    if not m: return 0
    val = float(m.group(1))
    if m.group(2) == 'K': return int(val * 1024)
    if m.group(2) == 'M': return int(val * 1024 * 1024)
    return 0


def _calc_ram_vram(size_gb: float):
    if size_gb <= 0: return 0, 0
    return round(size_gb * 1.2, 1), round(size_gb * 1.1, 1)


def _fetch_model_tags(model: str) -> dict:
    """Фетчит теги + размеры одной модели с ollama.com"""
    try:
        url = TAGS_URL.format(model=model)
        html = urllib.request.urlopen(url, timeout=10).read().decode()

        tags = {}
        # Находим все теги
        tag_pattern = rf'href="/library/{re.escape(model)}:([^"]+)"'
        tag_matches = list(re.finditer(tag_pattern, html))

        seen = set()
        for tm in tag_matches:
            tag = tm.group(1)
            if tag in seen:
                continue
            seen.add(tag)

            after = html[tm.end():tm.end()+800]
            size_match = re.search(r'[\s•]+(\d+\.?\d*(?:GB|MB|KB))', after)
            size_gb = _parse_size_gb(size_match.group(1)) if size_match else 0
            ctx_match = re.search(r'(\d+\.?\d*[KM])\s*context', after)
            context = _parse_context(ctx_match.group(1)) if ctx_match else 0
            ram, vram = _calc_ram_vram(size_gb)

            tags[tag] = {"size": size_gb, "ctx": context, "ram": ram, "vram": vram}

        return tags
    except Exception as e:
        logger.warning(f"Failed to fetch tags for {model}: {e}")
        return {}


def _fetch_model_list() -> list:
    """Фетчит список всех моделей с ollama.com"""
    global _model_list, _model_list_ts
    try:
        html = urllib.request.urlopen(CATALOG_URL, timeout=15).read().decode()
        names = re.findall(r'href="/library/([^"]+)"', html)
        # уникальные, без дублей
        seen = set()
        result = []
        for n in names:
            if n not in seen and "/" not in n:
                seen.add(n)
                result.append(n)
        _model_list = sorted(result)
        _model_list_ts = time.time()
        logger.info(f"Fetched model list: {len(_model_list)} models")
        return _model_list
    except Exception as e:
        logger.error(f"Failed to fetch model list: {e}")
        return _model_list


def _load_cache():
    """Загружает кеш из файла"""
    global _cache, _cache_timestamp
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                _cache = json.load(f)
            _cache_timestamp = CACHE_FILE.stat().st_mtime
            total = sum(len(v) for v in _cache.values())
            logger.info(f"Loaded catalog cache: {len(_cache)} models, {total} tags")
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")


def _save_cache():
    """Сохраняет кеш в файл"""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(_cache, f)
        logger.info(f"Saved catalog cache: {len(_cache)} models")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")


def _background_update():
    """Фоновое обновление всего каталога"""
    global _cache, _cache_timestamp, _updating
    if _updating:
        return
    _updating = True
    logger.info("Starting background catalog update...")

    try:
        models = _fetch_model_list()
        updated = 0
        for model in models:
            tags = _fetch_model_tags(model)
            if tags:
                _cache[model] = tags
                updated += 1
            time.sleep(0.15)  # не спамим

        _cache_timestamp = time.time()
        _save_cache()
        logger.info(f"Catalog updated: {updated}/{len(models)} models")
    except Exception as e:
        logger.error(f"Background update failed: {e}")
    finally:
        _updating = False


def init():
    """Инициализация при старте приложения"""
    _load_cache()

    # если кеш старше 24ч или пустой — обновляем в фоне
    if not _cache or (time.time() - _cache_timestamp) > _cache_ttl:
        thread = threading.Thread(target=_background_update, daemon=True)
        thread.start()



# Список моделей известных как uncensored
_UNCENSORED_NAMES = {
    'dolphin-llama3', 'dolphin-mistral', 'dolphin-mixtral', 'dolphin-phi',
    'dolphin3', 'dolphincoder', 'llama2-uncensored', 'nous-hermes', 'nous-hermes2',
    'nous-hermes2-mixtral', 'tinydolphin', 'wizard-vicuna-uncensored',
    'wizardlm-uncensored', 'hermes3', 'mannix-llama3.1-8b', 'gurubot',
    'llama3-chatqa', 'samantha-mistral', 'everythinglm', 'adrienbrault-nous-hermes2',
}

def _is_uncensored(name: str) -> bool:
    """Проверяет по имени, является ли модель uncensored"""
    nl = name.lower()
    if nl in _UNCENSORED_NAMES:
        return True
    for kw in ['uncensored', 'abliterat', 'dolphin']:
        if kw in nl:
            return True
    return False

def _get_ram_for_sort(tags: dict) -> float:
    """Получить RAM latest тега для сортировки. 9999 если неизвестно."""
    latest = tags.get('latest', {})
    ram = latest.get('ram', 0)
    if ram and ram > 0:
        return ram
    # fallback: первый тег с ram
    for t, v in tags.items():
        if isinstance(v, dict) and v.get('ram', 0) > 0:
            return v['ram']
    return 9999.0

def search(query: str = "", limit: int = 50) -> dict:
    """Поиск моделей в каталоге"""

    q = query.lower().strip()
    results = []

    POPULAR = [
        "qwen3", "qwen3.5", "qwen2.5", "qwen2.5-coder", "llama3.2", "llama3.1",
        "gemma3", "gemma3n", "phi4", "phi4-mini", "mistral", "deepseek-r1",
        "codestral", "devstral", "dolphin-mistral", "dolphin3",
        "wizard-vicuna-uncensored", "hermes3", "cogito",
        "mistral-small3.1", "tinyllama", "smollm2",
    ]

    if not q:
        # Все модели, сортированные по RAM (лёгкие наверху)
        all_models = []
        for name, tags in _cache.items():
            ram = _get_ram_for_sort(tags)
            main = {t: v for t, v in tags.items()
                    if not any(x in t for x in ["q2_", "q3_", "q4_0", "q4_1", "q5_0", "q5_1", "q6_", "q8_", "fp16", "bf16"])}
            if not main:
                main = dict(list(tags.items())[:5])
            all_models.append({
                "model": name,
                "tags": {t: v for t, v in list(main.items())[:8]},
                "total_tags": len(tags),
                "uncensored": _is_uncensored(name),
                "_ram_sort": ram,
            })
        all_models.sort(key=lambda x: x["_ram_sort"])
        for m in all_models:
            del m["_ram_sort"]
        return {"models": all_models[:limit], "total_in_catalog": len(_cache)}

    # Стратегия поиска:
    # 1. Склеиваем слова через дефис/точку → ищем точное имя модели
    # 2. Первое слово (или несколько) = имя модели, последнее = фильтр тега
    # 3. Сортируем: точное совпадение > начинается с > содержит

    words = q.split()
    
    # Генерируем варианты имени: "deepseek r1" → "deepseek-r1", "deepseek.r1", "deepseekr1"
    q_joined = [
        q.replace(' ', '-'),
        q.replace(' ', '.'),
        q.replace(' ', ''),
    ]

    scored = []

    for model_name, tags in _cache.items():
        score = 0
        tag_filter = []  # слова для фильтра тегов

        # --- Матчинг имени модели ---
        
        # A) Точное совпадение склеенного запроса
        for qj in q_joined:
            if model_name == qj:
                score = 100
                break
            elif model_name.startswith(qj):
                score = max(score, 90)
                break
            elif qj in model_name:
                score = max(score, 60)
                break

        # B) Пробуем: первые N слов = имя, остальные = тег
        if score == 0:
            # от длинного к короткому: "deepseek r1 14b" → пробуем "deepseek-r1" + "14b"
            for split_at in range(len(words), 0, -1):
                name_part_words = words[:split_at]
                tag_part_words = words[split_at:]
                
                for sep in ['-', '.', '']:
                    name_candidate = sep.join(name_part_words)
                    if model_name == name_candidate:
                        score = 95
                        tag_filter = tag_part_words
                        break
                    elif model_name.startswith(name_candidate) and len(name_candidate) >= 3:
                        score = max(score, 75 - (len(model_name) - len(name_candidate)))
                        tag_filter = tag_part_words
                        break
                    elif name_candidate in model_name and len(name_candidate) >= 3:
                        score = max(score, 50 - (len(model_name) - len(name_candidate)))
                        tag_filter = tag_part_words
                        break
                if score > 0:
                    break

        # C) Единственное слово — ищем в тегах тоже
        if score == 0 and len(words) == 1:
            matching = {t: v for t, v in tags.items() if words[0] in t}
            if matching:
                score = 10
                # для тега без совпадения имени — показываем только найденные теги
                scored.append((score, model_name, dict(list(matching.items())[:10]), len(tags)))
                continue

        if score <= 0:
            continue

        # --- Фильтрация тегов ---
        if tag_filter:
            # показываем только теги содержащие ВСЕ слова фильтра
            matching = {}
            for t, v in tags.items():
                if all(tw in t for tw in tag_filter):
                    matching[t] = v
            if matching:
                scored.append((score + 5, model_name, dict(list(matching.items())[:10]), len(tags)))
            # также добавляем модель без фильтра но с меньшим score
            main = {t: v for t, v in tags.items()
                    if not any(x in t for x in ["q2_", "q3_", "q4_0", "q4_1", "q5_0", "q5_1"])}
            if not main:
                main = dict(list(tags.items())[:8])
            scored.append((score - 10, model_name, dict(list(main.items())[:8]), len(tags)))
        else:
            # без фильтра — основные теги
            main = {t: v for t, v in tags.items()
                    if not any(x in t for x in ["q2_", "q3_", "q4_0", "q4_1", "q5_0", "q5_1"])}
            if not main:
                main = dict(list(tags.items())[:8])
            shown = dict(list(main.items())[:10])
            scored.append((score, model_name, shown, len(tags)))

    # дедупликация: одна модель может попасть дважды — берём лучший score
    best = {}
    for sc, name, mtags, total in scored:
        if name not in best or sc > best[name][0]:
            best[name] = (sc, name, mtags, total)

    # сортируем: по score (desc), затем по RAM (asc) — лёгкие выше
    def sort_key(item):
        sc, name, mtags, total = item
        ram = _get_ram_for_sort(_cache.get(name, {}))
        return (-sc, ram, name)

    sorted_results = sorted(best.values(), key=sort_key)

    results = [
        {"model": name, "tags": mtags, "total_tags": total, "uncensored": _is_uncensored(name)}
        for _, name, mtags, total in sorted_results[:limit]
    ]

    return {"models": results, "total_in_catalog": len(_cache)}



def get_model_tags(model_name: str) -> dict:
    """Все теги модели. Если нет в кеше — фетчит live"""
    if model_name in _cache and _cache[model_name]:
        return _cache[model_name]

    # live fetch
    logger.info(f"Live fetching tags for {model_name}")
    tags = _fetch_model_tags(model_name)
    if tags:
        _cache[model_name] = tags
        # сохраняем в фоне
        threading.Thread(target=_save_cache, daemon=True).start()
    return tags


def force_update():
    """Принудительное обновление (для кнопки в UI)"""
    thread = threading.Thread(target=_background_update, daemon=True)
    thread.start()
    return {"status": "updating", "current_models": len(_cache)}
