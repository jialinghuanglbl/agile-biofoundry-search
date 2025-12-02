# Agile Biofoundry — Article Search & Analysis

1. Open the sidebar **Add Article** form
2. Fill in:
   - **Title** (required)
   - **Authors** (comma-separated, optional)
   - **Abstract / Summary** (optional)
   - **URL / DOI** (optional)
   - **Full Text** (optional, improves search quality)
3. Click **Add Article**

### Search & Analyze

1. Enter a query in the **Search & Analysis** box
2. Adjust **Results** slider to control how many articles to return
3. Review matched articles (sorted by relevance)
4. Click **Get AI Analysis** to run an AI summary over the top results

### Manage Articles

1. Open the sidebar **Manage Articles** expander
2. View all articles
3. Click 🗑️ to delete an article

## Data Storage

Articles are stored in `data/articles.json` as a JSON array:
```json
[
  {
    "id": "uuid",
    "title": "...",
    "authors": ["...", "..."],
    "abstract": "...",
    "url": "...",
    "text": "...",
    "created_at": "2025-11-26T..."
  }
]
```

You can edit `data/articles.json` directly to bulk import articles or migrate data.

## How Search Works

1. **TF-IDF Vectorization**: Articles are converted to sparse vectors using term frequency and inverse document frequency
2. **Cosine Similarity**: User query is vectorized and compared to all articles
3. **Ranking**: Results sorted by relevance score (0–1)

## How AI Analysis Works

1. Top matching articles are retrieved from search
2. Article text is concatenated and sent to OpenAI's `gpt-4o-mini` model
3. Model generates analysis answering your query based on the articles
4. Response displayed in the app (typically 500–1500 characters)