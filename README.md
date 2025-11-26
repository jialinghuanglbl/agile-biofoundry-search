# Agile Biofoundry — Article Search & Analysis

A Streamlit app for building a custom article library and running AI-powered analysis on search results.

## Features

- **Manual Article Upload**: Add articles with title, authors, abstract, URL, and full text via a sidebar form
- **Local Storage**: Articles persist in `data/articles.json`
- **TF-IDF Search**: Fast keyword/semantic search across articles
- **AI Analysis**: Get ChatGPT-powered summaries and insights from OpenAI API
- **Article Management**: View, expand, and delete articles from the sidebar

## Setup

### 1. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### 2. Configure OpenAI API (Optional but Recommended)

To enable AI analysis, provide your OpenAI API key. Choose one:

**Option A: Environment Variable** (recommended for deployment)
```bash
export OPENAI_API_KEY="sk-..."
```

**Option B: Streamlit Secrets** (local development)
Create `.streamlit/secrets.toml`:
```toml
openai_api_key = "sk-..."
```

### 3. Run the App

```bash
streamlit run streamlit_app.py
```

The app will open at `http://localhost:8501`.

## Usage

### Add Articles

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

**Cost**: Each analysis call costs ~$0.01–$0.05 depending on article length (see [OpenAI pricing](https://openai.com/pricing)).

## Deployment

### Local
```bash
streamlit run streamlit_app.py
```

### Docker
```bash
docker build -t agile-biofoundry .
docker run -p 8501:8501 -e OPENAI_API_KEY="sk-..." agile-biofoundry
```

### Streamlit Cloud
1. Push repo to GitHub
2. Deploy at [streamlit.io/cloud](https://share.streamlit.io)
3. Add `OPENAI_API_KEY` secret in app settings

## Troubleshooting

**"OpenAI API key not configured"**
- Set `OPENAI_API_KEY` env var or add to `.streamlit/secrets.toml`
- Ensure the key is valid (starts with `sk-`)

**"No matching articles found"**
- Add more articles with substantive text/abstracts
- Try simpler queries (fewer words, common terms)

**App is slow**
- TF-IDF is computed on each search; for >1000 articles, consider caching the vectorizer to `.streamlit/cache_resources`