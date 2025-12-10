import streamlit as st
import os
import json
import uuid
import time
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import random

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import gc
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Selenium for JavaScript rendering
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# ============================================================================
# CONFIGURATION
# ============================================================================
DATA_DIR = Path("data")
ARTICLES_PATH = DATA_DIR / "articles.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_ARTICLE_TEXT = 200_000
MAX_DOWNLOAD_BYTES = 5_000_000
MAX_PDF_BYTES = 50_000_000
SELENIUM_TIMEOUT = 15  # seconds to wait for page load

RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=["HEAD", "GET", "POST"]
)

# Domains known to block automated access - skip gracefully
BLOCKED_DOMAINS = {
    "annualreviews.org",  # Strict bot detection
    "acs.org",  # ACS blocked
    "nature.com",  # Paywall
    "science.org",  # Science paywall
    "sciencedirect.com",  # Elsevier paywall
    "wiley.com",  # Wiley paywall
    "springer.com",  # Springer paywall
    "ieeexplore.ieee.org",  # IEEE paywall
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# ============================================================================
# SESSION & REQUEST HELPERS
# ============================================================================
def build_session(cookies: Optional[Dict] = None) -> requests.Session:
    """Create a requests session with retry logic and proper headers."""
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=RETRY_STRATEGY)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if cookies:
        s.cookies.update(cookies)
    return s

def get_random_user_agent() -> str:
    """Return a random user agent to avoid detection."""
    return random.choice(USER_AGENTS)

def cookie_header_to_dict(cookie_header: Optional[str]) -> Optional[Dict]:
    """Parse cookie string into dictionary."""
    if not cookie_header:
        return None
    cookies = {}
    for part in [p.strip() for p in cookie_header.split(";") if p.strip()]:
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

def parse_cookies(raw_input: str) -> str:
    """Auto-format cookies from DevTools copy-paste."""
    if not raw_input:
        return ""
    lines = raw_input.strip().split("\n")
    pairs = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[0].strip()
                value = parts[1].strip()
                if name and value and not any(x in name.lower() for x in ["domain", "path", "expires", "size", "http", "secure", "same"]):
                    pairs.append(f"{name}={value}")
        elif "=" in line and not any(x in line for x in ["http", "curl", "domain", "path", "expires"]):
            pairs.append(line)
    
    return "; ".join(pairs)

# ============================================================================
# STORAGE OPERATIONS
# ============================================================================
def load_articles() -> List[Dict]:
    """Load articles from local storage."""
    if ARTICLES_PATH.exists():
        try:
            with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            st.error("Article database corrupted. Starting fresh.")
            return []
    return []

def save_articles(articles: List[Dict]) -> None:
    """Save articles atomically to prevent corruption."""
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(DATA_DIR)) as tf:
            json.dump(articles, tf, ensure_ascii=False, indent=2)
            tmpname = tf.name
        Path(tmpname).replace(ARTICLES_PATH)
    except Exception as e:
        st.error(f"Failed to save articles: {str(e)}")

def add_article(title: str, authors: List[str], abstract: str, url: str, text: str) -> Dict:
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

def delete_article(article_id: str) -> None:
    """Delete an article by ID."""
    articles = load_articles()
    articles = [a for a in articles if a["id"] != article_id]
    save_articles(articles)

# ============================================================================
# CONTENT EXTRACTION
# ============================================================================
def extract_pdf_link_from_page(soup, base_url: str) -> Optional[str]:
    """
    Try to find a PDF download link from an HTML page.
    Useful for landing pages that host PDF viewers/containers.
    """
    # Look for direct PDF links
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').lower()
        if '.pdf' in href or 'download' in href or 'pdf' in link.get_text().lower():
            pdf_url = link['href']
            if not pdf_url.startswith('http'):
                pdf_url = urljoin(base_url, pdf_url)
            if pdf_url.lower().endswith('.pdf') or 'pdf' in pdf_url.lower():
                return pdf_url
    
    # Look for iframe pointing to PDF
    for iframe in soup.find_all('iframe', src=True):
        src = iframe['src'].lower()
        if '.pdf' in src or 'pdf' in src:
            pdf_url = iframe['src']
            if not pdf_url.startswith('http'):
                pdf_url = urljoin(base_url, pdf_url)
            return pdf_url
    
    return None

