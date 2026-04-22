"""
SpoilerShield Test Comment Generator & Accuracy Report

Usage:
    python generate_test_comments.py --book-id 1 --num-comments 100 --spoiler-ratio 0.3

This script:
1. Batch inserts mock comments into a specified book
2. Each comment is labeled as spoiler or non-spoiler with preset ground truth
3. Triggers AI spoiler detection for each comment
4. Generates an accuracy report comparing AI judgments vs ground truth labels
"""
import argparse
import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.models import Book, Paragraph, Comment
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.spoiler_detector import SpoilerDetector


SPOILER_COMMENTS = [
    "The main character dies at the end.",
    "The villain is actually the protagonist's father.",
    "The treasure was hidden in the cave all along.",
    "She betrays him in the final chapter.",
    "The butler is the murderer.",
    "They get married in the epilogue.",
    "The kingdom falls in the last battle.",
    "He sacrifices himself to save everyone.",
    "The secret letter reveals the truth.",
    "The real culprit was the detective's partner.",
]

NON_SPOILER_COMMENTS = [
    "This paragraph is beautifully written.",
    "I really enjoyed the descriptive language here.",
    "The author's style is very engaging.",
    "This reminds me of a similar scene in another book.",
    "Great character development in this section.",
    "The pacing of this part is excellent.",
    "I love the imagery used here.",
    "This is one of my favorite paragraphs.",
    "The dialogue here feels very natural.",
    "The atmosphere in this section is compelling.",
]


def generate_comments(book_id: int, num_comments: int, spoiler_ratio: float):
    init_db()
    db = SessionLocal()

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        print(f"Error: Book with id {book_id} not found.")
        db.close()
        return

    paragraphs = db.query(Paragraph).filter(Paragraph.book_id == book_id).order_by(Paragraph.para_index).all()
    if not paragraphs:
        print(f"Error: No paragraphs found for book id {book_id}.")
        db.close()
        return

    total_paras = len(paragraphs)
    num_spoilers = int(num_comments * spoiler_ratio)
    num_non_spoilers = num_comments - num_spoilers

    print("Loading embedding model...")
    emb_service = EmbeddingService()
    print("Initializing LLM service...")
    llm_service = LLMService()
    detector = SpoilerDetector(emb_service, llm_service)

    para_dicts = [{"para_index": p.para_index, "content": p.content} for p in paragraphs]

    results = []
    print(f"\nGenerating {num_comments} comments ({num_spoilers} spoilers, {num_non_spoilers} non-spoilers)...")

    for i in range(num_comments):
        is_ground_truth_spoiler = i < num_spoilers
        comment_templates = SPOILER_COMMENTS if is_ground_truth_spoiler else NON_SPOILER_COMMENTS
        comment_text = random.choice(comment_templates)

        if is_ground_truth_spoiler:
            para_index = random.randint(0, max(1, total_paras // 2))
        else:
            para_index = random.randint(0, total_paras - 1)

        paragraph = paragraphs[para_index]

        try:
            ai_result = detector.detect(
                comment=comment_text,
                current_para_index=para_index,
                all_paragraphs=para_dicts,
            )
        except Exception as e:
            print(f"  Error detecting comment {i}: {e}")
            ai_result = {"is_spoiler": None, "confidence": 0.0, "reason": str(e), "status": "PENDING_REVIEW"}

        ground_truth_label = "SPOILER" if is_ground_truth_spoiler else "NON_SPOILER"
        comment = Comment(
            paragraph_id=paragraph.id,
            book_id=book_id,
            content=comment_text,
            status=ai_result["status"],
            is_spoiler=ai_result["is_spoiler"],
            confidence=ai_result["confidence"],
            ai_reason=f"[GROUND_TRUTH:{ground_truth_label}] {ai_result['reason']}",
        )
        db.add(comment)
        db.commit()

        results.append({
            "ground_truth": is_ground_truth_spoiler,
            "ai_spoiler": ai_result["is_spoiler"],
            "confidence": ai_result["confidence"],
            "status": ai_result["status"],
        })

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{num_comments} comments...")

    db.close()
    generate_report(results, spoiler_ratio)


def generate_report(results: list[dict], spoiler_ratio: float):
    total = len(results)
    correct = 0
    true_spoilers = 0
    false_spoilers = 0
    true_non_spoilers = 0
    false_non_spoilers = 0

    for r in results:
        gt = r["ground_truth"]
        ai = r["ai_spoiler"]
        if gt and ai:
            true_spoilers += 1
            correct += 1
        elif gt and not ai:
            false_non_spoilers += 1
        elif not gt and ai:
            false_spoilers += 1
        else:
            true_non_spoilers += 1
            correct += 1

    accuracy = correct / total if total > 0 else 0
    spoiler_precision = true_spoilers / (true_spoilers + false_spoilers) if (true_spoilers + false_spoilers) > 0 else 0
    spoiler_recall = true_spoilers / (true_spoilers + false_non_spoilers) if (true_spoilers + false_non_spoilers) > 0 else 0

    print("\n" + "=" * 50)
    print("SPOILER SHIELD AI ACCURACY REPORT")
    print("=" * 50)
    print(f"Total comments:       {total}")
    print(f"Spoiler ratio:        {spoiler_ratio:.1%}")
    print(f"Overall accuracy:     {accuracy:.1%}")
    print(f"Spoiler precision:    {spoiler_precision:.1%}")
    print(f"Spoiler recall:       {spoiler_recall:.1%}")
    print(f"True positives:       {true_spoilers}")
    print(f"False positives:      {false_spoilers}")
    print(f"True negatives:       {true_non_spoilers}")
    print(f"False negatives:      {false_non_spoilers}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate test comments and accuracy report")
    parser.add_argument("--book-id", type=int, required=True, help="Book ID to insert comments into")
    parser.add_argument("--num-comments", type=int, default=100, help="Number of comments to generate")
    parser.add_argument("--spoiler-ratio", type=float, default=0.3, help="Ratio of spoiler comments (0.0-1.0)")
    args = parser.parse_args()
    generate_comments(args.book_id, args.num_comments, args.spoiler_ratio)
