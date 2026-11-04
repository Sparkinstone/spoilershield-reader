#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
insert_sample_comments.py
直接向 book_id=9 的若干段落写入示例评论（跳过 AI 检测），方便前端展示测试。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Paragraph, Comment

BOOK_ID = 9

# (para_index, content, is_spoiler, confidence, ai_reason, status)
SAMPLES = [
    (1,  "这段描写非常细腻，把雷雨夜的氛围渲染得淋漓尽致，让人身临其境。",
     False, 0.92, "只表达感受，未涉及后续剧情", "PUBLIC"),
    (1,  "作者从童年创伤引出主角对球状闪电的执念，后来球闪竟成了战争武器——这个转折令人唏嘘。",
     True,  0.96, "提及球状闪电被武器化的后续剧情", "HIDDEN"),
    (5,  "刘慈欣的科幻世界观总是让我叹服，科学细节与情感叙事融合得恰到好处。",
     False, 0.88, "泛泛评价，无具体剧透", "PUBLIC"),
    (5,  "没想到陈博士最后以量子态形式消失了，太震撼了！",
     True,  0.97, "直接剧透角色结局", "HIDDEN"),
    (10, "这章节节奏偏慢，但细读起来每一句话都在铺垫后面的大爆发，很耐人寻味。",
     False, 0.85, "感受性评价，无剧透", "PUBLIC"),
    (10, "林云这个角色很立体，她对武器的偏执和对爱情的克制最终都有了交代。",
     True,  0.90, "涉及林云角色结局走向", "HIDDEN"),
    (20, "书中对球状闪电物理特性的推导既严谨又充满想象力，读来酣畅。",
     False, 0.93, "讨论科学设定，无剧透", "PUBLIC"),
    (20, "量子玫瑰那段实验后来被证实是关键突破，直接推动了宏电子武器的诞生。",
     True,  0.95, "剧透实验结果与武器发展", "HIDDEN"),
    (30, "主角的执念贯穿全书，从少年到成年，这种人物弧线写得令人动容。",
     False, 0.87, "角色评价，无具体情节剧透", "PUBLIC"),
    (30, "最后的决战场景中球状闪电吞噬了整支部队，战争的荒诞感扑面而来。",
     True,  0.98, "直接描述结局战斗场景", "HIDDEN"),
    (50, "科幻感很强，但人物情感线也没有被忽视，两条线编织得很自然。",
     False, 0.89, "整体评价，无剧透", "PUBLIC"),
    (80, "对宏观量子态的科学构想非常大胆，刘慈欣真的很会讲故事。",
     False, 0.91, "科学评价，无剧透", "PUBLIC"),
    (100, "读到这里才发现之前每一个细节都是伏笔，这种布局太厉害了。",
     False, 0.83, "结构评价，无具体剧透", "PENDING_REVIEW"),
    (120, "陈博士和林云之间的感情线，含蓄却深刻，让人回味无穷。",
     False, 0.86, "情感评价，无剧透", "PUBLIC"),
    (150, "书末揭示球状闪电是宏电子激发态的设定简直绝了，完全颠覆认知。",
     True,  0.94, "剧透书末核心设定", "HIDDEN"),
]


def main():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for (para_index, content, is_spoiler, confidence, ai_reason, status) in SAMPLES:
            para = db.query(Paragraph).filter(
                Paragraph.book_id == BOOK_ID,
                Paragraph.para_index == para_index,
            ).first()
            if not para:
                print(f"[WARN] para_index={para_index} 不存在，跳过")
                skipped += 1
                continue

            comment = Comment(
                paragraph_id=para.id,
                book_id=BOOK_ID,
                content=content,
                is_spoiler=is_spoiler,
                confidence=confidence,
                ai_reason=ai_reason,
                status=status,
            )
            db.add(comment)
            inserted += 1

        db.commit()
        print(f"完成：插入 {inserted} 条评论，跳过 {skipped} 条。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
