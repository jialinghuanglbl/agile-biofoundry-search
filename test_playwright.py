from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import sys
from urllib.parse import urlparse, quote
import os

def test_playwright_vpn(url, ezproxy_username=None, ezproxy_password=None):
    """Test Playwright with academic site access via EZproxy."""
    
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower().replace('www.', '')
    
    # More comprehensive list
    blocked_domains = {
        "annualreviews.org", "acs.org", "science.org", 
        "sciencedirect.com", "wiley.com", "springer.com", 
        "ieeexplore.ieee.org", "nature.com", "cell.com",
        "pnas.org", "journals.asm.org", "liebertpub.com"
    }
    
    use_ezproxy = any(blocked in domain for blocked in blocked_domains)
    
    if use_ezproxy:
        ezproxy_url = f"https://proxy.lbl.gov/login?url={quote(url)}"
        print(f"Using EZproxy for {domain}: {ezproxy_url}")
        target_url = ezproxy_url
    else:
        target_url = url
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/Los_Angeles',
                # Important: accept downloads and handle redirects
                accept_downloads=False,
                ignore_https_errors=False
            )
            
            page = context.new_page()
            
            # Navigate to URL
            response = page.goto(target_url, wait_until='domcontentloaded', timeout=30000)
            
            # If EZproxy, handle authentication
            if use_ezproxy and "login" in page.url.lower():
                print("Detected login page, attempting authentication...")
                
                if not ezproxy_username or not ezproxy_password:
                    print("ERROR: EZproxy credentials required but not provided")
                    return False
                
                # Wait for login form (adjust selectors based on your EZproxy)
                try:
                    page.fill('input[name="user"]', ezproxy_username, timeout=5000)
                    page.fill('input[name="pass"]', ezproxy_password, timeout=5000)
                    page.click('input[type="submit"]', timeout=5000)
                    
                    # Wait for redirect to actual article
                    page.wait_for_load_state('networkidle', timeout=30000)
                    print(f"After auth, redirected to: {page.url}")
                except PlaywrightTimeout:
                    print("ERROR: Login form not found or timeout during authentication")
                    return False
            
            # Check final status
            final_response = page.goto(page.url, wait_until='networkidle', timeout=30000)
            print(f"Final status: {final_response.status}")
            print(f"Final URL: {page.url}")
            
            # More robust content detection
            if final_response.status in [200, 304]:
                # Try multiple selectors
                selectors = [
                    'article',
                    'main',
                    '[role="main"]',
                    '.article-body',
                    '.article-content',
                    '#article-content',
                    '.main-content'
                ]
                
                content = None
                for selector in selectors:
                    try:
                        element = page.locator(selector).first
                        content = element.inner_text(timeout=3000)
                        if len(content) > 200:
                            print(f"✓ Content extracted using selector: {selector}")
                            print(f"Preview: {content[:300]}...")
                            break
                    except:
                        continue
                
                if not content or len(content) < 200:
                    print("⚠ Page loaded but minimal content extracted")
                    # Take screenshot for debugging
                    page.screenshot(path="debug_screenshot.png")
                    print("Screenshot saved to debug_screenshot.png")
                    return False
                
                return True
            else:
                print(f"✗ Failed with status {final_response.status}")
                return False
                
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            browser.close()
        except:
            pass

if __name__ == "__main__":
    # Get credentials from environment or arguments
    username = os.getenv('EZPROXY_USER')
    password = os.getenv('EZPROXY_PASS')
    
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.nature.com/articles/s41586-020-2012-7"
    
    success = test_playwright_vpn(test_url, username, password)
    sys.exit(0 if success else 1)