def render_with_selenium(url: str, cookies: Optional[Dict] = None) -> Tuple[str, str]:
    """
    Render a page using Selenium for JavaScript-heavy sites.
    Returns: (html_content, reason)
    """
    if not SELENIUM_AVAILABLE:
        return "", "Selenium not installed"
    
    driver = None
    try:
        # Setup Chrome options for headless mode
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=" + get_random_user_agent())
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        
        driver = webdriver.Chrome(options=options)
        
        # Add cookies if provided
        if cookies:
            driver.get(url.split('//', 1)[1].split('/')[0])  # Go to domain first
            for name, value in cookies.items():
                try:
                    driver.add_cookie({"name": name, "value": value})
                except Exception:
                    pass  # Cookie may not be valid for this domain
        
        # Navigate to URL
        driver.get(url)
        
        # Wait for content to load (either article tag or main content)
        try:
            if SELENIUM_AVAILABLE:
                WebDriverWait(driver, SELENIUM_TIMEOUT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
        except Exception:
            pass  # Timeout is acceptable, work with what we have
        
        # Get rendered HTML
        html = driver.page_source
        
        if html and len(html) > 500:
            return html, "Rendered with Selenium (JavaScript)"
        else:
            return "", "Selenium rendered but page content empty"
    
    except Exception as e:
        return "", f"Selenium rendering failed: {str(e)[:80]}"
    
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

def fetch_and_extract_html(url: str, cookies: Optional[Dict] = None, delay: float = 1.0) -> Tuple[str, str]:
    """
    Fetch URL and extract main article text with rate limiting.
    Only processes HTML/web pages, skips direct PDFs.
    Returns: (content, reason) where reason explains success/failure.
    """
    time.sleep(delay)
    
    # Skip direct PDF URLs - check multiple patterns
    url_lower = url.lower()
    if (url_lower.endswith('.pdf') or 
        '/pdf/' in url_lower or
        'download.pdf' in url_lower or
        '/getpdf' in url_lower or
        'pdf?' in url_lower or
        'pdf=' in url_lower):
        return "", f"Skipped: PDF URL detected in path ({url[:80]})"
    
    # Check if domain is known to block automated access
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower().replace('www.', '')
    
    for blocked_domain in BLOCKED_DOMAINS:
        if blocked_domain in domain:
            return "", f"Skipped: {blocked_domain} blocks automated access. Try: (1) institutional login, (2) VPN, (3) manual web link"
    
    try:
        s = build_session(cookies)
        
        # Parse URL to build smart referer
        parsed = urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"
        
        headers = {
            "User-Agent": get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": referer,
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        resp = s.get(url, timeout=20, headers=headers, stream=True, allow_redirects=True)
        resp.raise_for_status()
        
        ctype = resp.headers.get("content-type", "")
        if "pdf" in ctype.lower():
            return "", "Skipped: Content-Type is PDF (use Web Link instead)"

        collected = bytearray()
        total = 0
        for chunk in resp.iter_content(8192):
            if not chunk:
                break
            collected.extend(chunk)
            total += len(chunk)
            if total >= MAX_DOWNLOAD_BYTES:
                break
        
        html = bytes(collected)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            return "", "403 Forbidden - Site blocks automated requests. Try: (1) institutional login cookies, (2) VPN, (3) use Web Link option instead of PDF/Inst. Access"
        elif e.response.status_code == 401:
            return "", "401 Unauthorized - Authentication required. Provide valid session cookies from DevTools"
        elif e.response.status_code == 404:
            return "", "404 Not Found - URL may be broken or article removed"
        elif e.response.status_code == 429:
            return "", "429 Too Many Requests - Rate limited. Increase delay between requests"
        return "", f"HTTP {e.response.status_code} error - Server rejected request"
    except requests.exceptions.Timeout:
        return "", "Timeout - Server took too long to respond (>20s)"
    except requests.exceptions.ConnectionError:
        return "", "Connection error - Network issue or invalid URL"
    except Exception as e:
        return "", f"Fetch error ({type(e).__name__}): {str(e)[:100]}"

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return "", "HTML parsing failed - malformed content"

    # Try <article> tag
    article_tag = soup.find("article")
    if article_tag:
        text = article_tag.get_text(separator="\n", strip=True)
        if len(text) > 200:
            return text, "Extracted from <article> tag"

    # Try main or role=main
    main_tag = soup.find("main") or soup.find(attrs={"role": "main"})
    if main_tag:
        text = main_tag.get_text(separator="\n", strip=True)
        if len(text) > 200:
            return text, "Extracted from <main> tag"

    # Try largest div/section
    candidates = soup.find_all(["div", "section", "article", "main"])
    best = ""
    for c in candidates:
        t = c.get_text(separator="\n", strip=True)
        if len(t) > len(best):
            best = t
    if len(best) > 200:
        return best, "Extracted from largest content block"

    # Fallback: all paragraphs
    ps = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
    joined = "\n\n".join(ps) if ps else ""
    
    if len(joined) > 200:
        return joined, "Extracted from paragraph tags"
    
    # If content is too short or empty, try Selenium for JavaScript-rendered content
    if len(joined) < 200:
        if SELENIUM_AVAILABLE:
            try:
                selenium_html, selenium_reason = render_with_selenium(url, cookies)
                if selenium_html and "failed" not in selenium_reason.lower():
                    # Parse selenium-rendered HTML
                    try:
                        selenium_soup = BeautifulSoup(selenium_html, "lxml")
                    except Exception:
                        selenium_soup = BeautifulSoup(selenium_html, "html.parser")
                    
                    # Try extraction strategies again on rendered content
                    article_tag = selenium_soup.find("article")
                    if article_tag:
                        text = article_tag.get_text(separator="\n", strip=True)
                        if len(text) > 200:
                            return text, f"{selenium_reason} - Extracted from <article> tag"
                    
                    main_tag = selenium_soup.find("main") or selenium_soup.find(attrs={"role": "main"})
                    if main_tag:
                        text = main_tag.get_text(separator="\n", strip=True)
                        if len(text) > 200:
                            return text, f"{selenium_reason} - Extracted from <main> tag"
                    
                    candidates = selenium_soup.find_all(["div", "section", "article", "main"])
                    best = ""
                    for c in candidates:
                        t = c.get_text(separator="\n", strip=True)
                        if len(t) > len(best):
                            best = t
                    if len(best) > 200:
                        return best, f"{selenium_reason} - Extracted from largest content block"
                    
                    ps = [p.get_text(separator=" ", strip=True) for p in selenium_soup.find_all("p")]
                    selenium_joined = "\n\n".join(ps) if ps else ""
                    if len(selenium_joined) > 200:
                        return selenium_joined, f"{selenium_reason} - Extracted from paragraph tags"
            except Exception:
                pass  # Selenium fallback failed, continue with standard response
    
    if len(joined) > 0:
        return "", f"Content too short ({len(joined)} chars, need >200) - may be paywall, login page, or JavaScript-heavy. Try: (1) institutional login, (2) VPN, (3) Web Link instead of PDF"
    else:
        return "", "No readable content found - page may require JavaScript (install: pip install selenium), be behind paywall, or is a PDF landing page"

def download_file(url: str, dest: Path, cookies: Optional[Dict] = None, delay: float = 1.0) -> Tuple[bool, str]:
    """
    Download a file with rate limiting.
    Returns: (success, reason)
    """
    time.sleep(delay)
    
    s = build_session(cookies)
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "application/pdf,*/*",
    }
    
    try:
        with s.get(url, stream=True, timeout=30, headers=headers, allow_redirects=True) as r:
            r.raise_for_status()
            total = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1024 * 64):
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
                    if total >= MAX_PDF_BYTES:
                        raise Exception("File exceeds max allowed size (50MB)")
        return True, f"Downloaded {total // 1024}KB"
    except requests.exceptions.HTTPError as e:
        if dest.exists():
            dest.unlink()
        if e.response.status_code == 403:
            return False, "403 Forbidden - PDF access requires authentication"
        elif e.response.status_code == 404:
            return False, "404 Not Found - PDF URL invalid"
        return False, f"HTTP {e.response.status_code}"
    except Exception as e:
        if dest.exists():
            dest.unlink()
        return False, f"Download failed: {str(e)[:100]}"

