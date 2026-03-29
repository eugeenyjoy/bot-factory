"""
RAG — база знаний бота
Разбивает тексты на чанки по смыслу (абзацы, предложения)
Поиск через TF-IDF (без внешних зависимостей)
"""

import re
import json
import math
import logging
from pathlib import Path
from collections import Counter
from typing import List, Dict, Optional

logger = logging.getLogger("rag")

BOTS_DIR = Path(__file__).parent.parent / "bots"

# стоп-слова — вынесены в константу
STOP_WORDS = {
    # русские
    'это', 'как', 'так', 'что', 'для', 'все', 'его', 'она', 'они', 'мне',
    'мой', 'ваш', 'наш', 'его', 'еще', 'уже', 'или', 'при', 'без', 'над',
    'под', 'про', 'между', 'через', 'после', 'перед', 'вот', 'тут', 'там',
    'где', 'когда', 'если', 'чтобы', 'потому', 'поэтому', 'такой', 'этот',
    'тот', 'самый', 'весь', 'каждый', 'другой', 'быть', 'было', 'будет',
    'есть', 'нет', 'можно', 'нужно', 'надо', 'очень', 'только', 'также',
    'тоже', 'более', 'менее', 'всего', 'всех', 'ещё', 'бы', 'же', 'ли',
    'не', 'ни', 'ну', 'да', 'нет',
    # английские
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
    'her', 'was', 'one', 'our', 'out', 'has', 'have', 'been', 'from',
    'this', 'that', 'with', 'they', 'been', 'have', 'many', 'some', 'them',
    'than', 'its', 'over', 'such', 'into', 'other', 'which', 'their',
    'there', 'about', 'would', 'make', 'like', 'just', 'could', 'also',
    'after', 'know', 'being', 'will', 'what', 'when', 'who', 'how',
}

# лимиты
MAX_CHUNKS = 10000
MAX_TEXT_SIZE = 10 * 1024 * 1024  # 10MB


