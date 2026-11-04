#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seed_test_comments.py
生成带 ground-truth 标签的中文测试评论，运行剧透检测，输出准确率报告。

用法:
    python scripts/seed_test_comments.py --book-id <id>
"""
import sys
import os
import io
import json
import argparse
import random
import time

# 修复 Windows 控制台 GBK 编码问题
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 让脚本能 import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from app.database import SessionLocal
from app.models import Book, Paragraph, Comment
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.spoiler_detector import SpoilerDetector
from app.config import settings

TOTAL_COMMENTS = 1000
SPOILER_COUNT = 300
NON_SPOILER_COUNT = 700
RESULT_PATH = os.path.join(os.path.dirname(__file__), "seed_result.json")


def get_front_half_paragraphs(db, book_id: int) -> list:
    """返回书前半部分段落（para_index 升序），格式为 list of dict。"""
    all_paras = (
        db.query(Paragraph)
        .filter(Paragraph.book_id == book_id)
        .order_by(Paragraph.para_index)
        .all()
    )
    half = len(all_paras) // 2
    front = all_paras[:half]
    return [{"id": p.id, "para_index": p.para_index, "content": p.content} for p in front]


BATCH_SIZE = 10  # 每次 API 调用生成的评论数


def generate_comments_via_llm(paragraphs: list) -> list:
    """
    调用配置的 LLM（默认 DeepSeek Flash，任意 OpenAI 兼容端点均可），
    批量生成带标签的中文测试评论。
    每次 API 调用传入 BATCH_SIZE 个段落，一次返回 BATCH_SIZE 条评论，大幅提速。
    返回 list of:
      {"para_index": int, "paragraph_id": int, "content": str, "ground_truth": bool}
    """
    if not settings.LLM_API_KEY:
        print("[ERROR] 未配置 LLM_API_KEY / OPENAI_API_KEY，无法生成测试评论", flush=True)
        sys.exit(1)
    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=settings.LLM_TIMEOUT,
    )
    results = []

    batches = [
        (SPOILER_COUNT, True,  "剧透"),
        (NON_SPOILER_COUNT, False, "非剧透"),
    ]

    for count, is_spoiler, label in batches:
        selected = random.choices(paragraphs, k=count)

        # 分批处理
        for batch_start in range(0, count, BATCH_SIZE):
            batch = selected[batch_start:batch_start + BATCH_SIZE]
            batch_end = batch_start + len(batch)
            print(f"  生成{label}评论 {batch_start+1}-{batch_end}/{count} ...", end="\r", flush=True)

            prompt = _build_batch_prompt(batch, is_spoiler)
            try:
                response = client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    max_tokens=80 * len(batch),
                    temperature=1.0,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = (response.choices[0].message.content or "").strip()
                comments_text = _parse_batch_response(raw, len(batch))
            except Exception as e:
                print(f"\n  [WARN] 批量生成失败 (batch {batch_start+1}-{batch_end}): {e}", flush=True)
                comments_text = ["(生成失败，跳过)"] * len(batch)

            for para, comment_text in zip(batch, comments_text):
                results.append({
                    "para_index": para["para_index"],
                    "paragraph_id": para["id"],
                    "content": comment_text,
                    "ground_truth": is_spoiler,
                })

            time.sleep(0.2)

        print(f"\n  [{label}评论生成完毕]", flush=True)

    return results


def _build_batch_prompt(paras: list, is_spoiler: bool) -> str:
    if is_spoiler:
        instruction = "必须泄露后续剧情（重要事件/角色命运/关键反转）"
    else:
        instruction = "只谈感受或分析，不透露后续剧情"

    segments = "\n".join(
        f"[{i+1}] {p['content'][:150]}" for i, p in enumerate(paras)
    )
    return f"""你是一个读者，正在阅读科幻小说《球状闪电》。以下是书中 {len(paras)} 个不同片段：

{segments}

