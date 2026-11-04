# Test Comment Seeding & Accuracy Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为《球状闪电》生成 200 条带 ground-truth 标签的中文测试评论（100 条剧透 / 100 条非剧透），通过 SpoilerDetector 运行，输出准确率报告。

**Architecture:** 一个独立 CLI 脚本 `scripts/seed_test_comments.py`，分三阶段运行：①调用 Claude API 针对书的前半段落批量生成带标签评论并保存为 JSON；②逐条调用现有 `SpoilerDetector` 进行检测并记录 AI 判断；③与 ground truth 对比计算 precision / recall / accuracy 并打印报告。结果同时写入 `scripts/seed_result.json` 以备复查。

**Tech Stack:** Python 3.11, anthropic SDK (claude-3-5-sonnet), SQLAlchemy (直接复用 app 的 DB session), 现有 `SpoilerDetector` / `EmbeddingService` / `LLMService`

---

## File Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/seed_test_comments.py` | 新建 | 主脚本：生成、检测、报告 |
| `scripts/seed_result.json` | 运行时生成 | 每条评论的 ground truth + AI 结果 |

不需要修改任何 app 代码。

---

### Task 1: 查找《球状闪电》的 book_id 并确定前半段落范围

**Files:**
- Run only (no file changes)

- [ ] **Step 1: 查询数据库确认书已导入**

```bash
cd D:\Learn\workshop\CommentMask
python -c "
from app.database import SessionLocal
from app.models import Book, Paragraph
db = SessionLocal()
books = db.query(Book).all()
for b in books:
    print(f'id={b.id}  title={b.title}  paragraphs={b.total_paragraphs}')
db.close()
"
```

Expected: 输出包含《球状闪电》的一行，记下其 `id` 和 `total_paragraphs`。

- [ ] **Step 2: 查看前几段内容，确认段落格式正常**

```bash
python -c "
from app.database import SessionLocal
from app.models import Paragraph
db = SessionLocal()
paras = db.query(Paragraph).filter(Paragraph.book_id == 1).order_by(Paragraph.para_index).limit(5).all()
for p in paras:
    print(f'[{p.para_index}] {p.content[:80]}')
db.close()
"
```

> 把 `book_id == 1` 换成上一步确认的真实 id。

Expected: 打印 5 段可读中文内容。

---

### Task 2: 创建脚本骨架并实现评论生成阶段

**Files:**
- Create: `scripts/seed_test_comments.py`

- [ ] **Step 1: 创建脚本，写入完整骨架**

