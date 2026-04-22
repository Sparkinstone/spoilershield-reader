import json
from openai import OpenAI
from app.config import settings


class LLMService:
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
        )

    def judge_spoiler(
        self,
        comment: str,
        current_paragraph: str,
        future_paragraphs: list[str],
    ) -> dict:
        future_text = "\n".join(
            f"- {para}" for para in future_paragraphs
        ) if future_paragraphs else "No relevant future paragraphs found."

        prompt = f"""You are a spoiler detection AI for a book reading platform.

A reader posted a comment on a paragraph. Determine if this comment reveals information about events that happen AFTER the current paragraph.

**Current paragraph:**
{current_paragraph}

**Relevant paragraphs that appear LATER in the book:**
{future_text}

**The reader's comment:**
{comment}

Respond with ONLY a JSON object (no other text):
{{\"is_spoiler\": true/false, \"confidence\": 0.0-1.0, \"reason\": \"explanation\"}}"""

        response = self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_completion_tokens=200,
        )

        content = response.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        return {
            "is_spoiler": bool(result.get("is_spoiler", False)),
            "confidence": float(result.get("confidence", 0.0)),
            "reason": str(result.get("reason", "")),
        }