def extract_text_from_pdf(path: Path) -> Tuple[str, str]:
    """
    Extract text from PDF file.
    Returns: (text, reason)
    """
    try:
        reader = PdfReader(str(path))
        if len(reader.pages) == 0:
            return "", "PDF has no pages"
        
        texts = []
        for p in reader.pages:
            try:
                t = p.extract_text() or ""
            except Exception:
                t = ""
            if t:
                texts.append(t)
        
        result = "\n\n".join(texts)
        if len(result) > 100:
            return result, f"Extracted from {len(reader.pages)} pages"
        else:
            return "", f"PDF has {len(reader.pages)} pages but no extractable text (may be scanned images)"
    except Exception as e:
        return "", f"PDF extraction failed: {str(e)[:100]}"

# ============================================================================
# API & LINK FETCHING
# ============================================================================
def fetch_items_api(
    endpoint: str,
    authorization: Optional[str] = None,
    cookie_header: Optional[str] = None,
    collection_id: Optional[str] = None
) -> List[Dict]:
    """Call JSON API endpoint to fetch items."""
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": endpoint,
    }
    
    if authorization:
        if authorization.lower().startswith("bearer ") or ":" in authorization:
            headers["Authorization"] = authorization
        else:
            headers["Authorization"] = f"Bearer {authorization}"

    cookies = cookie_header_to_dict(cookie_header) if cookie_header else None

    payload = {
        "libraryItemCriteria": {
            "collectionId": collection_id or "1054271",
            "tagIds": None,
            "withMissingCitationData": None,
            "fieldsCriteria": [],
            "withPdf": None,
            "recommended": None,
            "withAnnotations": None,
            "review": None,
            "clinicalTrial": None,
            "systematicReview": None,
            "addedByMe": None,
            "withoutTags": None,
        },
        "query": None,
        "page": None,
        "show": 100,
        "sortBy": ["addedDate"],
        "sortingOrder": None,
        "hasTextParams": False,
    }

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=30, cookies=cookies)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return [{"url": endpoint, "title": f"❌ API fetch error: {str(e)[:120]}"}]

    items = []
    if isinstance(data, dict):
        for key in ("displayedItems", "items", "results", "data", "articles", "content", "libraryItems"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        if not items and any(k in data for k in ("id", "title", "url")):
            items = [data]
    elif isinstance(data, list):
        items = data

    results = []
    seen = set()
    debug_info = []
    
    parsed = urlparse(endpoint)
    base = f"{parsed.scheme}://{parsed.netloc}"

    for idx, a in enumerate(items):
        if not isinstance(a, dict):
            continue

        article_title = a.get("title") or a.get("plainTitle") or "Untitled"
        
        raw_url = None
        url_source = None
        
        # Try primary fields
        for source_field in ("fullTextLink", "url", "link", "pdf_url", "pdf", "file", "uri", "pdfUrl"):
            val = a.get(source_field)
            if val:
                raw_url = val
                url_source = source_field
                break

        # Try pdfResource
        if not raw_url:
            pr = a.get("pdfResource") or a.get("pdf_resource")
            if isinstance(pr, dict):
                cloud = pr.get("cloudFilePath") or pr.get("cloud_file_path") or pr.get("cloudFile")
                if cloud:
                    raw_url = cloud
                    url_source = "pdfResource.cloudFilePath"

        # Try DOI fallback
        if not raw_url:
            doi = a.get("doi")
            if doi:
                raw_url = f"https://doi.org/{doi}"
                url_source = "doi"

        if not raw_url:
            debug_info.append(f"  [{idx}] {article_title}: ❌ No URL found")
            continue

        try:
            resolved = raw_url if raw_url.startswith("http") else urljoin(base + "/", raw_url)
        except Exception:
            resolved = raw_url

        if resolved in seen:
            continue

        title = a.get("title") or a.get("plainTitle") or a.get("name") or None
        debug_info.append(f"  [{idx}] {article_title}: ✅ [{url_source}] {resolved[:70]}")
        results.append({"url": resolved, "title": title})
        seen.add(resolved)

    st.session_state["parse_debug"] = debug_info
    return results

# ============================================================================
# SEARCH FUNCTIONALITY
# ============================================================================
def build_tfidf_index(articles: List[Dict]) -> Tuple[Optional[TfidfVectorizer], Optional[any]]:
    """Build TF-IDF index from articles."""
    if not articles:
        return None, None
    
    texts = [a.get("text", "") or a.get("abstract", "") or "" for a in articles]
    texts = [t.strip() for t in texts]

    if not any(texts):
        return None, None

    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=5000, min_df=1)
        X = vectorizer.fit_transform(texts)
        return vectorizer, X
    except ValueError:
        return None, None

