"""The spoiler-detection pipeline: retrieve → filter future → ask the LLM."""

from __future__ import annotations

from app.config import settings

# 最低准入相似度（只作用于向量召回）
MIN_SIMILARITY = 0.45
# 传入 LLM 的最大总字数
MAX_CONTEXT_CHARS = 1200
# 每个段落截取关键词片段的窗口大小（字符）
SNIPPET_WINDOW = 120


def _extract_snippet(content: str, query: str, window: int = SNIPPET_WINDOW) -> str:
    """在 content 中找到与 query 字符重叠最多的位置，截取前后 window 字的片段。"""
    if len(content) <= window:
        return content

    query_chars = {c for c in query if c.strip()}
    best_pos, best_score = 0, -1
    step = max(1, window // 2)
    last_start = len(content) - window
    for start in range(0, last_start + 1, step):
        chunk = content[start:start + window]
        score = sum(chunk.count(c) for c in query_chars)
        if score > best_score:
            best_score, best_pos = score, start

    snippet = content[best_pos:best_pos + window]
    prefix = "..." if best_pos > 0 else ""
    suffix = "..." if best_pos + window < len(content) else ""
    return prefix + snippet + suffix


def determine_status(is_spoiler: bool, confidence: float) -> str:
    threshold = settings.SPOILER_CONFIDENCE_THRESHOLD
    if confidence >= threshold:
        return "HIDDEN" if is_spoiler else "PUBLIC"
    return "PENDING_REVIEW"


def _merge_candidates(
    vector_results: list[dict],
    keyword_results: list[dict],
    min_similarity: float = MIN_SIMILARITY,
) -> list[dict]:
    """Merge both recall paths, de-duplicated by paragraph index.

    Vector hits must clear ``min_similarity``; keyword hits are a lexical
    fallback and carry a raw count instead of a cosine score, so they are kept
    when the count is positive.  The previous version compared dicts with
    ``p not in vector_results``, which was both fragile and unordered.
    """
    merged: dict[int, dict] = {}
    for paragraph in vector_results:
        if float(paragraph.get("similarity", 0.0)) >= min_similarity:
            merged[paragraph["para_index"]] = paragraph
    for paragraph in keyword_results:
        if paragraph["para_index"] in merged:
            continue
        if float(paragraph.get("similarity", 0.0)) > 0:
            merged[paragraph["para_index"]] = paragraph
    return [merged[index] for index in sorted(merged)]


class SpoilerDetector:
    def __init__(self, embedding_service, llm_service):
        self.embedding_service = embedding_service
        self.llm_service = llm_service

    def detect(self, comment: str, current_para_index: int, all_paragraphs: list[dict]) -> dict:
        if not all_paragraphs:
            raise ValueError("书籍没有段落，无法检测剧透")

        current_para = next(
            (p["content"] for p in all_paragraphs if p["para_index"] == current_para_index),
            None,
        )
        if current_para is None:
            raise ValueError(f"段落 {current_para_index} 不存在")

        vector_results = self.embedding_service.semantic_search(comment, all_paragraphs, top_k=5)
        keyword_results = self.embedding_service.keyword_search(comment, all_paragraphs, top_k=3)

        relevant = _merge_candidates(vector_results, keyword_results)
        future_paragraphs = [p for p in relevant if p["para_index"] > current_para_index]

        if future_paragraphs:
            total_chars = sum(len(p["content"]) for p in future_paragraphs)
            if total_chars > MAX_CONTEXT_CHARS:
                future_contents = [_extract_snippet(p["content"], comment) for p in future_paragraphs]
            else:
                future_contents = [p["content"] for p in future_paragraphs]
            no_context = False
        else:
            future_contents = []
            no_context = True

        llm_result = self.llm_service.judge_spoiler(
            comment=comment,
            current_paragraph=current_para,
            future_paragraphs=future_contents,
            no_context=no_context,
        )

        status = determine_status(llm_result["is_spoiler"], llm_result["confidence"])

        return {
            "is_spoiler": llm_result["is_spoiler"],
            "confidence": llm_result["confidence"],
            "reason": llm_result["reason"],
            "status": status,
        }
