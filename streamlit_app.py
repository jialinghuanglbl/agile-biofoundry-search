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
from urllib.parse import urljoin, urlparse, quote
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Browser automation for JavaScript rendering
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Legacy Selenium fallback
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        WEBDRIVER_MANAGER_AVAILABLE = True
    except Exception:
        WEBDRIVER_MANAGER_AVAILABLE = False
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
SELENIUM_TIMEOUT = 20  # seconds to wait for page load

RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=["HEAD", "GET", "POST"]
)

# Domains known to block automated access - skip gracefully
BLOCKED_DOMAINS = {
    "annualreviews.org", "acs.org", "science.org",
    "sciencedirect.com", "wiley.com", "springer.com",
    "ieeexplore.ieee.org", "nature.com", "cell.com",
    "pnas.org", "journals.asm.org", "liebertpub.com",
    "tandfonline.com", "sagepub.com", "karger.com"
}

CONTENT_SELECTORS = [
    'article',
    'main',
    '[role="main"]',
    '.article-body',
    '.article-content',
    '#article-content',
    '.main-content',
    '.article__body',
    '.content-inner',
    '#content',
    '.fulltext-view',
    '[data-article-body]',
]

ACCESS_DENIED_PHRASES = [
    'access denied', '403', 'forbidden', 'not authorized',
    'subscription required', 'purchase', 'sign in to access',
    'institutional access required', 'paywall'
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# EZproxy for LBL institutional access (use when VPN IP access fails)
EZPROXY_BASE = "https://proxy.lbl.gov/login?url="

# ============================================================================
# SESSION & REQUEST HELPERS
# ============================================================================
def build_session(cookies: Optional[Dict] = None, use_proxy: bool = False) -> requests.Session:
    """Create a requests session with retry logic and proper headers."""
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=RETRY_STRATEGY)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if cookies:
        s.cookies.update(cookies)
    if use_proxy:
        s.proxies = {'http': 'http://proxy.lbl.gov:80', 'https': 'http://proxy.lbl.gov:80'}
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
# CONTENT EXTRACTION WITH INTEGRATED FETCHER LOGIC
# ============================================================================
class AcademicArticleFetcher:
    """Integrated robust fetcher for academic articles with multiple fallback strategies."""

    def __init__(self, ezproxy_username: Optional[str] = None,
                 ezproxy_password: Optional[str] = None,
                 headless: bool = True,
                 debug: bool = False):
        """Initialize fetcher with optional credentials."""
        self.ezproxy_username = ezproxy_username or os.getenv('EZPROXY_USER')
        self.ezproxy_password = ezproxy_password or os.getenv('EZPROXY_PASS')
        self.headless = headless
        self.debug = debug
        
        self.user_agents = USER_AGENTS
        self.current_ua_index = 0

    def check_proxy_reachable(self, proxy_host: str = "proxy.lbl.gov",
                              port: int = 443, timeout: int = 5) -> bool:
        """Check if proxy server is reachable."""
        import socket
        try:
            socket.create_connection((proxy_host, port), timeout=timeout)
            if self.debug:
                print(f"✓ {proxy_host}:{port} is reachable")
            return True
        except (socket.timeout, socket.error) as e:
            if self.debug:
                print(f"✗ Cannot reach {proxy_host}:{port} - {e}")
            return False

    def check_proxy_http(self, test_url: str = "https://proxy.lbl.gov") -> bool:
        """Check if proxy is reachable via HTTP request."""
        try:
            response = requests.get(test_url, timeout=10, allow_redirects=True)
            if self.debug:
                print(f"✓ HTTP test to {test_url}: {response.status_code}")
            return response.status_code in [200, 302, 401, 403]
        except Exception as e:
            if self.debug:
                print(f"✗ HTTP test failed: {e}")
            return False

    def check_vpn_status(self) -> bool:
        """Check if likely connected to VPN by testing proxy reachability."""
        import socket
        try:
            socket.gethostbyname("proxy.lbl.gov")
            if self.debug:
                print("✓ proxy.lbl.gov DNS resolves")
            
            if self.check_proxy_http():
                if self.debug:
                    print("✓ proxy.lbl.gov responds to HTTP")
                return True
            
            return True
        except:
            return self.check_proxy_reachable()

    def get_domain_info(self, url: str) -> Tuple[str, bool]:
        """Extract domain and check if it's in blocked list."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
        needs_proxy = any(blocked in domain for blocked in BLOCKED_DOMAINS)
        return domain, needs_proxy

    def generate_ezproxy_urls(self, url: str) -> list:
        """Generate different EZproxy URL formats to try."""
        parsed = urlparse(url)
        domain = parsed.netloc
        
        urls = []
        urls.append(("login_url", f"https://proxy.lbl.gov/login?url={quote(url)}"))
        prefix_url = url.replace("://", f"://{domain}.proxy.lbl.gov/")
        urls.append(("prefix", prefix_url))
        subdomain_url = url.replace(f"://{domain}", f"://proxy-lbl-gov.{domain}")
        urls.append(("subdomain", subdomain_url))
        
        return urls

    def test_proxy_access(self, url: str) -> dict:
        """Test proxy access using simple HTTP requests before launching browser."""
        results = {
            'direct_access': False,
            'proxy_reachable': False,
            'proxy_login_page': False,
            'needs_auth': False,
            'details': []
        }
        
        try:
            print("\n" + "="*60)
            print("PRE-FLIGHT TESTS")
            print("="*60)
            
            print("\n→ Test 1: Direct access to article")
            try:
                response = requests.get(url, timeout=10, allow_redirects=True)
                results['details'].append(f"Direct access: {response.status_code}")
                print(f" Status: {response.status_code}")
                
                if response.status_code == 200:
                    text_lower = response.text.lower()
                    if 'subscription' in text_lower or 'access denied' in text_lower or 'sign in' in text_lower:
                        print(" ✗ Access denied (paywall detected)")
                    else:
                        print(" ✓ Might have direct access!")
                        results['direct_access'] = True
            except Exception as e:
                print(f" ✗ Failed: {e}")
                results['details'].append(f"Direct access failed: {e}")
            
            print("\n→ Test 2: Proxy server reachability")
            try:
                response = requests.get("https://proxy.lbl.gov", timeout=10, allow_redirects=True)
                results['proxy_reachable'] = True
                print(f" ✓ Proxy responds: {response.status_code}")
                results['details'].append(f"Proxy reachable: {response.status_code}")
            except Exception as e:
                print(f" ✗ Proxy not reachable: {e}")
                results['details'].append(f"Proxy not reachable: {e}")
            
            print("\n→ Test 3: Proxy login URL")
            proxy_url = f"https://proxy.lbl.gov/login?url={quote(url)}"
            try:
                response = requests.get(proxy_url, timeout=10, allow_redirects=True)
                print(f" Status: {response.status_code}")
                print(f" Final URL: {response.url}")
                results['details'].append(f"Proxy login: {response.status_code}")
                
                text_lower = response.text.lower()
                if 'login' in text_lower or 'username' in text_lower or 'password' in text_lower:
                    print(" ✓ Reached proxy login page")
                    results['proxy_login_page'] = True
                    results['needs_auth'] = True
                elif 'annual reviews' in text_lower or 'article' in text_lower:
                    print(" ✓ Got through to article (no auth needed!)")
                    results['proxy_login_page'] = True
                    results['needs_auth'] = False
                else:
                    print(" ? Unclear response")
                    print(f" Preview: {response.text[:200]}")
            except Exception as e:
                print(f" ✗ Failed: {e}")
                results['details'].append(f"Proxy login failed: {e}")
            
        except ImportError:
            print("⚠ requests library not available, skipping HTTP tests")
            results['details'].append("requests library not available")
        
        return results

    def try_authentication(self, page) -> bool:
        """Attempt to authenticate on EZproxy login page."""
        if not self.ezproxy_username or not self.ezproxy_password:
            print("⚠ No EZproxy credentials provided")
            return False
        
        login_selectors = [
            ('input[name="user"]', 'input[name="pass"]', 'input[type="submit"]'),
            ('input[name="username"]', 'input[name="password"]', 'input[type="submit"]'),
            ('#username', '#password', 'button[type="submit"]'),
            ('input[id*="user"]', 'input[id*="pass"]', 'button'),
        ]
        
        for user_sel, pass_sel, submit_sel in login_selectors:
            try:
                if page.locator(user_sel).count() > 0:
                    print(f" → Found login form, attempting authentication...")
                    page.fill(user_sel, self.ezproxy_username, timeout=5000)
                    page.fill(pass_sel, self.ezproxy_password, timeout=5000)
                    page.click(submit_sel, timeout=5000)
                    page.wait_for_load_state('networkidle', timeout=30000)
                    print(f" → After auth: {page.url}")
                    return True
            except Exception as e:
                if self.debug:
                    print(f" → Auth attempt failed with selectors {user_sel}: {e}")
                continue
        
        return False

    def extract_content(self, page) -> Optional[str]:
        """Try to extract article content using multiple selectors."""
        for selector in CONTENT_SELECTORS:
            try:
                element = page.locator(selector).first
                content = element.inner_text(timeout=3000)
                if len(content) > 200:
                    if self.debug:
                        print(f" ✓ Content extracted using '{selector}': {len(content)} chars")
                    return content
            except:
                continue
        return None

    def check_access_denied(self, page) -> bool:
        """Check if page shows access denied messages."""
        try:
            page_text = page.inner_text('body', timeout=5000).lower()
            for phrase in ACCESS_DENIED_PHRASES:
                if phrase in page_text:
                    if self.debug:
                        print(f" ✗ Found access denied phrase: '{phrase}'")
                    return True
        except:
            pass
        return False

    def get_user_agent(self) -> str:
        """Get next user agent from rotation."""
        ua = self.user_agents[self.current_ua_index]
        self.current_ua_index = (self.current_ua_index + 1) % len(self.user_agents)
        return ua

    def try_fetch_with_method(self, url: str, method_name: str) -> Tuple[bool, Optional[str]]:
        """Try to fetch article using a specific method."""
        print(f"\n{'='*60}")
        print(f"Method: {method_name}")
        print(f"{'='*60}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                    ]
                )
                
                context = browser.new_context(
                    user_agent=self.get_user_agent(),
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/Los_Angeles',
                    # Additional fingerprinting resistance
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Upgrade-Insecure-Requests': '1',
                    }
                )
                
                page = context.new_page()
                
                print(f"→ Navigating to: {url}")
                
                try:
                    response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    print(f" Status: {response.status}")
                    print(f" Final URL: {page.url}")
                except PlaywrightTimeout:
                    print(" ✗ Timeout - page took too long to load")
                    browser.close()
                    return False, None
                except Exception as e:
                    print(f" ✗ Navigation failed: {str(e)}")
                    browser.close()
                    return False, None
                
                if "login" in page.url.lower():
                    print(" → Login page detected")
                    if not self.try_authentication(page):
                        print(" ✗ Authentication failed or not attempted")
                        browser.close()
                        return False, None
                
                page.wait_for_timeout(2000)
                
                if self.check_access_denied(page):
                    print(" ✗ Access denied detected on page")
                    browser.close()
                    return False, None
                
                content = self.extract_content(page)
                
                if content and len(content) > 200:
                    print(f" ✓ SUCCESS: Extracted {len(content)} characters")
                    print(f" Preview: {content[:200]}...")
                    
                    if self.debug:
                        screenshot_name = f"success_{method_name.replace(' ', '_')}.png"
                        page.screenshot(path=screenshot_name)
                        print(f" → Screenshot saved: {screenshot_name}")
                    
                    browser.close()
                    return True, content
                else:
                    print(" ✗ No substantial content found")
                    
                    screenshot_name = f"failed_{method_name.replace(' ', '_')}.png"
                    page.screenshot(path=screenshot_name)
                    print(f" → Screenshot saved: {screenshot_name}")
                    
                    browser.close()
                    return False, None
                
        except Exception as e:
            print(f" ✗ Error: {str(e)}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return False, None

    def fetch(self, url: str) -> Tuple[bool, Optional[str]]:
        """Main method to fetch article using all available strategies."""
        print(f"\n{'='*60}")
        print(f"FETCHING: {url}")
        print(f"{'='*60}")
        
        domain, needs_proxy = self.get_domain_info(url)
        print(f"Domain: {domain}")
        print(f"Needs proxy: {needs_proxy}")
        
        vpn_connected = self.check_vpn_status()
        print(f"VPN/Proxy reachable: {vpn_connected}")
        
        test_results = self.test_proxy_access(url)
        
        print("\n" + "="*60)
        print("STRATEGY SELECTION")
        print("="*60)
        
        if test_results['direct_access']:
            print("✓ Pre-flight test suggests direct access works!")
            print(" → Will try direct access first")
        elif test_results['proxy_login_page'] and not test_results['needs_auth']:
            print("✓ Pre-flight test suggests proxy works without auth!")
            print(" → Will prioritize proxy methods")
        elif test_results['proxy_login_page'] and test_results['needs_auth']:
            print("⚠ Proxy requires authentication")
            if self.ezproxy_username:
                print(" → Will attempt login with provided credentials")
            else:
                print(" → No credentials provided, login may fail")
        
        if vpn_connected or not needs_proxy or test_results['direct_access']:
            print("\n→ Strategy 1: Direct access")
            success, content = self.try_fetch_with_method(url, "Direct Access")
            if success:
                return True, content
        
        if needs_proxy and vpn_connected:
            ezproxy_urls = self.generate_ezproxy_urls(url)
            
            for idx, (format_name, ezproxy_url) in enumerate(ezproxy_urls, 1):
                print(f"\n→ Strategy 2.{idx}: EZproxy ({format_name})")
                success, content = self.try_fetch_with_method(
                    ezproxy_url,
                    f"EZproxy - {format_name}"
                )
                if success:
                    return True, content
                
                time.sleep(1)
        
        if needs_proxy and not vpn_connected:
            print("\n→ Strategy 3: Direct access (fallback)")
            print(" Note: VPN not detected, but trying anyway...")
            success, content = self.try_fetch_with_method(url, "Direct Access (Fallback)")
            if success:
                return True, content
        
        print(f"\n{'='*60}")
        print("ALL STRATEGIES FAILED")
        print(f"{'='*60}")
        
        if needs_proxy and not vpn_connected:
            print("\n💡 Suggestions:")
            print(" 1. Connect to LBL VPN and try again")
            print(" 2. Verify your EZproxy credentials")
            print(" 3. Check if the article URL is correct")
        elif test_results['needs_auth'] and not self.ezproxy_username:
            print("\n💡 Suggestions:")
            print(" 1. Provide EZproxy credentials:")
            print(" 2. Or set environment variables:")
            print(" set EZPROXY_USER=your_username")
            print(" set EZPROXY_PASS=your_password")
        
        return False, None

# ============================================================================
# FETCH AND EXTRACT WITH FETCHER
# ============================================================================
def fetch_and_extract_html(url: str, cookies: Optional[Dict] = None, delay: float = 1.0, ezproxy_username: Optional[str] = None, ezproxy_password: Optional[str] = None, debug: bool = False) -> Tuple[str, str]:
    """ 
    Enhanced fetch using AcademicArticleFetcher logic.
    """
    time.sleep(delay)
    
    # Skip direct PDF URLs
    url_lower = url.lower()
    if (url_lower.endswith('.pdf') or
        '/pdf/' in url_lower or
        'download.pdf' in url_lower or
        '/getpdf' in url_lower or
        'pdf?' in url_lower or
        'pdf=' in url_lower):
        return "", f"Skipped: PDF URL detected in path ({url[:80]})"
    
    fetcher = AcademicArticleFetcher(ezproxy_username=ezproxy_username, ezproxy_password=ezproxy_password, headless=True, debug=debug)
    
    success, content = fetcher.fetch(url)
    
    if success and content:
        if len(content) > MAX_ARTICLE_TEXT:
            content = content[:MAX_ARTICLE_TEXT] + "\n\n...[truncated]"
        return content, "Extracted using AcademicArticleFetcher"
    else:
        return "", "Failed to extract content using AcademicArticleFetcher"

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
        
        # Try links array with preferences
        if not raw_url:
            links = a.get("links") or a.get("linkList") or []
            if isinstance(links, list):
                # Check if domain is blocked to prefer Institutional Access
                preferred_type = "Institutional Access" if any(
                    blocked in (a.get("url") or "").lower() for blocked in BLOCKED_DOMAINS
                ) else "Web Link"
                
                for link in links:
                    if isinstance(link, dict) and link.get("type") == preferred_type:
                        raw_url = link.get("url") or link.get("link")
                        url_source = f"links.{preferred_type}"
                        break
                # Fallback to any link if preferred not found
                if not raw_url:
                    for link in links:
                        if isinstance(link, dict) and link.get("url"):
                            raw_url = link.get("url")
                            url_source = f"links.{link.get('type', 'unknown')}"
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
            debug_info.append(f" [{idx}] {article_title}: ❌ No URL found")
            continue

        try:
            resolved = raw_url if raw_url.startswith("http") else urljoin(base + "/", raw_url)
        except Exception:
            resolved = raw_url

        if resolved in seen:
            continue

        title = a.get("title") or a.get("plainTitle") or a.get("name") or None
        debug_info.append(f" [{idx}] {article_title}: ✅ [{url_source}] {resolved[:70]}")
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
    ezproxy_username: Optional[str],
    ezproxy_password: Optional[str],
    rate_limit_delay: float = 2.0,
    debug: bool = False
) -> Tuple[List[Dict], List[str], int]:
    """Process a batch of articles with detailed error reporting using fetcher."""
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
        
        # Skip PDF URLs
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
            extracted, reason = fetch_and_extract_html(url, cookies=cookies_dict, delay=rate_limit_delay, ezproxy_username=ezproxy_username, ezproxy_password=ezproxy_password, debug=debug)
            
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
            logs.append(f" • {domain}: {count} articles")
        logs.append("")
        logs.append("💡 To access blocked content:")
        logs.append(" 1. Institutional login: Use your university/organization credentials")
        logs.append(" 2. VPN: Connect to institutional VPN to bypass geographic restrictions")
        logs.append(" 3. Library proxy: Some institutions provide proxy URLs")
        logs.append(" 4. DOI alternative: Try searching the DOI directly via https://doi.org/")

    return new_articles, logs, imported

# ============================================================================
# STREAMLIT APP
# ============================================================================
def run_app():
    st.set_page_config(page_title="Agile Biofoundry Search", layout="wide")
    st.title("Agile Biofoundry — Article Search & Analysis")

    if "lean_import_pos" not in st.session_state:
        st.session_state.lean_import_pos = 0

    # ========================================================================
    # SIDEBAR: IMPORT & CONFIGURATION
    # ========================================================================
    st.sidebar.header("Library Import")

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

    with st.sidebar.expander("Authentication Cookies"):
        st.markdown(""" **Get cookies from DevTools:**