def search_articles(query: str, articles: List[Dict], top_k: int = 5) -> List[Tuple[Dict, float]]:
    """Search articles using TF-IDF similarity with keyword fallback."""
    if not articles:
        return []

    vectorizer, X = build_tfidf_index(articles)

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
        return [(articles[i], score) for i, score in scored[:top_k]]

    q_vec = vectorizer.transform([query])
    sims = cosine_similarity(q_vec, X).flatten()
    top_idx = sims.argsort()[::-1][:top_k]
    results = [(articles[i], float(sims[i])) for i in top_idx if sims[i] > 0]
    return results

def call_openai_analysis(query: str, articles_text: str, api_key: str) -> str:
    """Call OpenAI API for article analysis."""
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert research analyst. Analyze the provided articles and answer the user's query with insights, key findings, and synthesis from the articles.",
                },
                {"role": "user", "content": f"Query: {query}\n\nArticles:\n{articles_text}"},
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

def get_openai_client():
    """Get OpenAI API key from secrets or environment."""
    api_key = st.secrets.get("openai_api_key") if hasattr(st, "secrets") else None
    return api_key or os.environ.get("OPENAI_API_KEY")

# ============================================================================
# BATCH IMPORT LOGIC
# ============================================================================
def process_article_batch(
    items: List[Dict],
    start_idx: int,
    cookies_dict: Optional[Dict],
    existing_urls: set,
    rate_limit_delay: float = 2.0
) -> Tuple[List[Dict], List[str], int]:
    """Process a batch of articles with detailed error reporting. HTML/Web links only."""
    new_articles = []
    logs = []
    imported = 0
    
    for idx, item in enumerate(items):
        global_idx = start_idx + idx + 1
        url = item.get("url")
        title = item.get("title") or url

        if not url or url in existing_urls:
            logs.append(f"⏭ {global_idx}: Skipped (duplicate or no URL)")
            continue
        
        # Skip PDF URLs - check multiple patterns
        url_lower = url.lower()
        if (url_lower.endswith('.pdf') or 
            '/pdf/' in url_lower or
            'download.pdf' in url_lower or
            '/getpdf' in url_lower or
            'pdf?' in url_lower or
            'pdf=' in url_lower):
            logs.append(f"⏭ {global_idx}: Skipped PDF URL - {url[:80]}")
            continue

        text = ""
        import_reason = ""
        
        try:
            extracted, reason = fetch_and_extract_html(url, cookies=cookies_dict, delay=rate_limit_delay)
            
            if extracted and len(extracted) > 200:
                text = extracted
                logs.append(f"✅ {global_idx}: {reason} ({len(text)} chars)")
            else:
                logs.append(f"❌ {global_idx}: {reason}")
                import_reason = reason

        except Exception as e:
            error_msg = f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"
            logs.append(f"❌ {global_idx}: {error_msg}")
            import_reason = error_msg
            continue

        if text:
            if len(text) > MAX_ARTICLE_TEXT:
                text = text[:MAX_ARTICLE_TEXT] + "\n\n...[truncated]"

            new_article = {
                "id": str(uuid.uuid4()),
                "title": title,
                "authors": [],
                "abstract": None,
                "url": url,
                "text": text,
                "created_at": datetime.now().isoformat(),
                "import_status": "success"
            }
            new_articles.append(new_article)
            existing_urls.add(url)
            imported += 1
        elif import_reason:
            # Store failed articles with reason
            failed_article = {
                "id": str(uuid.uuid4()),
                "title": title,
                "authors": [],
                "abstract": None,
                "url": url,
                "text": "",
                "created_at": datetime.now().isoformat(),
                "import_status": "failed",
                "import_reason": import_reason
            }
            new_articles.append(failed_article)
            existing_urls.add(url)

    # Analyze blocked domains and provide summary
    blocked_summary = {}
    for log in logs:
        for domain in BLOCKED_DOMAINS:
            if domain in log:
                blocked_summary[domain] = blocked_summary.get(domain, 0) + 1
    
    if blocked_summary:
        logs.append("")
        logs.append("📊 SUMMARY: Blocked Domains")
        for domain, count in sorted(blocked_summary.items(), key=lambda x: -x[1]):
            logs.append(f"  • {domain}: {count} articles")
        logs.append("")
        logs.append("💡 To access blocked content:")
        logs.append("  1. Institutional login: Use your university/organization credentials")
        logs.append("  2. VPN: Connect to institutional VPN to bypass geographic restrictions")
        logs.append("  3. Library proxy: Some institutions provide proxy URLs")
        logs.append("  4. DOI alternative: Try searching the DOI directly via https://doi.org/")

    return new_articles, logs, imported

