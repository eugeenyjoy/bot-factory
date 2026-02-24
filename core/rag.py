"""
RAG — Retrieval Augmented Generation
База знаний для каждого бота
Загружает документы → нарезает на чанки → индексирует → ищет релевантные
"""

import os
import json
import logging
import numpy as np
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("rag")

# ленивая загрузка тяжёлых библиотек
_embedder = None
_faiss = None


def get_embedder():
    """Загружает модель эмбеддингов (один раз)"""
    global _embedder
    if _embedder is None:
        logger.info("📦 Loading embedding model...")
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("✅ Embedding model loaded")
    return _embedder


def get_faiss():
    """Импортирует faiss (один раз)"""
    global _faiss
    if _faiss is None:
        import faiss
        _faiss = faiss
    return _faiss


class RAG:
    """База знаний одного бота"""

    def __init__(self, bot_id: str):
        self.bot_id = bot_id

        # папки
        base = Path(__file__).parent.parent / "bots" / f"bot_{bot_id}"
        self.knowledge_dir = base / "knowledge"
        self.index_dir = base / "index"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # пути к файлам индекса
        self.index_path = self.index_dir / "faiss.index"
        self.chunks_path = self.index_dir / "chunks.json"

        # данные в памяти
        self.chunks = []       # список текстовых чанков
        self.sources = []      # источник каждого чанка
        self.index = None      # FAISS индекс

        # загружаем существующий индекс если есть
        self._load_index()

    # ====================================================
    # ЗАГРУЗКА ФАЙЛОВ
    # ====================================================

    def add_file(self, filename: str, content: bytes) -> dict:
        """
        Добавляет файл в базу знаний
        Сохраняет файл → парсит → нарезает на чанки → обновляет индекс
        """
        # сохраняем файл
        filepath = self.knowledge_dir / filename
        with open(filepath, 'wb') as f:
            f.write(content)

        # парсим текст
        text = self._extract_text(filepath)
        if not text.strip():
            return {"ok": False, "error": "Не удалось извлечь текст из файла"}

        # нарезаем на чанки
        new_chunks = self._split_text(text, filename)

        # добавляем к существующим
        self.chunks.extend(new_chunks)
        self.sources.extend([filename] * len(new_chunks))

        # перестраиваем индекс
        self._build_index()

        logger.info(f"📚 Bot {self.bot_id}: added {filename} ({len(new_chunks)} chunks)")

        return {
            "ok": True,
            "filename": filename,
            "chunks": len(new_chunks),
            "total_chunks": len(self.chunks)
        }

    def add_text(self, name: str, text: str) -> dict:
        """Добавляет текст напрямую (без файла)"""
        if not text.strip():
            return {"ok": False, "error": "Пустой текст"}

        # сохраняем как txt
        filepath = self.knowledge_dir / f"{name}.txt"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(text)

        # нарезаем
        new_chunks = self._split_text(text, name)
        self.chunks.extend(new_chunks)
        self.sources.extend([name] * len(new_chunks))

        # перестраиваем
        self._build_index()

        return {
            "ok": True,
            "name": name,
            "chunks": len(new_chunks),
            "total_chunks": len(self.chunks)
        }

    def remove_file(self, filename: str) -> bool:
        """Удаляет файл и его чанки из индекса"""
        # удаляем файл
        filepath = self.knowledge_dir / filename
        if filepath.exists():
            os.remove(filepath)

        # удаляем чанки этого файла
        new_chunks = []
        new_sources = []
        for chunk, source in zip(self.chunks, self.sources):
            if source != filename:
                new_chunks.append(chunk)
                new_sources.append(source)

        removed = len(self.chunks) - len(new_chunks)
        self.chunks = new_chunks
        self.sources = new_sources

        # перестраиваем индекс
        if self.chunks:
            self._build_index()
        else:
            self.index = None
            self._save_index()

        logger.info(f"🗑️ Bot {self.bot_id}: removed {filename} ({removed} chunks)")
        return removed > 0

    def clear(self):
        """Удаляет всю базу знаний"""
        # удаляем файлы
        for f in self.knowledge_dir.iterdir():
            os.remove(f)

        # очищаем
        self.chunks = []
        self.sources = []
        self.index = None
        self._save_index()

        logger.info(f"🗑️ Bot {self.bot_id}: knowledge base cleared")

    # ====================================================
    # ПОИСК
    # ====================================================

    def search(self, query: str, top_k: int = 3) -> List[dict]:
        """
        Ищет релевантные чанки по запросу
        Возвращает список: [{text, source, score}]
        """
        if not self.chunks or self.index is None:
            return []

        # эмбеддинг запроса
        embedder = get_embedder()
        query_vec = embedder.encode([query])
        query_vec = np.array(query_vec, dtype='float32')

        # поиск в FAISS
        faiss = get_faiss()
        k = min(top_k, len(self.chunks))
        scores, indices = self.index.search(query_vec, k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            results.append({
                "text": self.chunks[idx],
                "source": self.sources[idx],
                "score": float(scores[0][i])
            })

        return results

    def get_context(self, query: str, top_k: int = 3) -> str:
        """
        Возвращает контекст для промпта из базы знаний
        """
        results = self.search(query, top_k)
        if not results:
            return ""

        context_parts = []
        for r in results:
            context_parts.append(f"[{r['source']}]\n{r['text']}")

        return "\n\n---\n\n".join(context_parts)

    # ====================================================
    # ИНФОРМАЦИЯ
    # ====================================================

    def get_info(self) -> dict:
        """Информация о базе знаний"""
        files = []
        if self.knowledge_dir.exists():
            for f in sorted(self.knowledge_dir.iterdir()):
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "chunks": sum(1 for s in self.sources if s == f.name)
                })

        return {
            "total_files": len(files),
            "total_chunks": len(self.chunks),
            "files": files,
            "has_index": self.index is not None
        }

    # ====================================================
    # ВНУТРЕННИЕ МЕТОДЫ
    # ====================================================

    def _extract_text(self, filepath: Path) -> str:
        """Извлекает текст из файла"""
        ext = filepath.suffix.lower()

        if ext in ('.txt', '.md', '.csv', '.log', '.json', '.html', '.xml'):
            return filepath.read_text(encoding='utf-8', errors='ignore')

        elif ext == '.pdf':
            return self._extract_pdf(filepath)

        else:
            # пробуем как текст
            try:
                return filepath.read_text(encoding='utf-8', errors='ignore')
            except:
                return ""

    def _extract_pdf(self, filepath: Path) -> str:
        """Извлекает текст из PDF"""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(filepath))
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return ""

    def _split_text(self, text: str, source: str, chunk_size: int = 500, overlap: int = 50) -> list:
        """Нарезает текст на чанки с перекрытием"""
        # разбиваем по абзацам
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

        chunks = []
        current_chunk = ""

        for para in paragraphs:
            # если абзац сам по себе больше chunk_size — разбиваем его
            if len(para) > chunk_size:
                # сохраняем текущий чанк
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                # разбиваем длинный абзац
                words = para.split()
                temp = ""
                for word in words:
                    if len(temp) + len(word) + 1 > chunk_size:
                        chunks.append(temp.strip())
                        # перекрытие — берём последние N символов
                        temp = temp[-overlap:] + " " + word if overlap else word
                    else:
                        temp = temp + " " + word if temp else word
                if temp:
                    chunks.append(temp.strip())

            # если добавление абзаца превысит лимит
            elif len(current_chunk) + len(para) + 1 > chunk_size:
                chunks.append(current_chunk)
                # перекрытие
                current_chunk = current_chunk[-overlap:] + "\n" + para if overlap else para
            else:
                current_chunk = current_chunk + "\n" + para if current_chunk else para

        # последний чанк
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _build_index(self):
        """Строит FAISS индекс из чанков"""
        if not self.chunks:
            self.index = None
            self._save_index()
            return

        # получаем эмбеддинги
        embedder = get_embedder()
        vectors = embedder.encode(self.chunks)
        vectors = np.array(vectors, dtype='float32')

        # строим индекс
        faiss = get_faiss()
        dimension = vectors.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(vectors)

        # сохраняем
        self._save_index()

    def _save_index(self):
        """Сохраняет индекс и чанки на диск"""
        # сохраняем чанки
        data = {
            "chunks": self.chunks,
            "sources": self.sources
        }
        with open(self.chunks_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # сохраняем FAISS индекс
        if self.index is not None:
            faiss = get_faiss()
            faiss.write_index(self.index, str(self.index_path))
        else:
            if self.index_path.exists():
                os.remove(self.index_path)

    def _load_index(self):
        """Загружает индекс и чанки с диска"""
        # загружаем чанки
        if self.chunks_path.exists():
            try:
                with open(self.chunks_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.chunks = data.get("chunks", [])
                self.sources = data.get("sources", [])
            except:
                self.chunks = []
                self.sources = []

        # загружаем FAISS индекс
        if self.index_path.exists() and self.chunks:
            try:
                faiss = get_faiss()
                self.index = faiss.read_index(str(self.index_path))
                logger.info(f"📚 Bot {self.bot_id}: loaded {len(self.chunks)} chunks")
            except:
                self.index = None