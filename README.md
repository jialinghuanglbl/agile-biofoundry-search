# Agile Biofoundry — Article Search & Analysis

A **Streamlit** app for importing academic articles from your Lean Library workspace, extracting content, and analyzing them with AI.

## Quick Start

1. **Fetch articles from your Lean Library**:
   - Paste your Sciwheel API endpoint and collection ID
   - Provide authentication cookies (from DevTools)
   - Import in batches to avoid timeouts

2. **Extract content** from article URLs:
   - Automatically downloads HTML and PDFs
   - Extracts readable text
   - Handles institutional paywalls (with proper auth)

3. **Search** your library:
   - TF-IDF based relevance ranking
   - AI-powered analysis (OpenAI)

## Getting Started

### Setup

1. Clone/open this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Set OpenAI API key:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

4. Run the app:
   ```bash
   streamlit run streamlit_app.py
   ```

### Import Articles from Lean Library

1. **Get API endpoint and cookies:**
   - Log in to your Lean Library workspace
   - Open DevTools (F12) → Network tab → Filter XHR
   - Find the `items` XHR request
   - Copy the request URL → paste as "API endpoint"
   - Go to Application → Cookies → Copy all cookies for sciwheel.com
   - Paste into "Paste cookies here" text area

2. **Set collection ID:**
   - URL format: `https://sciwheel.com/work/#/items?collection=XXXXX`
   - Extract `XXXXX` as your collection ID

3. **Validate cookies:**
   - Click "Validate cookies" button
   - Should see ✅ "Cookies look valid"

4. **Import in batches:**
   - Set "Batch size" (e.g., 10)
   - Click "Import next batch and extract content"
   - Watch progress and review import log
   - Click "Reset batch position" to start over

### Access Restricted Content

**Many journals require authentication.** See:
- **[BLOCKED_CONTENT_GUIDE.md](./BLOCKED_CONTENT_GUIDE.md)** — Why some articles can't be accessed
- **[INSTITUTIONAL_ACCESS_SETUP.md](./INSTITUTIONAL_ACCESS_SETUP.md)** — How to authenticate with your institution

**Quick summary:**
1. Log into your institution's account on a journal site
2. Copy cookies from DevTools
3. Paste into app's cookie field
4. Re-run import

### Manage Articles

In the sidebar **Manage Articles** section:
- View all imported articles
- Click 🗑️ to delete

### Search & Analyze

1. Open **Search & Analysis** section
2. Enter a query (e.g., "What are the key findings about cell growth?")
3. Adjust "Results" slider to control how many articles to return
4. Review matched articles sorted by relevance
5. (Optional) Click "Get AI Analysis" for AI-powered summary

## Data Storage

Articles are stored in `data/articles.json` as JSON:
```json
[
  {
    "id": "uuid",
    "title": "Article Title",
    "authors": [],
    "abstract": "...",
    "url": "https://...",
    "text": "Full extracted text...",
    "created_at": "2025-12-10T12:00:00",
    "import_status": "success"
  }
]
```

You can edit this file directly for bulk imports or migrations.

## How Search Works

1. **TF-IDF Vectorization**: Articles are converted to sparse vectors using term frequency and inverse document frequency
2. **Cosine Similarity**: User query is vectorized and compared to all articles
3. **Ranking**: Results sorted by relevance score (0–1)

## How AI Analysis Works

1. Top matching articles are retrieved from search
2. Article text is concatenated and sent to OpenAI's `gpt-4o-mini` model
3. Model generates analysis answering your query based on the articles
4. Response displayed in the app (typically 500–1500 characters)