1. Open library (logged in)

2. DevTools → Application → Cookies

3. Copy all and paste below """)
    
        cookie_input = st.sidebar.text_area(
            "Paste cookies",
            height=100,
            placeholder="name=value; name2=value2",
            key="lean_cookie_input"
        )
    
        cookie_header = parse_cookies(cookie_input)

    with st.sidebar.expander("EZProxy Credentials"):
        ezproxy_username = st.text_input("EZProxy Username", key="ezproxy_username")
        ezproxy_password = st.text_input("EZProxy Password", type="password", key="ezproxy_password")

    st.sidebar.markdown("---")
    rate_limit_delay = st.sidebar.slider(
        "⏱️ Request delay (seconds)",
        min_value=0.5,
        max_value=5.0,
        value=2.0,
        step=0.5,
        help="Increase if getting 403 errors"
    )

    debug_mode = st.sidebar.checkbox("Debug Mode", key="debug_mode")

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
                    st.sidebar.warning(f"May be invalid")
            except Exception as e:
                st.sidebar.error(f"❌ Failed: {str(e)[:100]}")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        fetch_btn = st.button("Fetch", key="btn_fetch")
    with col2:
        debug_btn = st.button("Debug", key="btn_debug")

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
    
    st.header("Library Overview")
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
        st.subheader("Fetched Links")
        
        max_preview = min(20, len(fetched))
        for i, item in enumerate(fetched[:max_preview]):
            st.write(f"{i+1}. {item.get('title') or item['url'][:60]}")
        
        if len(fetched) > max_preview:
            st.info(f"Showing {max_preview} of {len(fetched)} links")

        st.markdown("---")
        st.subheader("Batch Import")
        
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
            import_batch_btn = st.button("Import Batch", type="primary")
        with col_b:
            reset_pos = st.button("Reset")

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
                sublist, start, cookies_dict, existing_urls, 
                ezproxy_username=st.session_state.get("ezproxy_username"),
                ezproxy_password=st.session_state.get("ezproxy_password"),
                rate_limit_delay=rate_limit_delay,
                debug=debug_mode
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
        st.header("Search & Analysis")
        
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
        with st.sidebar.expander("Mass Delete"):
            st.write("**Delete by status:**")
            col1, col2 = st.sidebar.columns(2)
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