请为每个片段各写一条中文评论（20-50字），{instruction}。
按如下格式输出，每行一条，编号对应：
1. <评论>
2. <评论>
...
只输出编号和评论，不要其他内容。"""


def _parse_batch_response(raw: str, expected: int) -> list:
    """从批量返回文本中解析出 expected 条评论。不足则用占位符补齐。"""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    comments = []
    for line in lines:
        # 匹配 "1. xxx" 或 "1、xxx" 格式
        if line and line[0].isdigit():
            dot_pos = -1
            for j, ch in enumerate(line):
                if ch in '.、。':
                    dot_pos = j
                    break
            if dot_pos != -1:
                comments.append(line[dot_pos+1:].strip())
    # 若解析数量不符，补齐或截断
    while len(comments) < expected:
        comments.append("(生成失败，跳过)")
    return comments[:expected]


def run_detection(comments: list, book_id: int, db) -> list:
    """对每条评论运行 SpoilerDetector，把 AI 结果写回 dict。"""
    embedding_service = EmbeddingService()
    llm_service = LLMService()
    detector = SpoilerDetector(embedding_service, llm_service)

    all_paras = (
        db.query(Paragraph)
        .filter(Paragraph.book_id == book_id)
        .order_by(Paragraph.para_index)
        .all()
    )
    para_dicts = [
        {
            "para_index": p.para_index,
            "content": p.content,
            "embedding": embedding_service.json_to_embedding(p.embedding_blob) if p.embedding_blob else None,
        }
        for p in all_paras
    ]

    for i, item in enumerate(comments):
        print(f"  检测评论 {i+1}/{len(comments)} ...", end="\r")
        if item["content"] in ("（生成失败，跳过）", "(生成失败，跳过)"):
            item["ai_is_spoiler"] = None
            item["ai_confidence"] = None
            item["ai_reason"] = "skipped"
            item["ai_status"] = "SKIPPED"
            continue

        try:
            result = detector.detect(
                comment=item["content"],
                current_para_index=item["para_index"],
                all_paragraphs=para_dicts,
            )
            item["ai_is_spoiler"] = result["is_spoiler"]
            item["ai_confidence"] = result["confidence"]
            item["ai_reason"] = result["reason"]
            item["ai_status"] = result["status"]
        except Exception as e:
            print(f"\n  [WARN] 检测失败: {e}", flush=True)
            item["ai_is_spoiler"] = None
            item["ai_confidence"] = None
            item["ai_reason"] = str(e)
            item["ai_status"] = "ERROR"

    print(f"\n  [检测完毕]", flush=True)
    return comments


def compute_accuracy(comments: list) -> dict:
    """
    只统计 ai_is_spoiler 不为 None 的条目（跳过失败项）。
    返回 precision, recall, accuracy 及混淆矩阵。
    """
    valid = [c for c in comments if c.get("ai_is_spoiler") is not None]
    skipped = len(comments) - len(valid)

    tp = sum(1 for c in valid if c["ground_truth"] is True  and c["ai_is_spoiler"] is True)
    tn = sum(1 for c in valid if c["ground_truth"] is False and c["ai_is_spoiler"] is False)
    fp = sum(1 for c in valid if c["ground_truth"] is False and c["ai_is_spoiler"] is True)
    fn = sum(1 for c in valid if c["ground_truth"] is True  and c["ai_is_spoiler"] is False)

    accuracy  = (tp + tn) / len(valid) if valid else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "total": len(comments),
        "valid": len(valid),
        "skipped": skipped,
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def print_report(metrics: dict):
    print("\n" + "=" * 50)
    print("剧透检测准确率报告")
    print("=" * 50)
    print(f"总评论数:   {metrics['total']}")
    print(f"有效评论:   {metrics['valid']}  (跳过: {metrics['skipped']})")
    print()
    print(f"混淆矩阵:")
    print(f"  TP (剧透判对):   {metrics['tp']}")
    print(f"  TN (非剧透判对): {metrics['tn']}")
    print(f"  FP (误报剧透):   {metrics['fp']}")
    print(f"  FN (漏报剧透):   {metrics['fn']}")
    print()
    print(f"Accuracy:  {metrics['accuracy'] * 100:.1f}%")
    print(f"Precision: {metrics['precision'] * 100:.1f}%")
    print(f"Recall:    {metrics['recall'] * 100:.1f}%")
    print(f"F1 Score:  {metrics['f1'] * 100:.1f}%")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="为指定书籍生成测试评论并评估剧透检测准确率")
    parser.add_argument("--book-id", type=int, required=True, help="数据库中的 book id")
    parser.add_argument("--skip-generate", action="store_true",
                        help="跳过生成阶段，直接从 seed_result.json 加载已有评论并重新检测")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        book = db.query(Book).filter(Book.id == args.book_id).first()
        if not book:
            print(f"找不到 book_id={args.book_id}")
            sys.exit(1)
        print(f"目标书籍: 《{book.title}》 (id={book.id}, 共 {book.total_paragraphs} 段)")

        if args.skip_generate and os.path.exists(RESULT_PATH):
            print(f"加载已有评论: {RESULT_PATH}")
            with open(RESULT_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            comments = saved.get("comments", [])
        else:
            # 阶段 1: 生成评论
            print(f"\n阶段 1/2: 生成 {TOTAL_COMMENTS} 条测试评论...")
            paragraphs = get_front_half_paragraphs(db, args.book_id)
            print(f"  前半部分段落数: {len(paragraphs)}")
            comments = generate_comments_via_llm(paragraphs)

        # 阶段 2: 运行检测
        print(f"\n阶段 2/2: 运行剧透检测...")
        comments = run_detection(comments, args.book_id, db)

        # 保存结果
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump({"book_id": args.book_id, "comments": comments}, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {RESULT_PATH}")

        # 阶段 3: 计算并打印报告
        metrics = compute_accuracy(comments)
        print_report(metrics)

    finally:
        db.close()


if __name__ == "__main__":
    main()
