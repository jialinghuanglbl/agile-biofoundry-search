import streamlit as st
import os
import json
import uuid
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Local article storage
DATA_DIR = Path("data")
ARTICLES_PATH = DATA_DIR / "articles.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Initialize OpenAI client (requires OPENAI_API_KEY env var or st.secrets)
def get_openai_client():
    api_key = st.secrets.get("openai_api_key") if hasattr(st, "secrets") else None
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return api_key

def load_articles():
    """Load articles from local storage."""
    if ARTICLES_PATH.exists():
        with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_articles(articles):
    """Save articles to local storage."""
    with open(ARTICLES_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

def add_article(title, authors, abstract, url, text):
    """Add a new article to the collection."""
    articles = load_articles()
    new_article = {
        "id": str(uuid.uuid4()),
        "title": title,
        "authors": authors if isinstance(authors, list) else [authors] if authors else [],
        "abstract": abstract,
        "url": url,
        "text": text,
        "created_at": datetime.now().isoformat(),
    }
    articles.append(new_article)
    save_articles(articles)
    return new_article

def delete_article(article_id):
    """Delete an article by ID."""
    articles = load_articles()
    articles = [a for a in articles if a["id"] != article_id]
    save_articles(articles)


def fetch_and_extract_html(url: str) -> str:
    """Fetch a URL and heuristically extract the main article text using BeautifulSoup.

    Strategy:
    - Try to find an <article> tag
    - Else try to find tag with role="main" or <main>
    - Else extract all <p> text and return the largest contiguous block
    """
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "agile-biofoundry-bot/1.0"})
        resp.raise_for_status()
        html = resp.content
    except Exception:
        return ""

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return ""

    # 1) <article>
    article_tag = soup.find("article")
    if article_tag:
        text = article_tag.get_text(separator="\n", strip=True)
        if len(text) > 200:
            return text

    # 2) main or role=main
    main_tag = soup.find("main") or soup.find(attrs={"role": "main"})
    if main_tag:
        text = main_tag.get_text(separator="\n", strip=True)
        if len(text) > 200:
            return text

    # 3) find the largest <div> or section by text length
    candidates = soup.find_all(["div", "section", "article", "main"])
    best = ""
    for c in candidates:
        t = c.get_text(separator="\n", strip=True)
        if len(t) > len(best):
            best = t
    if len(best) > 200:
        return best

    # 4) fallback: join all paragraph text
    ps = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
    if not ps:
        return ""
    # return the longest contiguous paragraph block (join all)
    joined = "\n\n".join(ps)
    return joined

def build_tfidf_index(articles):
    """Build a TF-IDF index from articles."""
    if not articles:
        return None, None
    texts = [a.get("text", "") or a.get("abstract", "") or "" for a in articles]

    # Strip and normalize
    texts = [t.strip() for t in texts]

    # If all texts are empty, there's nothing to vectorize
    if not any(texts):
        return None, None

    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=5000, min_df=1)
        X = vectorizer.fit_transform(texts)
        return vectorizer, X
    except ValueError:
        # Empty vocabulary (e.g., documents only contain stop words)
        return None, None


def search_articles(query, articles, top_k=5):
    """Search articles using TF-IDF similarity, with fallback to keyword matching."""
    if not articles:
        return []

    vectorizer, X = build_tfidf_index(articles)

    # If TF-IDF failed (empty vocab), fall back to simple keyword matching
    if vectorizer is None:
        query_lower = query.lower()
        scored = []
        for i, article in enumerate(articles):
            title = article.get("title", "").lower()
            abstract = article.get("abstract", "").lower()
            text = article.get("text", "").lower()

            score = 0.0
            if query_lower in title:
                score += 2.0
            score += title.count(query_lower) * 0.5
            score += abstract.count(query_lower) * 0.3
            score += text.count(query_lower) * 0.1

            if score > 0:
                scored.append((i, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = [(articles[i], score) for i, score in scored[:top_k]]
        return results

    # TF-IDF search
    q_vec = vectorizer.transform([query])
    sims = cosine_similarity(q_vec, X).flatten()
    top_idx = sims.argsort()[::-1][:top_k]
    results = [(articles[i], float(sims[i])) for i in top_idx if sims[i] > 0]
    return results

def call_openai_analysis(query, articles_text, api_key):
    """Call OpenAI to analyze search results and answer the query."""
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert research analyst. Analyze the provided articles and answer the user's query with insights, key findings, and synthesis from the articles.",
                },
                {
                    "role": "user",
                    "content": f"Query: {query}\n\nArticles:\n{articles_text}",
                },
            ],
            "temperature": 0.7,
            "max_tokens": 1500,
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error calling OpenAI: {str(e)}"

