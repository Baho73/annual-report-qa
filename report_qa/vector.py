"""M-VECTOR: контрольная ветка замера — поиск по чанкам."""

# FILE: report_qa/vector.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: добросовестная реализация поиска по чанкам как контрольная точка сравнения с полным контекстом и маршрутизацией.
#   SCOPE: нарезка по разделам без разрыва таблиц, лексический поиск BM25, точка подключения плотных эмбеддингов.
#   DEPENDS: M-PARSE, M-CONFIG
#   LINKS: M-VECTOR, V-M-VECTOR
#   INPUTS: data/sections.json
#   OUTPUTS: ранжированный список чанков с разделами и страницами
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   Chunk - кусок документа с заголовком раздела и диапазоном страниц внутри текста
#   build_chunks - нарезка по разделам: смысловая единица вместо фиксированных N токенов
#   BM25 - лексический поиск; на числах и точных терминах работает лучше эмбеддингов
#   search - top-k чанков под запрос
#   section_ids_for - идентификаторы разделов, покрывающих найденные чанки
#   MAX_CHUNK_CHARS - потолок размера чанка, выше которого раздел режется по абзацам
# END_MODULE_MAP

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

from report_qa import config
from report_qa.parse import load_sections

__all__ = ["Chunk", "build_chunks", "BM25", "search", "section_ids_for", "MAX_CHUNK_CHARS"]

# Потолок подобран так, чтобы типичный подраздел отчёта уходил одним куском.
MAX_CHUNK_CHARS = 6000
_OVERLAP_CHARS = 400

_WORD_RE = re.compile(r"[\w-]+", re.U)


# START_BLOCK_CHUNKS
@dataclass
class Chunk:
    """Кусок документа, знающий, откуда он взят."""

    text: str
    section_id: str
    section_title: str
    page_from: int
    page_to: int

    @property
    def searchable(self) -> str:
        """Текст для индекса.

        Заголовок и страницы лежат ВНУТРИ текста, а не только в метаданных:
        иначе запрос «риски» не находит раздел, где слово стоит в заголовке,
        а в теле встречается редко.
        """
        return f"{self.section_title}\nстр. {self.page_from}-{self.page_to}\n{self.text}"


def build_chunks(sections: Optional[List[dict]] = None) -> List[Chunk]:
    """Нарезка по разделам, а не по фиксированному размеру.

    Условие честности замера: чанк совпадает со смысловой единицей документа,
    иначе сравнение идёт с соломенным чучелом и разбирается на защите за минуту.
    Числовые таблицы в текст не попадают вовсе — они живут отдельным JSON
    с провенансом, и рвать их нечем.
    """
    sections = sections if sections is not None else load_sections()
    # Берём листовые разделы: у родителя текст дублирует детей.
    leaves = []
    for section in sections:
        has_children = any(
            other is not section
            and other["level"] > section["level"]
            and section["page_from"] <= other["page_from"] <= section["page_to"]
            for other in sections
        )
        if not has_children:
            leaves.append(section)

    chunks: List[Chunk] = []
    for section in leaves:
        text = section["text"].strip()
        if not text:
            continue
        if len(text) <= MAX_CHUNK_CHARS:
            pieces = [text]
        else:
            # Длинный раздел режем по абзацам с перекрытием, чтобы факт на
            # границе не потерялся между кусками.
            pieces, current = [], ""
            for paragraph in text.split("\n\n"):
                if len(current) + len(paragraph) > MAX_CHUNK_CHARS and current:
                    pieces.append(current)
                    current = current[-_OVERLAP_CHARS:] + "\n\n" + paragraph
                else:
                    current = f"{current}\n\n{paragraph}" if current else paragraph
            if current:
                pieces.append(current)

        for piece in pieces:
            chunks.append(Chunk(
                text=piece,
                section_id=section["id"],
                section_title=section["title"],
                page_from=section["page_from"],
                page_to=section["page_to"],
            ))
    return chunks
# END_BLOCK_CHUNKS


# START_BLOCK_BM25
class BM25:
    """Лексический поиск.

    Плотные эмбеддинги плохо находят числа и точные термины — именно то, из
    чего состоит финансовый отчёт. Поэтому лексическая ветка обязательна;
    плотная подключается рядом, когда будет доступ к модели эмбеддингов.
    """

    def __init__(self, documents: List[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [self._tokenize(d) for d in documents]
        self.lengths = [len(d) for d in self.docs]
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.docs else 0.0
        self.freqs = [Counter(d) for d in self.docs]

        appearances = Counter()
        for doc in self.docs:
            appearances.update(set(doc))
        total = len(self.docs) or 1
        self.idf = {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for term, count in appearances.items()
        }

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [w.lower() for w in _WORD_RE.findall(text or "")]

    def score(self, query: str, index: int) -> float:
        freqs, length = self.freqs[index], self.lengths[index] or 1
        total = 0.0
        for term in self._tokenize(query):
            frequency = freqs.get(term, 0)
            if not frequency:
                continue
            denominator = frequency + self.k1 * (1 - self.b + self.b * length / (self.avgdl or 1))
            total += self.idf.get(term, 0.0) * frequency * (self.k1 + 1) / denominator
        return total

    def top(self, query: str, k: int) -> List[int]:
        scored = ((i, self.score(query, i)) for i in range(len(self.docs)))
        ranked = sorted((p for p in scored if p[1] > 0), key=lambda p: -p[1])
        return [i for i, _ in ranked[:k]]
# END_BLOCK_BM25


# START_BLOCK_SEARCH
_INDEX: dict = {}


def _index(sections: Optional[List[dict]] = None):
    """Индекс строится один раз на процесс: перестройка на каждый вопрос
    съела бы всю разницу в задержке, ради которой ветка и меряется."""
    if "chunks" not in _INDEX or sections is not None:
        chunks = build_chunks(sections)
        _INDEX["chunks"] = chunks
        _INDEX["bm25"] = BM25([c.searchable for c in chunks])
    return _INDEX["chunks"], _INDEX["bm25"]


def search(question: str, k: Optional[int] = None,
           sections: Optional[List[dict]] = None) -> List[Chunk]:
    """Top-k чанков под вопрос.

    k=8 по умолчанию, а не 3: при узкой выборке проигрыш ветки объяснялся бы
    размером окна, а не качеством поиска, и замер потерял бы смысл.
    """
    chunks, bm25 = _index(sections)
    k = k or config.THRESHOLDS["top_k"]
    return [chunks[i] for i in bm25.top(question, k)]


def section_ids_for(question: str, k: Optional[int] = None,
                    sections: Optional[List[dict]] = None) -> List[str]:
    """Разделы, покрывающие найденные чанки — вход для сборки контекста."""
    return list(dict.fromkeys(c.section_id for c in search(question, k, sections)))
# END_BLOCK_SEARCH