```python
#!/usr/bin/env python3
"""
seed_test_comments.py
生成 200 条带 ground-truth 标签的中文测试评论，运行剧透检测，输出准确率报告。

用法:
    python scripts/seed_test_comments.py --book-id <id>
"""
import sys
import os
import json
import argparse
import random
import time

# 让脚本能 import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from app.database import SessionLocal
from app.models import Book, Paragraph, Comment
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.spoiler_detector import SpoilerDetector
from app.config import settings

TOTAL_COMMENTS = 200
SPOILER_COUNT = 100
NON_SPOILER_COUNT = 100
RESULT_PATH = os.path.join(os.path.dirname(__file__), "seed_result.json")


def get_front_half_paragraphs(db, book_id: int) -> list[dict]:
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


def generate_comments_via_claude(paragraphs: list[dict]) -> list[dict]:
    """
    调用 Claude API，针对随机选取的段落生成带标签的中文测试评论。
    返回 list of:
      {"para_index": int, "paragraph_id": int, "content": str, "ground_truth": bool}
    """
    client = anthropic.Anthropic(api_key=settings.OPENAI_API_KEY)  # key 复用同一个环境变量
    # 如果有独立的 ANTHROPIC_API_KEY 则优先使用
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        client = anthropic.Anthropic(api_key=anthropic_key)

    results = []

    # 分两批：100 条剧透 + 100 条非剧透
    batches = [
        (SPOILER_COUNT, True,  "剧透"),
        (NON_SPOILER_COUNT, False, "非剧透"),
    ]

    for count, is_spoiler, label in batches:
        # 从前半段落中随机抽取 count 个段落（允许重复，模拟真实情况）
        selected = random.choices(paragraphs, k=count)

        for i, para in enumerate(selected):
            prompt = _build_prompt(para["content"], is_spoiler)
            print(f"  生成{label}评论 {i+1}/{count} (para_index={para['para_index']})...", end="\r")

            try:
                response = client.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=150,
                    messages=[{"role": "user", "content": prompt}],
                )
                comment_text = response.content[0].text.strip()
            except Exception as e:
                print(f"\n  ⚠️  生成失败 (para_index={para['para_index']}): {e}")
                comment_text = "（生成失败，跳过）"

            results.append({
                "para_index": para["para_index"],
                "paragraph_id": para["id"],
                "content": comment_text,
                "ground_truth": is_spoiler,
            })

            # 简单限速，避免触发 API rate limit
            time.sleep(0.3)

        print(f"\n  ✅ {label}评论生成完毕")

    return results


def _build_prompt(paragraph_content: str, is_spoiler: bool) -> str:
    if is_spoiler:
        return f"""你正在阅读科幻小说《球状闪电》。以下是书中某处的一段文字：

---
{paragraph_content[:400]}
---

请以读者身份，写一条**中文评论**（20-60字），评论内容必须**泄露后续剧情**（比如后面发生的重要事件、角色命运或关键反转）。
直接输出评论正文，不要加引号或任何前缀。"""
    else:
        return f"""你正在阅读科幻小说《球状闪电》。以下是书中某处的一段文字：

---
{paragraph_content[:400]}
---

请以读者身份，写一条**中文评论**（20-60字），只谈对这段文字的感受或分析，**不能透露任何后续剧情**。
直接输出评论正文，不要加引号或任何前缀。"""


def run_detection(comments: list[dict], book_id: int, db) -> list[dict]:
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
    para_dicts = [{"para_index": p.para_index, "content": p.content} for p in all_paras]

    for i, item in enumerate(comments):
        print(f"  检测评论 {i+1}/{len(comments)} ...", end="\r")
        if item["content"] == "（生成失败，跳过）":
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
            print(f"\n  ⚠️  检测失败: {e}")
            item["ai_is_spoiler"] = None
            item["ai_confidence"] = None
            item["ai_reason"] = str(e)
            item["ai_status"] = "ERROR"

    print(f"\n  ✅ 检测完毕")
    return comments


def compute_accuracy(comments: list[dict]) -> dict:
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
    print("📊 剧透检测准确率报告")
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
            print(f"❌ 找不到 book_id={args.book_id}")
            sys.exit(1)
        print(f"📚 目标书籍: 《{book.title}》 (id={book.id}, 共 {book.total_paragraphs} 段)")

        if args.skip_generate and os.path.exists(RESULT_PATH):
            print(f"⏩ 加载已有评论: {RESULT_PATH}")
            with open(RESULT_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            comments = saved.get("comments", [])
        else:
            # 阶段 1: 生成评论
            print(f"\n🖊️  阶段 1/2: 生成 {TOTAL_COMMENTS} 条测试评论...")
            paragraphs = get_front_half_paragraphs(db, args.book_id)
            print(f"  前半部分段落数: {len(paragraphs)}")
            comments = generate_comments_via_claude(paragraphs)

        # 阶段 2: 运行检测
        print(f"\n🔍 阶段 2/2: 运行剧透检测...")
        comments = run_detection(comments, args.book_id, db)

        # 保存结果
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump({"book_id": args.book_id, "comments": comments}, f, ensure_ascii=False, indent=2)
        print(f"\n💾 结果已保存: {RESULT_PATH}")

        # 阶段 3: 计算并打印报告
        metrics = compute_accuracy(comments)
        print_report(metrics)

    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 确认 anthropic 包已安装**

```bash
cd D:\Learn\workshop\CommentMask
pip show anthropic
```

Expected: 显示 anthropic 版本信息。若未安装，运行：

```bash
pip install anthropic
```

- [ ] **Step 3: 确认 ANTHROPIC_API_KEY 环境变量已设置（或复用 OPENAI_API_KEY）**

```bash
python -c "import os; print('ANTHROPIC_API_KEY:', bool(os.getenv('ANTHROPIC_API_KEY'))); print('OPENAI_API_KEY:', bool(os.getenv('OPENAI_API_KEY')))"
```

Expected: 至少一个为 `True`。

---

### Task 3: 运行脚本，生成评论并执行检测

**Files:**
- Run: `scripts/seed_test_comments.py`
- Generated: `scripts/seed_result.json`

- [ ] **Step 1: 用真实 book_id 运行脚本**

```bash
cd D:\Learn\workshop\CommentMask
python scripts/seed_test_comments.py --book-id <从Task1确认的id>
```

Expected:
```
📚 目标书籍: 《球状闪电》 (id=X, 共 XXXX 段)

🖊️  阶段 1/2: 生成 200 条测试评论...
  前半部分段落数: XXX
  生成剧透评论 100/100
  ✅ 剧透评论生成完毕
  生成非剧透评论 100/100
  ✅ 非剧透评论生成完毕

🔍 阶段 2/2: 运行剧透检测...
  检测评论 200/200
  ✅ 检测完毕

💾 结果已保存: scripts/seed_result.json

==================================================
📊 剧透检测准确率报告
==================================================
...
```

- [ ] **Step 2: 如果只想重跑检测（不重新生成评论），使用 --skip-generate**

```bash
python scripts/seed_test_comments.py --book-id <id> --skip-generate
```

Expected: 跳过生成阶段，直接打印报告。

- [ ] **Step 3: 查看详细结果样本**

```bash
python -c "
import json
with open('scripts/seed_result.json', encoding='utf-8') as f:
    data = json.load(f)
for c in data['comments'][:3]:
    print(f'ground_truth={c[\"ground_truth\"]}  ai={c[\"ai_is_spoiler\"]}  conf={c[\"ai_confidence\"]}')
    print(f'  评论: {c[\"content\"][:60]}')
    print()
"
```

Expected: 打印前 3 条评论的 ground truth、AI 判断和置信度。

---

### Task 4: Commit

**Files:**
- `scripts/seed_test_comments.py`

- [ ] **Step 1: Commit 脚本（不提交 seed_result.json，内含大量 LLM 输出）**

```bash
cd D:\Learn\workshop\CommentMask
git add scripts/seed_test_comments.py
git commit -m "feat: add test comment seeding & accuracy evaluation script"
```

Expected: commit 成功。
