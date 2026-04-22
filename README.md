# SpoilerShield MVP

AI-powered anti-spoiler reader. Upload ebooks, read them, comment on paragraphs — AI automatically detects and hides spoiler comments.

## Setup

1. Clone the repo and enter the directory
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your OpenAI API key:
   ```bash
   cp .env.example .env
   ```
5. Run the application:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Usage

1. Visit `http://localhost:8000` — upload a PDF, EPUB, or TXT file
2. Click "Read" to enter the reading interface
3. Click any paragraph to open the comment sidebar
4. Post a comment — AI will automatically detect spoilers
5. Visit `http://localhost:8000/admin` to review low-confidence comments

## Test Script

Generate mock comments and view AI accuracy report:

```bash
python generate_test_comments.py --book-id 1 --num-comments 100 --spoiler-ratio 0.3
```

**Arguments:**
- `--book-id`: ID of the book (shown after upload)
- `--num-comments`: Number of comments to generate (default: 100)
- `--spoiler-ratio`: Ratio of spoiler vs non-spoiler comments (default: 0.3)

**Report output includes:**
- Overall accuracy
- Spoiler precision and recall
- True/false positive/negative counts

## Configuration

All settings are in `.env`:
- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_API_BASE`: OpenAI API base URL (default: https://api.openai.com/v1)
- `SPOILER_CONFIDENCE_THRESHOLD`: AI confidence threshold for auto-handling (default: 0.7)
- `LLM_MODEL`: LLM model name (default: gpt-4o)
- `EMBEDDING_MODEL`: Sentence-transformers model (default: all-MiniLM-L6-v2)