# ============================================================================
# STREAMLIT APP
# ============================================================================
def run_app():
    st.set_page_config(page_title="Agile Biofoundry Search", layout="wide")
    st.title("🧬 Agile Biofoundry — Article Search & Analysis")

    if "lean_import_pos" not in st.session_state:
        st.session_state.lean_import_pos = 0

    # ========================================================================
    # SIDEBAR: IMPORT & CONFIGURATION
    # ========================================================================
    st.sidebar.header("📚 Library Import")
    st.sidebar.info("⚠️ **Important:** When importing, use 'Web Link' or 'DOI' options, NOT 'Open PDF' or 'Inst. Access' - this app extracts from HTML pages only.")


    st.sidebar.markdown("---")
    st.sidebar.subheader("Upload File")
    upload_file = st.sidebar.file_uploader(
        "Upload JSON/CSV",
        type=["json", "csv"],
        key="lean_upload"
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("API Configuration")
    api_endpoint = st.sidebar.text_input(
        "API Endpoint (XHR URL)",
        placeholder="https://site.com/api/items",
        key="lean_api_endpoint"
    )
    collection_id = st.sidebar.text_input(
        "Collection ID",
        placeholder="1054271",
        key="lean_collection_id"
    )
    authorization_header = st.sidebar.text_input(
        "Authorization Header",
        placeholder="Bearer <token>",
        type="password",
        key="lean_api_auth"
    )

    with st.sidebar.expander("🍪 Authentication Cookies"):
        st.markdown("""
**Get cookies from DevTools:**
1. Open library (logged in)
2. DevTools → Application → Cookies
3. Copy all and paste below
""")
    
    cookie_input = st.sidebar.text_area(
        "Paste cookies",
        height=100,
        placeholder="name=value; name2=value2",
        key="lean_cookie_input"
    )
    
    cookie_header = parse_cookies(cookie_input)

    st.sidebar.markdown("---")
    rate_limit_delay = st.sidebar.slider(
        "⏱️ Request delay (seconds)",
        min_value=0.5,
        max_value=5.0,
        value=2.0,
        step=0.5,
        help="Increase if getting 403 errors"
    )

    if st.sidebar.button("✓ Validate Cookies"):
        if not cookie_input:
            st.sidebar.error("No cookies provided")
        else:
            cookies_check = cookie_header_to_dict(cookie_header)
            s = build_session(cookies_check)
            try:
                check_url = api_endpoint or "https://sciwheel.com/work/"
                resp = s.get(check_url, timeout=15, headers={"User-Agent": get_random_user_agent()})
                if resp.status_code == 200 and "login" not in resp.url.lower():
                    st.sidebar.success(f"✅ Valid")
                else:
                    st.sidebar.warning(f"⚠️ May be invalid")
            except Exception as e:
                st.sidebar.error(f"❌ Failed: {str(e)[:100]}")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        fetch_btn = st.button("🔍 Fetch", key="btn_fetch")
    with col2:
        debug_btn = st.button("🐛 Debug", key="btn_debug")

    if fetch_btn and api_endpoint:
        with st.spinner("Fetching..."):
            links = fetch_items_api(api_endpoint, authorization_header, cookie_header, collection_id)
            links = [l for l in links if not l.get("title", "").startswith("❌")]
        
        if links:
            st.session_state["lean_fetched_links"] = links
            st.sidebar.success(f"✅ Found {len(links)} links")

    # ========================================================================
    # MAIN AREA
    # ========================================================================
    articles = load_articles()
    
    st.header("📊 Library Overview")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Articles", len(articles))
    with col2:
        articles_with_text = sum(1 for a in articles if a.get("text"))
        st.metric("With Full Text", articles_with_text)
    with col3:
        failed_articles = sum(1 for a in articles if a.get("import_status") == "failed")
        st.metric("Failed Imports", failed_articles)
    with col4:
        fetched = st.session_state.get("lean_fetched_links", [])
        st.metric("Ready to Import", len(fetched))

    # Display fetched links
    if fetched:
        st.divider()
        st.subheader("📋 Fetched Links")
        
        max_preview = min(20, len(fetched))
        for i, item in enumerate(fetched[:max_preview]):
            st.write(f"{i+1}. {item.get('title') or item['url'][:60]}")
        
        if len(fetched) > max_preview:
            st.info(f"Showing {max_preview} of {len(fetched)} links")

        st.markdown("---")
        st.subheader("⚙️ Batch Import")
        
        import_pos = st.session_state.lean_import_pos
        total = len(fetched)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            batch_size = st.number_input(
                "Batch size",
                min_value=1,
                max_value=max(1, total - import_pos),
                value=min(10, total - import_pos),
                step=1
            )
        with col2:
            st.metric("Progress", f"{import_pos}/{total}")

        col_a, col_b = st.columns(2)
        with col_a:
            import_batch_btn = st.button("▶️ Import Batch", type="primary")
        with col_b:
            reset_pos = st.button("🔄 Reset")

        if reset_pos:
            st.session_state.lean_import_pos = 0
            st.success("Position reset")
            st.rerun()

        if import_batch_btn:
            start = import_pos
            end = min(start + batch_size, total)
            sublist = fetched[start:end]

            articles = load_articles()
            existing_urls = {a.get("url") for a in articles}
            
            progress_bar = st.progress(0)
            status_container = st.empty()
            
            cookies_dict = cookie_header_to_dict(cookie_header)
            
            new_articles, logs, imported = process_article_batch(
                sublist, start, cookies_dict, existing_urls, rate_limit_delay
            )
            
            if new_articles:
                articles.extend(new_articles)
                save_articles(articles)
                gc.collect()
            
            st.session_state.lean_import_log = logs
            st.session_state.lean_import_pos = end
            
            progress_bar.progress(100)
            status_container.success(f"✅ Added {imported} articles. Position: {end}/{total}")
            
            if logs:
                with st.expander("View import log"):
                    for line in logs:
                        st.write(line)
            
            st.rerun()

    # ========================================================================
    # SEARCH & ANALYSIS
    # ========================================================================
    if articles:
        st.divider()
        st.header("🔍 Search & Analysis")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input(
                "Search query",
                placeholder="e.g., 'What are the key findings about cell growth?'"
            )
        with col2:
            top_k = st.slider("Results", 1, min(20, len(articles)), 5)

        if query:
            results = search_articles(query, articles, top_k=top_k)
            
            if not results:
                st.warning("No matching articles found")
            else:
                st.subheader(f"Found {len(results)} articles")
                for article, score in results:
                    with st.expander(f"**{article['title']}** ({score:.1%})"):
                        if article.get("url"):
                            st.write(f"**URL:** {article['url']}")
                        if article.get("abstract"):
                            st.write(f"**Abstract:** {article['abstract']}")
                        if article.get("text"):
                            preview = article['text'][:500]
                            st.write(f"**Preview:** {preview}...")

                st.divider()
                st.subheader("🤖 AI Analysis")
                api_key = get_openai_client()
                
                if api_key:
                    if st.button("Get AI Analysis", type="primary"):
                        articles_context = "\n\n---\n\n".join([
                            f"**{a['title']}**\n{a.get('text') or a.get('abstract') or 'No content'}"
                            for a, _ in results
                        ])
                        with st.spinner("Analyzing..."):
                            analysis = call_openai_analysis(query, articles_context, api_key)
                        st.write(analysis)
                else:
                    st.info("Set OPENAI_API_KEY to enable AI analysis")

    # ========================================================================
    # ARTICLE MANAGEMENT
    # ========================================================================
    st.sidebar.divider()
    st.sidebar.header("📖 Manage Articles")
    
    if articles:
        # Mass deletion options
        with st.sidebar.expander("🗑️ Mass Delete"):
            st.write("**Delete by status:**")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Delete Failed", help="Remove articles that failed to import"):
                    failed_ids = [a["id"] for a in articles if a.get("import_status") == "failed"]
                    if failed_ids:
                        articles = [a for a in articles if a["id"] not in failed_ids]
                        save_articles(articles)
                        st.success(f"Deleted {len(failed_ids)} failed articles")
                        st.rerun()
                    else:
                        st.info("No failed articles to delete")
            
            with col2:
                if st.button("Delete Empty", help="Remove articles with no text"):
                    empty_ids = [a["id"] for a in articles if not a.get("text")]
                    if empty_ids:
                        articles = [a for a in articles if a["id"] not in empty_ids]
                        save_articles(articles)
                        st.success(f"Deleted {len(empty_ids)} empty articles")
                        st.rerun()
                    else:
                        st.info("No empty articles to delete")
            
            st.write("**Delete all:**")
            if st.button("⚠️ Delete ALL Articles", type="secondary"):
                st.session_state["confirm_delete_all"] = True
            
            if st.session_state.get("confirm_delete_all"):
                st.warning("⚠️ This will delete ALL articles permanently!")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("✓ Confirm", type="primary"):
                        save_articles([])
                        st.session_state["confirm_delete_all"] = False
                        st.success("All articles deleted")
                        st.rerun()
                with col_b:
                    if st.button("✗ Cancel"):
                        st.session_state["confirm_delete_all"] = False
                        st.rerun()
        
        # View/delete individual articles
        with st.sidebar.expander(f"Articles ({len(articles)})"):
            for article in articles:
                col1, col2 = st.columns([3, 1])
                with col1:
                    title_display = article['title'][:40] + "..." if len(article['title']) > 40 else article['title']
                    status_icon = "❌" if article.get("import_status") == "failed" else "✅"
                    st.write(f"{status_icon} **{title_display}**")
                    if article.get("import_status") == "failed" and article.get("import_reason"):
                        st.caption(f"Reason: {article['import_reason'][:60]}...")
                with col2:
                    if st.button("🗑️", key=f"del_{article['id']}", help="Delete"):
                        delete_article(article['id'])
                        st.rerun()
        
        # Failed imports summary
        failed = [a for a in articles if a.get("import_status") == "failed"]
        if failed:
            st.sidebar.divider()
            with st.sidebar.expander(f"⚠️ Failed Imports ({len(failed)})"):
                st.write("**Common failure reasons:**")
                reasons = {}
                for a in failed:
                    reason = a.get("import_reason", "Unknown")
                    # Categorize reasons
                    if "403" in reason or "Forbidden" in reason:
                        key = "403 Forbidden (auth required)"
                    elif "404" in reason:
                        key = "404 Not Found"
                    elif "paywall" in reason.lower():
                        key = "Paywall/login required"
                    elif "too short" in reason.lower():
                        key = "Content too short"
                    elif "no extractable text" in reason.lower():
                        key = "PDF scan (no text)"
                    else:
                        key = "Other errors"
                    
                    reasons[key] = reasons.get(key, 0) + 1
                
                for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
                    st.write(f"• {reason}: **{count}**")
                
                st.info("💡 **Tips:**\n- Use 'Web Link' option instead of 'Open PDF'\n- Add institutional login cookies for 403 errors\n- Try VPN for blocked sites\n- Some sites require manual download")

if __name__ == "__main__":
    run_app()