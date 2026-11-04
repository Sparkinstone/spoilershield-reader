# Final Instruction for Claude Code: Build "SpoilerShield MVP"

## Project Objective
Build a web application called **SpoilerShield** - an AI-powered "anti-spoiler reader" MVP. Users can upload ebooks, read them, and comment on any paragraph. The system will automatically detect if a comment contains **spoilers for future content** and handle it appropriately.

## Core Feature List (MVP Scope)
1. **File Support**: Upload and render PDF, EPUB, and TXT files as readable text with natural paragraphs in the web interface.
2. **Reading & Commenting**:
   - Reading interface (similar to WeChat Read iPad): Book text on the left, comment section for the current paragraph on the right.
   - Users can click/highlight any paragraph to open a sidebar and write a comment.
3. **AI Automatic Spoiler Detection (Core)**:
   - **Trigger**: When a user submits a comment.
   - **Pipeline**:
     1. **Semantic Search (RAG)**: Find the 3 paragraphs in the entire book that are most semantically similar to the comment.
     2. **Position Check**: Check if any of those 3 paragraphs come **after** the paragraph being commented on.
     3. **AI Judgment**: Send the "comment", "current paragraph", and any "relevant future paragraphs" to LLM (GPT-4o) to determine if it's a spoiler.
     4. **Automatic Handling**: Based on AI confidence (`confidence`):
        - confidence >= 0.7: Automatically mark as "spoiler" (hidden) or "non-spoiler" (public).
        - confidence < 0.7: Mark as "pending review" (visible only to the commenter).
4. **Comment Display**:
   - Public comments: Display normally.
   - Spoiler comments: Blurred with "Click to reveal spoiler" overlay.
   - Global toggle: A button to show/hide all spoiler-marked comments.
5. **Admin Panel**:
   - List all "pending review" comments.
   - Show AI's reasoning and confidence score.
   - Provide buttons for manual moderation ("Approve", "Mark as Spoiler", "Delete").
6. **Testing & Data Script (Critical)**:
   - Provide a background script to **batch insert mock comments** into any paragraph of a specified book.
   - The script should control the ratio of spoiler vs. non-spoiler comments.
   - After execution, generate a simple **test report** showing AI judgment accuracy (compared to script's preset labels).

## Application Architecture (High-Level)
- **Backend**: FastAPI (Python)
- **Frontend**: HTMX + Jinja2 templates + Tailwind CSS
- **Database**: SQLite
- **File Parsing**: Use appropriate libraries to parse books into a **list of paragraphs**. Each paragraph records:
  - `id`
  - `book_id`
  - `para_index` (sequential position in book, starting at 0)
  - `page_num` (original page number)
  - `content` (paragraph plain text)
- **AI Services**:
  - **Embedding**: Use a lightweight local model (e.g., `sentence-transformers`) to generate semantic vectors for each paragraph, stored in DB for fast retrieval.
  - **LLM Call**: Call GPT-4o API. The prompt must be engineered to return fixed-format JSON.
- **Database Tables**:
  - `books`: Book metadata.
  - `paragraphs`: Paragraphs with content and vectors.
  - `comments`: **Must include fields**: `id`, `paragraph_id`, `content`, `status` (`PENDING_REVIEW`/`PUBLIC`/`HIDDEN`), `is_spoiler` (boolean), `confidence` (float), `ai_reason` (text).

## Required Response Formats
- **LLM Prompt**: Must instruct LLM to return JSON:
json

{

"is_spoiler": true,

"confidence": 0.85,

"reason": "This comment reveals the killer's identity, which isn't revealed until page 50."

}
- **Key API Endpoints**:
  - `POST /upload`: Upload file, trigger parsing and indexing.
  - `GET /book/{book_id}`: Get book content for reader rendering.
  - `POST /comment`: Submit comment, trigger AI spoiler detection.
  - `GET /admin/pending`: Get pending review comments.
  - `POST /admin/action`: Execute admin moderation actions.

## Delivery Requirements
1. **Complete Runnable Code**: All Python files, HTML templates, static files, `requirements.txt`, and `.env.example`.
2. **Clear Setup Instructions**: A `README.md` explaining how to install dependencies, set environment variables, and run the application.
3. **One-Click Test Script**: A standalone Python script in the root directory (e.g., `generate_test_comments.py`). Its **usage** and **output report format** must be documented in `README.md`.
4. **Configuration**: The AI confidence threshold (0.7) must be read from the `.env` file.

## Final Deliverable Form
After running the application, I should be able to:
1. Visit `http://localhost:8000` and see the upload interface.
2. Upload a PDF/EPUB/TXT file.
3. Enter the reading interface, click a paragraph, and post a comment.
4. Immediately see the comment processed by AI (public/hidden/pending).
5. Visit `http://localhost:8000/admin` to review low-confidence comments.
6. Run the test script to insert 100 mock comments into a book and view an AI accuracy report.