def run_app():
    st.set_page_config(page_title="Agile Biofoundry Search", layout="wide")
    st.title("Agile Biofoundry — Article Search & Analysis")

    # Sidebar: Add article form
    st.sidebar.header("Add Article")
    with st.sidebar.form("add_article_form"):
        title = st.text_input("Title *", key="article_title")
        authors = st.text_input("Authors (comma-separated)", key="article_authors")
        abstract = st.text_area("Abstract / Summary", key="article_abstract")
        url = st.text_input("URL / DOI", key="article_url")
        full_text = st.text_area("Full Text (optional)", height=150, key="article_text")
        
        submit = st.form_submit_button("Add Article", type="primary")
        if submit:
            if not title:
                st.sidebar.error("Title is required.")
            else:
                author_list = [a.strip() for a in authors.split(",") if a.strip()] if authors else []
                text = (full_text or abstract or "").strip()
                add_article(title, author_list, abstract, url, text)
                st.sidebar.success("Article added!")
                st.rerun()

    # Load articles
    articles = load_articles()
    
    # Main area: Search and analysis
    st.header("Search & Analysis")
    
    if not articles:
        st.info("No articles yet. Add articles from the sidebar to get started.")
        return

    # Display article count
    st.metric("Articles in library", len(articles))

    # Search bar and settings
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Enter your search query or question:", placeholder="e.g., 'What are the key findings about cell growth?'")
    with col2:
        top_k = st.slider("Results", 1, min(10, len(articles)), 3)

    if query:
        st.divider()
        
        # Search
        results = search_articles(query, articles, top_k=top_k)
        
        if not results:
            st.warning("No matching articles found.")
        else:
            # Display search results
            st.subheader(f"Found {len(results)} relevant articles")
            for article, score in results:
                with st.expander(f"**{article['title']}** (relevance: {score:.2%})"):
                    if article.get("authors"):
                        st.write(f"**Authors:** {', '.join(article['authors'])}")
                    if article.get("url"):
                        st.write(f"**URL:** {article['url']}")
                    if article.get("abstract"):
                        st.write(f"**Abstract:** {article['abstract']}")
                    if article.get("text"):
                        st.write(f"**Preview:** {article['text'][:500]}...")

            # AI analysis
            st.divider()
            st.subheader("AI Analysis")
            api_key = get_openai_client()
            
            if api_key:
                if st.button("Get AI Analysis", type="primary"):
                    articles_context = "\n\n---\n\n".join([
                        f"**{a['title']}** by {', '.join(a['authors']) if a.get('authors') else 'Unknown'}\n{a.get('text') or a.get('abstract') or 'No content'}"
                        for a, _ in results
                    ])
                    with st.spinner("Analyzing articles with AI..."):
                        analysis = call_openai_analysis(query, articles_context, api_key)
                    st.write(analysis)
            else:
                st.info("OpenAI API key not configured. Set `OPENAI_API_KEY` env var or add `openai_api_key` to `.streamlit/secrets.toml` to enable AI analysis.")

    # Sidebar: Manage articles
    st.sidebar.divider()
    st.sidebar.header("Manage Articles")
    if articles:
        with st.sidebar.expander(f"View/Delete Articles ({len(articles)})"):
            for article in articles:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{article['title'][:40]}...**" if len(article['title']) > 40 else f"**{article['title']}**")
                with col2:
                    if st.button("🗑️", key=f"del_{article['id']}", help="Delete"):
                        delete_article(article['id'])
                        st.rerun()

    # Sidebar: Scan articles' URLs and extract HTML text with verbose logging
    if st.sidebar.button("Scan article URLs and extract HTML text"):
        with st.spinner("Scanning article URLs and extracting text..."):
            articles = load_articles()
            log_lines = []
            updated = 0
            for a in articles:
                # skip if already has text
                if a.get("text"):
                    log_lines.append(f"⏭**{a['title']}** — already has text, skipping")
                    continue
                url = a.get("url") or ""
                if not url or not isinstance(url, str):
                    log_lines.append(f"**{a['title']}** — no URL provided")
                    continue
                extracted = fetch_and_extract_html(url)
                if extracted and len(extracted) > 200:
                    a["text"] = extracted
                    updated += 1
                    log_lines.append(f"**{a['title']}** — extracted {len(extracted)} chars from `{url[:60]}...`")
                elif extracted:
                    log_lines.append(f"**{a['title']}** — extracted only {len(extracted)} chars (min 200) from `{url[:60]}...`")
                else:
                    log_lines.append(f"**{a['title']}** — failed to extract from `{url[:60]}...`")
            if updated:
                save_articles(articles)
        
        # Display results in main area
        st.divider()
        st.subheader("Scan Results")
        st.success(f"Updated **{updated}** articles with extracted text.")
        with st.expander("View detailed scan log", expanded=True):
            for line in log_lines:
                st.markdown(line)
        st.rerun()

if __name__ == "__main__":
    run_app()
