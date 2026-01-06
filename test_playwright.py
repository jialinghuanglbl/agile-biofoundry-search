from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import sys
import socket
import os
import time
from urllib.parse import urlparse, quote
from typing import Optional, Tuple

class AcademicArticleFetcher:
    """Robust fetcher for academic articles with multiple fallback strategies."""
    
    BLOCKED_DOMAINS = {
        "annualreviews.org", "acs.org", "science.org", 
        "sciencedirect.com", "wiley.com", "springer.com", 
        "ieeexplore.ieee.org", "nature.com", "cell.com",
        "pnas.org", "journals.asm.org", "liebertpub.com",
        "tandfonline.com", "sagepub.com", "karger.com"
    }
    
    EZPROXY_FORMATS = {
        "login_url": "https://proxy.lbl.gov/login?url={url}",
        "prefix": "https://{domain}.proxy.lbl.gov{path}",
        "subdomain": "https://proxy-lbl-gov.{domain}{path}",
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
    
    def __init__(self, ezproxy_username: Optional[str] = None, 
                 ezproxy_password: Optional[str] = None,
                 headless: bool = True,
                 debug: bool = False):
        """Initialize fetcher with optional credentials."""
        self.ezproxy_username = ezproxy_username or os.getenv('EZPROXY_USER')
        self.ezproxy_password = ezproxy_password or os.getenv('EZPROXY_PASS')
        self.headless = headless
        self.debug = debug
    
    def check_proxy_reachable(self, proxy_host: str = "proxy.lbl.gov", 
                              port: int = 443, timeout: int = 5) -> bool:
        """Check if proxy server is reachable."""
        try:
            socket.create_connection((proxy_host, port), timeout=timeout)
            if self.debug:
                print(f"✓ {proxy_host}:{port} is reachable")
            return True
        except (socket.timeout, socket.error) as e:
            if self.debug:
                print(f"✗ Cannot reach {proxy_host}:{port} - {e}")
            return False
    
    def check_vpn_status(self) -> bool:
        """Check if likely connected to VPN by testing proxy reachability."""
        return self.check_proxy_reachable()
    
    def get_domain_info(self, url: str) -> Tuple[str, bool]:
        """Extract domain and check if it's in blocked list."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
        needs_proxy = any(blocked in domain for blocked in self.BLOCKED_DOMAINS)
        return domain, needs_proxy
    
    def generate_ezproxy_urls(self, url: str) -> list:
        """Generate different EZproxy URL formats to try."""
        parsed = urlparse(url)
        domain = parsed.netloc
        
        urls = []
        
        # Format 1: login?url= (most common)
        urls.append(("login_url", f"https://proxy.lbl.gov/login?url={quote(url)}"))
        
        # Format 2: domain prefix
        prefix_url = url.replace("://", f"://{domain}.proxy.lbl.gov/")
        urls.append(("prefix", prefix_url))
        
        # Format 3: subdomain style
        subdomain_url = url.replace(f"://{domain}", f"://proxy-lbl-gov.{domain}")
        urls.append(("subdomain", subdomain_url))
        
        return urls
    
    def try_authentication(self, page) -> bool:
        """Attempt to authenticate on EZproxy login page."""
        if not self.ezproxy_username or not self.ezproxy_password:
            print("⚠ No EZproxy credentials provided")
            return False
        
        # Common EZproxy login form selectors
        login_selectors = [
            ('input[name="user"]', 'input[name="pass"]', 'input[type="submit"]'),
            ('input[name="username"]', 'input[name="password"]', 'input[type="submit"]'),
            ('#username', '#password', 'button[type="submit"]'),
            ('input[id*="user"]', 'input[id*="pass"]', 'button'),
        ]
        
        for user_sel, pass_sel, submit_sel in login_selectors:
            try:
                if page.locator(user_sel).count() > 0:
                    print(f"  → Found login form, attempting authentication...")
                    page.fill(user_sel, self.ezproxy_username, timeout=5000)
                    page.fill(pass_sel, self.ezproxy_password, timeout=5000)
                    page.click(submit_sel, timeout=5000)
                    page.wait_for_load_state('networkidle', timeout=30000)
                    print(f"  → After auth: {page.url}")
                    return True
            except Exception as e:
                if self.debug:
                    print(f"  → Auth attempt failed with selectors {user_sel}: {e}")
                continue
        
        return False
    
    def extract_content(self, page) -> Optional[str]:
        """Try to extract article content using multiple selectors."""
        for selector in self.CONTENT_SELECTORS:
            try:
                element = page.locator(selector).first
                content = element.inner_text(timeout=3000)
                if len(content) > 200:
                    if self.debug:
                        print(f"  ✓ Content extracted using '{selector}': {len(content)} chars")
                    return content
            except:
                continue
        return None
    
    def check_access_denied(self, page) -> bool:
        """Check if page shows access denied messages."""
        try:
            page_text = page.inner_text('body', timeout=5000).lower()
            for phrase in self.ACCESS_DENIED_PHRASES:
                if phrase in page_text:
                    if self.debug:
                        print(f"  ✗ Found access denied phrase: '{phrase}'")
                    return True
        except:
            pass
        return False
    
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
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/Los_Angeles',
                )
                
                page = context.new_page()
                
                print(f"→ Navigating to: {url}")
                
                try:
                    response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    print(f"  Status: {response.status}")
                    print(f"  Final URL: {page.url}")
                except PlaywrightTimeout:
                    print("  ✗ Timeout - page took too long to load")
                    browser.close()
                    return False, None
                except Exception as e:
                    print(f"  ✗ Navigation failed: {str(e)}")
                    browser.close()
                    return False, None
                
                # Check if we're on a login page
                if "login" in page.url.lower():
                    print("  → Login page detected")
                    if not self.try_authentication(page):
                        print("  ✗ Authentication failed or not attempted")
                        browser.close()
                        return False, None
                
                # Wait a bit for dynamic content
                page.wait_for_timeout(2000)
                
                # Check for access denied
                if self.check_access_denied(page):
                    print("  ✗ Access denied detected on page")
                    browser.close()
                    return False, None
                
                # Try to extract content
                content = self.extract_content(page)
                
                if content and len(content) > 200:
                    print(f"  ✓ SUCCESS: Extracted {len(content)} characters")
                    print(f"  Preview: {content[:200]}...")
                    
                    # Save debug screenshot if enabled
                    if self.debug:
                        screenshot_name = f"success_{method_name.replace(' ', '_')}.png"
                        page.screenshot(path=screenshot_name)
                        print(f"  → Screenshot saved: {screenshot_name}")
                    
                    browser.close()
                    return True, content
                else:
                    print("  ✗ No substantial content found")
                    
                    # Save debug screenshot
                    screenshot_name = f"failed_{method_name.replace(' ', '_')}.png"
                    page.screenshot(path=screenshot_name)
                    print(f"  → Screenshot saved: {screenshot_name}")
                    
                    browser.close()
                    return False, None
                    
        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return False, None
    
    def fetch(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Main method to fetch article using all available strategies.
        Returns (success: bool, content: Optional[str])
        """
        print(f"\n{'='*60}")
        print(f"FETCHING: {url}")
        print(f"{'='*60}")
        
        domain, needs_proxy = self.get_domain_info(url)
        print(f"Domain: {domain}")
        print(f"Needs proxy: {needs_proxy}")
        
        # Check VPN status
        vpn_connected = self.check_vpn_status()
        print(f"VPN/Proxy reachable: {vpn_connected}")
        
        # Strategy 1: Try direct access first (if on VPN or not a blocked domain)
        if vpn_connected or not needs_proxy:
            print("\n→ Strategy 1: Direct access")
            success, content = self.try_fetch_with_method(url, "Direct Access")
            if success:
                return True, content
        
        # Strategy 2: Try EZproxy if needed and VPN is connected
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
                
                # Brief delay between attempts
                time.sleep(1)
        
        # Strategy 3: Try direct access even if we think it needs proxy
        # (sometimes institutional access is granted via IP)
        if needs_proxy and not vpn_connected:
            print("\n→ Strategy 3: Direct access (fallback)")
            print("  Note: VPN not detected, but trying anyway...")
            success, content = self.try_fetch_with_method(url, "Direct Access (Fallback)")
            if success:
                return True, content
        
        # All strategies failed
        print(f"\n{'='*60}")
        print("ALL STRATEGIES FAILED")
        print(f"{'='*60}")
        
        if needs_proxy and not vpn_connected:
            print("\n💡 Suggestions:")
            print("  1. Connect to LBL VPN and try again")
            print("  2. Verify your EZproxy credentials")
            print("  3. Check if the article URL is correct")
        
        return False, None


def main():
    """Main entry point for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Fetch academic articles with automatic fallback strategies'
    )
    parser.add_argument('url', help='URL of the article to fetch')
    parser.add_argument('--username', help='EZproxy username (or set EZPROXY_USER env var)')
    parser.add_argument('--password', help='EZproxy password (or set EZPROXY_PASS env var)')
    parser.add_argument('--no-headless', action='store_true', help='Show browser window')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--output', '-o', help='Save content to file')
    
    args = parser.parse_args()
    
    # Create fetcher
    fetcher = AcademicArticleFetcher(
        ezproxy_username=args.username,
        ezproxy_password=args.password,
        headless=not args.no_headless,
        debug=args.debug
    )
    
    # Fetch article
    success, content = fetcher.fetch(args.url)
    
    if success and content:
        print(f"\n{'='*60}")
        print("SUCCESS!")
        print(f"{'='*60}")
        print(f"Extracted {len(content)} characters")
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Content saved to: {args.output}")
        else:
            print("\nContent preview:")
            print(content[:500])
            print("...")
        
        return 0
    else:
        print("\n❌ Failed to fetch article")
        return 1


if __name__ == "__main__":
    sys.exit(main())