class RAG:

    def __init__(self, bot_id: str, chunk_size: int = 800,
                 chunk_overlap: int = 100, min_chunk_size: int = 50):
        self.bot_id = bot_id
        self.chunk_size = max(100, min(5000, chunk_size))
        self.chunk_overlap = max(0, min(chunk_size // 2, chunk_overlap))
        self.min_chunk_size = max(10, min(chunk_size, min_chunk_size))

        self.data_dir = BOTS_DIR / f"bot_{bot_id}" / "knowledge"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.index_file = self.data_dir / "index.json"

        # chunks: [{"text": ..., "source": ..., "index": ...}]
        self.chunks: List[Dict] = []
        # idf кэш
        self._idf_cache: Dict[str, float] = {}
        self._doc_freq: Counter = Counter()
        self._total_docs: int = 0

        self._load_index()

    # ============================
    # ЗАГРУЗКА / СОХРАНЕНИЕ
    # ============================

    def _load_index(self):
        if not self.index_file.exists():
            return

        try:
            raw = self.index_file.read_text(encoding='utf-8')
            data = json.loads(raw)

            if not isinstance(data, dict):
                logger.warning(f"RAG {self.bot_id}: invalid index format")
                self.chunks = []
                return

            loaded = data.get("chunks", [])

            # валидация чанков
            valid_chunks = []
            for chunk in loaded:
                if (isinstance(chunk, dict)
                        and isinstance(chunk.get("text"), str)
                        and chunk["text"].strip()):
                    valid_chunks.append(chunk)

            self.chunks = valid_chunks
            self._rebuild_index()
            logger.info(f"RAG {self.bot_id}: loaded {len(self.chunks)} chunks")

        except json.JSONDecodeError as e:
            logger.error(f"RAG {self.bot_id} index JSON error: {e}")
            self.chunks = []
        except OSError as e:
            logger.error(f"RAG {self.bot_id} index read error: {e}")
            self.chunks = []

    def _save_index(self):
        try:
            data = {"chunks": self.chunks}
            tmp_file = self.index_file.with_suffix('.tmp')
            tmp_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            tmp_file.replace(self.index_file)
        except OSError as e:
            logger.error(f"RAG {self.bot_id} save error: {e}")
        except (TypeError, ValueError) as e:
            logger.error(f"RAG {self.bot_id} serialize error: {e}")

    def _rebuild_index(self):
        """Пересчитывает TF-IDF индекс"""
        self._doc_freq = Counter()
        self._total_docs = len(self.chunks)

        for chunk in self.chunks:
            words = set(self._tokenize(chunk["text"]))
            for word in words:
                self._doc_freq[word] += 1

        self._idf_cache = {}
        for word, freq in self._doc_freq.items():
            self._idf_cache[word] = math.log(
                (self._total_docs + 1) / (freq + 1)
            ) + 1

    # ============================
    # ДОБАВЛЕНИЕ
    # ============================

    def add_text(self, name: str, text: str) -> int:
        """Добавляет текст, разбивает на чанки. Возвращает кол-во чанков."""
        if not name or not name.strip():
            raise ValueError("Name cannot be empty")

        if not text or not text.strip():
            return 0

        if len(text) > MAX_TEXT_SIZE:
            raise ValueError(f"Text too large: {len(text)} bytes (max {MAX_TEXT_SIZE})")

        # удаляем старые чанки с тем же именем
        self.chunks = [c for c in self.chunks if c.get("source") != name]

        # разбиваем на чанки
        new_chunks = self._smart_chunk(text, name)

        if not new_chunks:
            return 0

        # проверяем лимит
        if len(self.chunks) + len(new_chunks) > MAX_CHUNKS:
            raise ValueError(
                f"Too many chunks: {len(self.chunks) + len(new_chunks)} "
                f"(max {MAX_CHUNKS})"
            )

        start_idx = len(self.chunks)
        for i, chunk_text in enumerate(new_chunks):
            self.chunks.append({
                "text": chunk_text,
                "source": name,
                "index": start_idx + i,
            })

        self._rebuild_index()
        self._save_index()

        logger.info(f"RAG {self.bot_id}: added '{name}' → {len(new_chunks)} chunks")
        return len(new_chunks)

    def add_file(self, filename: str, content: bytes) -> dict:
        """Добавляет бинарный файл (для совместимости)"""
        if not content:
            return {"ok": False, "error": "Empty content"}

        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = content.decode('cp1251')
            except UnicodeDecodeError as e:
                logger.warning(f"File decode failed {filename}: {e}")
                return {"ok": False, "error": "Не удалось прочитать файл"}

        if not text.strip():
            return {"ok": False, "error": "Файл пустой"}

        try:
            chunks = self.add_text(filename, text)
            return {"ok": True, "chunks": chunks, "filename": filename}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    # ============================
    # УМНЫЙ ЧАНКИНГ
    # ============================

    def _smart_chunk(self, text: str, source: str = "") -> List[str]:
        """
        Разбивает текст на чанки по смыслу:
        1. Сначала по двойным переносам (абзацы)
        2. Потом по предложениям если абзац слишком большой
        3. Overlap между чанками для контекста
        """
        text = text.strip()
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        if not text:
            return []

        # если текст короткий — один чанк
        if len(text) <= self.chunk_size:
            if len(text) >= self.min_chunk_size:
                return [text]
            return [text] if text.strip() else []

        # разбиваем по абзацам
        paragraphs = re.split(r'\n\n+', text)

        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # если абзац слишком большой — разбиваем по предложениям
            if len(para) > self.chunk_size:
                if current.strip():
                    chunks.append(current.strip())
                    current = ""

                sentence_chunks = self._chunk_long_paragraph(para)
                chunks.extend(sentence_chunks)
                continue

            # обычный абзац — накапливаем
            if len(current) + len(para) + 2 <= self.chunk_size:
                current = (current + "\n\n" + para).strip()
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = para

        if current.strip():
            chunks.append(current.strip())

        # добавляем overlap
        if self.chunk_overlap > 0 and len(chunks) > 1:
            chunks = self._add_overlap(chunks)

        # фильтруем слишком маленькие
        chunks = [c for c in chunks if len(c) >= self.min_chunk_size]

        return chunks

    def _chunk_long_paragraph(self, para: str) -> List[str]:
        """Разбивает длинный абзац по предложениям"""
        chunks = []
        sentences = self._split_sentences(para)
        sent_chunk = ""

        for sent in sentences:
            if len(sent_chunk) + len(sent) + 1 <= self.chunk_size:
                sent_chunk = (sent_chunk + " " + sent).strip()
            else:
                if sent_chunk:
                    chunks.append(sent_chunk)

                # одно предложение больше chunk_size — разрезаем
                if len(sent) > self.chunk_size:
                    step = max(1, self.chunk_size - self.chunk_overlap)
                    for i in range(0, len(sent), step):
                        piece = sent[i:i + self.chunk_size]
                        if piece.strip():
                            chunks.append(piece.strip())
                    sent_chunk = ""
                else:
                    sent_chunk = sent

        if sent_chunk.strip():
            chunks.append(sent_chunk.strip())

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """Разбивает текст на предложения"""
        parts = re.split(r'(?<=[.!?])\s+|\n', text)
        return [p.strip() for p in parts if p.strip()]

    def _add_overlap(self, chunks: List[str]) -> List[str]:
        """Добавляет overlap — конец предыдущего чанка в начало следующего"""
        result = [chunks[0]]

        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            curr = chunks[i]

            overlap_text = prev[-self.chunk_overlap:]

            # находим начало слова
            space_idx = overlap_text.find(' ')
            if space_idx > 0:
                overlap_text = overlap_text[space_idx + 1:]

            combined = f"...{overlap_text}\n\n{curr}"
            result.append(combined)

        return result

    # ============================
    # ПОИСК
    # ============================

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Поиск по TF-IDF + keyword matching"""
        if not self.chunks:
            return []

        if not query or not query.strip():
            return []

        top_k = max(1, min(50, top_k))

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        query_tf = Counter(query_tokens)
        scores = []

        for i, chunk in enumerate(self.chunks):
            score = self._score_chunk(chunk["text"], query_tokens, query_tf)
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scores[:top_k]:
            chunk = self.chunks[idx]
            results.append({
                "text": chunk["text"],
                "source": chunk.get("source", "unknown"),
                "score": round(score, 4),
                "index": idx,
            })

        return results

    def get_context(self, query: str, top_k: int = 3) -> str:
        """Возвращает контекст для системного промпта"""
        results = self.search(query, top_k)
        if not results:
            return ""

        parts = []
        for r in results:
            source = r["source"]
            text = r["text"]
            parts.append(f"[Источник: {source}]\n{text}")

        return "\n\n---\n\n".join(parts)

    def _score_chunk(self, text: str, query_tokens: List[str],
                     query_tf: Counter) -> float:
        """Считает TF-IDF score для чанка"""
        doc_tokens = self._tokenize(text)
        if not doc_tokens:
            return 0.0

        doc_tf = Counter(doc_tokens)
        doc_len = len(doc_tokens)

        score = 0.0
        for token in query_tokens:
            if token in doc_tf:
                tf = doc_tf[token] / doc_len
                idf = self._idf_cache.get(token, 1.0)
                score += tf * idf * query_tf[token]

        # бонус за точное вхождение фразы
        text_lower = text.lower()
        query_lower = " ".join(query_tokens)
        if len(query_lower) > 3 and query_lower in text_lower:
            score *= 2.0

        # бонус за наличие всех слов запроса
        unique_tokens = set(query_tokens)
        if len(unique_tokens) > 1 and all(t in doc_tf for t in unique_tokens):
            score *= 1.5

        return score

    # ============================
    # ТОКЕНИЗАЦИЯ
    # ============================

    def _tokenize(self, text: str) -> List[str]:
        """Простая токенизация: lowercase, убираем пунктуацию, стоп-слова"""
        if not text:
            return []
        text = text.lower()
        tokens = re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9]+', text)
        tokens = [t for t in tokens if len(t) > 2 and t not in STOP_WORDS]
        return tokens

    # ============================
    # УПРАВЛЕНИЕ
    # ============================

    def remove_file(self, name: str):
        if not name:
            return
        before = len(self.chunks)
        self.chunks = [c for c in self.chunks if c.get("source") != name]
        removed = before - len(self.chunks)
        if removed > 0:
            self._rebuild_index()
            self._save_index()
            logger.info(f"RAG {self.bot_id}: removed '{name}' ({removed} chunks)")

    def clear(self):
        count = len(self.chunks)
        self.chunks = []
        self._rebuild_index()
        self._save_index()
        logger.info(f"RAG {self.bot_id}: cleared ({count} chunks)")

    def get_info(self) -> dict:
        sources: Dict[str, dict] = {}
        for chunk in self.chunks:
            src = chunk.get("source", "unknown")
            if src not in sources:
                sources[src] = {"name": src, "chunks": 0, "size": 0}
            sources[src]["chunks"] += 1
            sources[src]["size"] += len(chunk.get("text", ""))

        admin_files = []
        user_files = []
        for info in sources.values():
            if info["name"].startswith("👤"):
                user_files.append(info)
            else:
                admin_files.append(info)

        return {
            "total_files": len(sources),
            "total_chunks": len(self.chunks),
            "files": list(sources.values()),
            "admin_files": admin_files,
            "user_files": user_files,
        }