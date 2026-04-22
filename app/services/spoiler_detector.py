from app.config import settings


def determine_status(is_spoiler: bool, confidence: float) -> str:
    threshold = settings.SPOILER_CONFIDENCE_THRESHOLD
    if confidence >= threshold:
        return "HIDDEN" if is_spoiler else "PUBLIC"
    return "PENDING_REVIEW"


class SpoilerDetector:
    def __init__(self, embedding_service, llm_service):
        self.embedding_service = embedding_service
        self.llm_service = llm_service

    def detect(self, comment: str, current_para_index: int, all_paragraphs: list[dict]) -> dict:
        relevant = self.embedding_service.semantic_search(comment, all_paragraphs, top_k=3)
        future_paragraphs = [p for p in relevant if p["para_index"] > current_para_index]

        current_para = next(
            (p["content"] for p in all_paragraphs if p["para_index"] == current_para_index),
            ""
        )

        future_contents = [p["content"] for p in future_paragraphs]
        llm_result = self.llm_service.judge_spoiler(
            comment=comment,
            current_paragraph=current_para,
            future_paragraphs=future_contents,
        )

        status = determine_status(llm_result["is_spoiler"], llm_result["confidence"])

        return {
            "is_spoiler": llm_result["is_spoiler"],
            "confidence": llm_result["confidence"],
            "reason": llm_result["reason"],
            "status": status,
        }
