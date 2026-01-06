#!/usr/bin/env python3
"""
Test script to verify Playwright + VPN setup for bypassing 403 errors.
Run this locally after connecting to LBL VPN.
"""

from playwright.sync_api import sync_playwright
import sys

def test_playwright_vpn(url="https://www.nature.com/articles/s41586-020-2012-7"):
    """Test Playwright with a known paywall URL."""
    # Check if domain is blocked and use EZproxy
    from urllib.parse import urlparse, quote
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower().replace('www.', '')
    blocked_domains = {
        "acs.org", "science.org", 
        "sciencedirect.com", "wiley.com", "springer.com", "ieeexplore.ieee.org"
    }
    if any(blocked in domain for blocked in blocked_domains):
        ezproxy_url = f"https://proxy.lbl.gov/login?url={quote(url)}"
        print(f"Domain {domain} is blocked - using EZproxy: {ezproxy_url}")
        url = ezproxy_url
    
    print(f"Testing Playwright with URL: {url}")
    print("This should work if VPN + Playwright + EZproxy are set up correctly...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu'
                ]
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/Los_Angeles'
            )

            page = context.new_page()
            response = page.goto(url, wait_until='networkidle', timeout=30000)

            print(f"Response status: {response.status}")
            print(f"Response URL: {response.url}")

            if response.status == 200:
                # Try to extract some content
                content = page.locator('article, main, .article-content').first.inner_text(timeout=5000)
                if len(content) > 100:
                    print("SUCCESS: Extracted content!")
                    print(f"Content preview: {content[:200]}...")
                else:
                    print("WARNING: Page loaded but content extraction failed")
            else:
                print(f"FAILED: Got status {response.status}")

            browser.close()

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    else:
        test_url = "https://www.nature.com/articles/s41586-020-2012-7"  # Example paywall URL

    success = test_playwright_vpn(test_url)
    if success:
        print("\nPlaywright + VPN test completed.")
    else:
        print("\nPlaywright test failed.")