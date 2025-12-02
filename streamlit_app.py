import streamlit as st
import os
import json
import uuid
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from PyPDF2 import PdfReader

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


def download_file(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, stream=True, timeout=30, headers={"User-Agent": "agile-biofoundry-bot/1.0"})
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 64):
                f.write(chunk)
        return True
    except Exception:
        return False


def fetch_lean_library_links(page_url: str, cookie_header: str | None = None, limit: int = 200) -> list:
    """Fetch a Lean Library page and heuristically extract candidate article links.

    - `cookie_header` can be a raw cookie string like "name=value; name2=value2" to access pages behind simple auth.
    - Passes all cookies, referer, and User-Agent to mimic a browser for authenticated pages.
    - Returns a list of dicts: {"url": <absolute url>, "title": <link text or None>}.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": page_url,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        cookies = None
        if cookie_header:
            cookies = {}
            for part in [p.strip() for p in cookie_header.split(";") if p.strip()]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()

        # Use session to persist cookies and headers
        session = requests.Session()
        if cookies:
            session.cookies.update(cookies)
        
        resp = session.get(page_url, headers=headers, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        
        # Check if we got redirected to login (common pattern)
        if "login" in resp.url.lower() or "signin" in resp.url.lower():
            return [{"url": page_url, "title": "⚠️ Page requires authentication—provide valid cookies"}]
        
        try:
            soup = BeautifulSoup(resp.content, "lxml")
        except Exception:
            soup = BeautifulSoup(resp.content, "html.parser")
    except Exception as e:
        return [{"url": page_url, "title": f"❌ Error fetching page: {str(e)[:60]}"}]

    anchors = soup.find_all("a", href=True)
    results = []
    seen = set()
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        href = urljoin(page_url, href)
        # only keep http(s)
        if not (href.startswith("http://") or href.startswith("https://")):
            continue
        # skip obvious anchors or same-page fragments
        if href in seen or href.startswith(page_url + "#"):
            continue
        # simple noise filtering: ignore links to css/js/images and mailto/tel
        if any(x in href for x in (".css", ".js", ".jpg", ".jpeg", ".png", ".svg", "mailto:", "tel:")):
            continue

        title = a.get_text(strip=True) or None
        results.append({"url": href, "title": title})
        seen.add(href)
        if len(results) >= limit:
            break

    return results


def fetch_items_api(endpoint: str, authorization: str | None = None, cookie_header: str | None = None, query_params: str | None = None) -> list:
    """Call a JSON API endpoint (the SPA XHR 'items' endpoint) and return a list of {url,title} dicts.

    - `authorization` (optional) — full header value (e.g. 'Bearer <token>') or token string.
    - `cookie_header` (optional) — cookie string "name1=value1; name2=value2".
    - `query_params` (optional) — query string like "collectionId=1054271&limit=100".
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": endpoint,
    }
    if authorization:
        # allow either full 'Bearer ...' or bare token
        if authorization.lower().startswith("bearer ") or ":" in authorization or authorization.count(" ") > 0:
            headers["Authorization"] = authorization
        else:
            headers["Authorization"] = f"Bearer {authorization}"

    cookies = None
    if cookie_header:
        cookies = {}
        for part in [p.strip() for p in cookie_header.split(";") if p.strip()]:
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()

    # Add query params if provided
    url = endpoint
    if query_params:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query_params}"

    try:
        resp = requests.get(url, headers=headers, timeout=30, cookies=cookies)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return [{"url": endpoint, "title": f"❌ API fetch error: {str(e)[:120]}"}]

    # Normalize data to a list of items
    items = []
    if isinstance(data, dict):
        for key in ("items", "results", "data", "articles", "content"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        if not items:
            # maybe the dict itself is one item
            if any(k in data for k in ("id", "title", "url")):
                items = [data]
    elif isinstance(data, list):
        items = data

    results = []
    seen = set()
    for a in items:
        if not isinstance(a, dict):
            continue
        url = a.get("url") or a.get("link") or a.get("pdf_url") or a.get("pdf") or a.get("file") or a.get("uri")
        title = a.get("title") or a.get("name") or a.get("article_title") or None
        if not url:
            continue
        if url in seen:
            continue
        results.append({"url": url, "title": title})
        seen.add(url)
    return results


def extract_text_from_pdf(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        texts = []
        for p in reader.pages:
            try:
                t = p.extract_text() or ""
            except Exception:
                t = ""
            if t:
                texts.append(t)
        return "\n\n".join(texts)
    except Exception:
        return ""

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

    # Sidebar note: articles are managed by imports and crawls (no manual add)
    st.sidebar.header("Library Import / Sync")
    st.sidebar.info("Articles are added automatically via Lean Library import or page fetch. Use the Import or Fetch options below to populate the library. You can view/delete items under Manage Articles.")

    # Load articles
    st.sidebar.markdown("---")
    st.sidebar.header("Import Lean Library export")
    upload_file = st.sidebar.file_uploader("Upload JSON (array of articles) or CSV with a 'url' column", type=["json", "csv"], key="lean_upload")
    st.sidebar.markdown("---")
    st.sidebar.header("Or: fetch from a Lean Library page")
    lean_page = st.sidebar.text_input("Lean Library page URL", placeholder="https://your-institution.leanlibrary.org/collections/xxxx", key="lean_page_url")

    # API endpoint / Authorization support (preferred for SPA)
    st.sidebar.markdown("---")
    st.sidebar.header("Optional: Use site API / XHR endpoint")
    st.sidebar.info("Paste the 'items' XHR endpoint URL. Auth is typically via cookies (session-based). If items need filtering, add query params like `?collectionId=1054271`.")
    api_endpoint = st.sidebar.text_input("API endpoint (paste XHR 'items' URL)", placeholder="https://sciwheel.com/work/api/search/items", key="lean_api_endpoint")
    query_params = st.sidebar.text_input("Query parameters (optional)", placeholder="collectionId=1054271&limit=100", key="lean_query_params")
    authorization_header = st.sidebar.text_input("Authorization header (optional, usually not needed)", placeholder="Bearer <token> or token", key="lean_api_auth")

    with st.sidebar.expander("ℹ️ How to get the XHR token", expanded=False):
        st.markdown("""
1. Open your project page in the browser while logged in.
2. Open DevTools → Network → filter XHR/Fetch and reload.
3. Find the `items` XHR request, right-click → Copy → Copy request URL.
4. In the XHR request headers look for `Authorization`, or check Application → Local Storage for `accessToken`/`authToken`.
5. Paste the request URL into "API endpoint" and paste the header value into "Authorization header".
""")

    with st.sidebar.expander("ℹ️ How to get authentication cookies", expanded=False):
        st.markdown("""
**Quick copy-paste method:**
1. Open your Lean Library project in a browser (logged in)
2. Open Developer Tools → **Application** → **Cookies** → **sciwheel.com**
3. Select all cookies (Ctrl+A in the table), copy them
4. Paste into the text area below — the app will auto-format
5. Or manually copy key cookie names like `JSESSIONID`, `SPRING_SECURITY_REMEMBER_ME_COOKIE`, etc.
""")

    cookie_input = st.sidebar.text_area(
        "Paste cookies here (will auto-format)",
        height=100,
        placeholder="Paste raw cookies from DevTools. Format: name=value or multi-line list",
        key="lean_cookie_input"
    )
    
    # Auto-format cookies: handle both "name=value" and multi-line formats
    def parse_cookies(raw_input):
        if not raw_input:
            return ""
        lines = raw_input.strip().split("\n")
        pairs = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Handle tab-separated DevTools format (Name [TAB] Value [TAB] ...)
            if "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    value = parts[1].strip()
                    if name and value and not any(x in name.lower() for x in ["domain", "path", "expires", "size", "http", "secure", "same"]):
                        pairs.append(f"{name}={value}")
            # Handle standard "name=value" format
            elif "=" in line and not any(x in line for x in ["http", "curl", "domain", "path", "expires"]):
                pairs.append(line)
        
        return "; ".join(pairs)
    
    cookie_header = parse_cookies(cookie_input)
    
    # Buttons: Fetch and Debug
    col1, col2, col3 = st.sidebar.columns(3)
    with col1:
        fetch_btn = st.button("🔄 Fetch links", key="btn_fetch")
    with col2:
        debug_btn = st.button("🐛 Debug API", key="btn_debug")
    
    if fetch_btn or debug_btn:
        if debug_btn and not api_endpoint:
            st.sidebar.error("Provide an API endpoint first.")
        elif debug_btn:
            # Debug: show raw API response
            st.sidebar.info("Fetching raw API response...")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}
            if authorization_header:
                if authorization_header.lower().startswith("bearer ") or ":" in authorization_header or authorization_header.count(" ") > 0:
                    headers["Authorization"] = authorization_header
                else:
                    headers["Authorization"] = f"Bearer {authorization_header}"
            cookies = None
            if cookie_header:
                cookies = {}
                for part in [p.strip() for p in cookie_header.split(";") if p.strip()]:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()
            
            # Build URL with query params
            url = api_endpoint
            if query_params:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{query_params}"
            
            # Show what we're sending
            st.sidebar.write("**Request details:**")
            st.sidebar.write(f"URL: `{url}`")
            st.sidebar.write(f"Auth header: `{headers.get('Authorization', '(none)')}`")
            st.sidebar.write(f"Cookies: `{len(cookies) if cookies else 0} cookies`")
            
            try:
                resp = requests.get(url, headers=headers, timeout=30, cookies=cookies)
                st.sidebar.write(f"**Response status:** {resp.status_code}")
                resp.raise_for_status()
                raw_data = resp.json()
                st.sidebar.success(f"✅ Success")
                st.sidebar.json(raw_data)
            except requests.exceptions.HTTPError as e:
                st.sidebar.error(f"❌ HTTP Error {e.response.status_code}: {e.response.reason}")
                st.sidebar.write("**Tips:**")
                st.sidebar.write("- For 401/403: Cookies may have expired. Re-copy from DevTools → Application → Cookies.")
                st.sidebar.write("- Try adding query params like `collectionId=1054271` (the collection ID from your URL).")
                st.sidebar.write("- The endpoint may require different query param names. Check DevTools Network tab for the actual XHR request URL parameters.")
                try:
                    st.sidebar.write(f"Response body: {e.response.text[:200]}")
                except:
                    pass
            except Exception as e:
                st.sidebar.error(f"❌ Error: {str(e)}")
        elif fetch_btn:
            # Fetch: process and store links
            if api_endpoint:
                with st.spinner("Fetching items via API..."):
                    links = fetch_items_api(api_endpoint, authorization_header, cookie_header, query_params)
            else:
                with st.spinner("Fetching links from Lean Library page..."):
                    links = fetch_lean_library_links(lean_page, cookie_header)
            if not links:
                st.sidebar.warning("No candidate links found or failed to fetch the page. Check URL / cookies / auth token.")
            else:
                st.session_state["lean_fetched_links"] = links
                st.sidebar.success(f"Found {len(links)} links (showing first 50).")
    
        if not lean_page:
            st.sidebar.error("Provide a Lean Library page URL first.")
        else:
            with st.spinner("Fetching links from Lean Library page..."):
                links = fetch_lean_library_links(lean_page, cookie_header)
            if not links:
                st.sidebar.warning("No candidate links found or failed to fetch the page. Check URL / cookies.")
            else:
                st.session_state["lean_fetched_links"] = links
                st.sidebar.success(f"Found {len(links)} links (showing first 50).")
    articles = load_articles()
    
    # Main area: Search and analysis
    st.header("Search & Analysis")
    
    # Check if we have fetched links to display/import
    fetched = st.session_state.get("lean_fetched_links") if hasattr(st, "session_state") else None
    
    # Only return early if we have no articles AND no fetched links
    if not articles and not fetched:
        st.info("No articles yet. Fetch links from a Lean Library page or upload an export to get started.")
        return

    if upload_file is not None:
        # read file
        raw = upload_file.read()
    if fetched:
        st.divider()
        st.subheader("Links found on Lean Library page")
        max_preview = min(50, len(fetched))
        
        # Show fetched links
        for i, item in enumerate(fetched[:max_preview]):
            st.write(f"{i+1}. {item.get('title') or item['url']}")
            st.write(f"`{item['url']}`")
        
        # Add import button
        if st.button("Import all links and extract content"):
            articles = load_articles()
            existing_urls = {a.get("url") for a in articles}
            progress_bar = st.progress(0)
            status_container = st.empty()
            logs = []
            imported = 0
            total = len(fetched)
            
            for i, item in enumerate(fetched):
                url = item.get("url")
                title = item.get("title") or url
                
                # Update progress and status
                progress_pct = int((i + 1) / total * 100)
                progress_bar.progress(progress_pct)
                status_container.write(f"Processing {i+1}/{total}...")
                
                if not url or url in existing_urls:
                    logs.append(f"⏭ {i+1}/{total}: Skipped (duplicate or no URL)")
                    continue
                
                # Try HTML extraction first
                text = ""
                extracted = fetch_and_extract_html(url)
                if extracted and len(extracted) > 200:
                    text = extracted
                    logs.append(f"✅ {i+1}/{total}: Extracted HTML ({len(text)} chars)")
                else:
                    # Try PDF
                    is_pdf = url.lower().endswith(".pdf")
                    if not is_pdf:
                        try:
                            head = requests.head(url, headers={"User-Agent": "agile-biofoundry-bot/1.0"}, timeout=10, allow_redirects=True)
                            ctype = head.headers.get("content-type", "")
                            is_pdf = "pdf" in ctype.lower()
                        except Exception:
                            pass
                    
                    if is_pdf:
                        dest = DATA_DIR / (str(uuid.uuid4()) + ".pdf")
                        if download_file(url, dest):
                            pdf_text = extract_text_from_pdf(dest)
                            if pdf_text and len(pdf_text) > 100:
                                text = pdf_text
                                logs.append(f"✅ {i+1}/{total}: Extracted PDF ({len(text)} chars)")
                            else:
                                logs.append(f"⚠️ {i+1}/{total}: PDF has no extractable text")
                        else:
                            logs.append(f"❌ {i+1}/{total}: Failed to download PDF")
                    else:
                        if extracted:
                            logs.append(f"⚠️ {i+1}/{total}: HTML too small ({len(extracted)} chars, need >200)")
                        else:
                            logs.append(f"❌ {i+1}/{total}: Failed to extract any content")
                
                # Add article
                new = {
                    "id": str(uuid.uuid4()),
                    "title": title,
                    "authors": [],
                    "abstract": None,
                    "url": url,
                    "text": text,
                    "created_at": datetime.now().isoformat(),
                }
                articles.append(new)
                existing_urls.add(url)
                imported += 1
            
            # Save and finalize
            if imported > 0:
                save_articles(articles)
            st.session_state["lean_import_log"] = logs
            progress_bar.progress(100)
            status_container.success(f"✅ Import complete! Added {imported} articles.")
            st.rerun()
    
    # Display article count
    st.metric("Articles in library", len(articles))

    # Show last import log if available
    import_log = st.session_state.get("lean_import_log") if hasattr(st, "session_state") else None
    if import_log:
        st.divider()
        st.subheader("Last import log")
        with st.expander("View import log", expanded=False):
            for line in import_log:
                st.write(line)

    # Search bar and settings
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Enter your search query or question:", placeholder="e.g., 'What are the key findings about cell growth?'")
    with col2:
        top_k = st.slider("Results", 1, min(10, len(articles)), 100)

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
