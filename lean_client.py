import os
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
except Exception:
    pdfplumber = None


def _get_headers_from_secrets(secrets: Dict) -> Dict[str, str]:
    # Prefer API key
    if not secrets:
        return {}
    api_key = secrets.get("api_key") or secrets.get("apiKey")
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}

    # Try client credentials (requires token_url)
    # client_id = secrets.get("client_id")
    # client_secret = secrets.get("client_secret")
    # token_url = secrets.get("token_url")
    # if client_id and client_secret and token_url:
    #     resp = requests.post(token_url, data={
    #         "grant_type": "client_credentials",
    #         "client_id": client_id,
    #         "client_secret": client_secret,
    #     }, timeout=30)
    #     resp.raise_for_status()
    #     token = resp.json().get("access_token")
    #     if token:
    #         return {"Authorization": f"Bearer {token}"}

    return {}


def _try_endpoints(base_url: str, project_id: str) -> List[str]:
    # Generates URL endpoints to try
    base = base_url.rstrip("/")
    return [
        f"{base}/v1/projects/{project_id}/articles",
        f"{base}/v1/projects/{project_id}/items",
        f"{base}/projects/{project_id}/articles",
        f"{base}/projects/{project_id}/items",
    ]


def fetch_articles_raw(project_id: str, headers: Dict[str, str], base_url: str = "https://api.leanlibrary.com") -> List[Dict]:
    # Try the endpoints and return the first successful JSON list
    endpoints = _try_endpoints(base_url, project_id)
    last_exc = None
    for url in endpoints:
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            # If data contains 'results' or 'items', favor that
            if isinstance(data, dict):
                for key in ("results", "items", "articles", "data"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                # if dict but looks like one item, wrap
                if any(k in data for k in ("id", "title")):
                    return [data]
            elif isinstance(data, list):
                return data
        except Exception as e:
            last_exc = e
            continue
    if last_exc:
        raise last_exc
    return []

# Download article content and extracts from PDF w/pdfplumber and HTML w/beautifulsoup
def _download_and_extract(url: str, dest_txt: Path, dest_pdf: Optional[Path] = None) -> str:
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
    except Exception:
        return ""

    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype or (dest_pdf is not None and url.lower().endswith(".pdf")):
        if dest_pdf is None:
            dest_pdf = dest_txt.with_suffix(".pdf")
        with open(dest_pdf, "wb") as f:
            for chunk in r.iter_content(1024 * 64):
                f.write(chunk)
        if pdfplumber:
            try:
                with pdfplumber.open(dest_pdf) as pdf:
                    texts = [p.extract_text() or "" for p in pdf.pages]
                text = "\n\n".join(texts)
                dest_txt.write_text(text, encoding="utf-8")
                return text
            except Exception:
                return ""
        else:
            return ""

    # Otherwise assume HTML/text
    text = ""
    try:
        # decode content as text
        content = r.content
        soup = BeautifulSoup(content, "lxml")
        # try to extract article body heuristically
        article = soup.find("article")
        if article:
            text = article.get_text(separator="\n", strip=True)
        else:
            body = soup.find("body")
            if body:
                text = body.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)
    except Exception:
        text = ""

    try:
        dest_txt.write_text(text or "", encoding="utf-8")
    except Exception:
        pass
    return text

# Caches download article content locally to articles.json
def fetch_and_cache(project_id: str, secrets: Dict, data_dir: str = "data") -> List[Dict]:
    data_path = Path(data_dir)
    files_dir = data_path / "files"
    data_path.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    headers = _get_headers_from_secrets(secrets)
    base_url = secrets.get("api_base", "https://api.leanlibrary.com")
    raw_articles = fetch_articles_raw(project_id, headers, base_url=base_url)

    articles_out = []
    for a in raw_articles:
        # try to extract common fields
        aid = a.get("id") or a.get("article_id") or str(time.time()).replace('.', '')
        title = a.get("title") or a.get("name") or "Untitled"
        url = a.get("url") or a.get("link") or a.get("pdf_url") or a.get("pdf")
        authors = a.get("authors") or a.get("author") or []

        txt_path = files_dir / f"{aid}.txt"
        pdf_path = files_dir / f"{aid}.pdf"
        text = ""
        if url:
            try:
                text = _download_and_extract(url, txt_path, pdf_path)
            except Exception:
                text = ""

        snippet = (text or "")[:500]
        out = {
            "id": aid,
            "title": title,
            "url": url,
            "authors": authors,
            "text": text,
            "snippet": snippet,
            "raw": a,
        }
        articles_out.append(out)

    # Save to articles.json
    with open(data_path / "articles.json", "w", encoding="utf-8") as f:
        json.dump(articles_out, f, ensure_ascii=False, indent=2)

    return articles_out

# loads articles for streamlit_app.py
def load_cached_articles(path: str) -> List[Dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
