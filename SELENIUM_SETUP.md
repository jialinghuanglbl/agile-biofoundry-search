# Selenium JavaScript Rendering Support

The app now includes optional Selenium support to handle **JavaScript-heavy sites** that don't render properly with static HTML extraction.

## When Selenium Helps

Pages that require JavaScript to display content:
- Single-page applications (React, Angular, Vue)
- Content loaded dynamically after page load
- Sites with complex DOM manipulation
- Paywalls/login overlays that need rendering

## Installation

### 1. Install Selenium and ChromeDriver

```bash
# Install Selenium
pip install selenium

# Install webdriver-manager for automatic ChromeDriver management
pip install webdriver-manager
```

### 2. Install Google Chrome

Selenium uses Google Chrome in headless mode. Make sure Chrome is installed:

```bash
# Ubuntu/Debian
sudo apt-get install google-chrome-stable

# macOS
brew install google-chrome

# Or download from https://www.google.com/chrome/
```

### 3. Verify Installation

```python
from selenium import webdriver
driver = webdriver.Chrome()
driver.quit()
```

## How It Works

1. **Primary**: Static HTML extraction (fast, lightweight)
2. **Fallback**: If content is too short (<200 chars), Selenium attempts:
   - Renders page with real Chrome browser
   - Waits up to 15 seconds for content to load
   - Extracts rendered HTML using same strategies as step 1

## Configuration

You can adjust the timeout in `streamlit_app.py`:

```python
SELENIUM_TIMEOUT = 15  # seconds to wait for page load
```

Increase if pages take longer to render, decrease for faster fallback to errors.

## Performance Impact

- **First use**: Slow (Chrome startup ~5-10s)
- **Subsequent uses**: Faster (Chrome reused)
- **Memory**: ~100-150MB per browser instance
- **Disabled by default**: Only activates when primary extraction fails

## Troubleshooting

### ChromeDriver Not Found

```
selenium.common.exceptions.SessionNotCreatedException
```

**Solution**: Ensure Google Chrome is installed:
```bash
which google-chrome  # Check if installed
google-chrome --version  # Verify version
```

### Timeout Waiting for Page Load

```
selenium.common.exceptions.TimeoutException
```

**Solution**: 
- Increase `SELENIUM_TIMEOUT` in config
- Check page load times in browser DevTools
- Some sites may never render their content

### Memory Issues

If Selenium causes out-of-memory errors:
- Use smaller batch sizes during import
- Reduce `SELENIUM_TIMEOUT` to exit faster
- Consider using VPN/institutional access instead (faster)

### ChromeDriver Version Mismatch

```
This version of ChromeDriver only supports Chrome version XX
```

**Solution**: 
- Update Chrome: `sudo apt-get update && sudo apt-get upgrade google-chrome-stable`
- Or uninstall ChromeDriver and let webdriver-manager download the correct version

## When NOT to Use Selenium

- Paywalled sites (Selenium won't bypass authentication)
- Institutional access required (provide cookies instead)
- Performance-critical imports (static extraction is faster)

## Alternative: Cookies + VPN

For better success rates, try:
1. Log into journal site with institutional credentials
2. Extract cookies from DevTools
3. Paste cookies in app's cookie field
4. Import with cookies (faster and more reliable than Selenium)

See `INSTITUTIONAL_ACCESS_SETUP.md` for detailed cookie extraction.

## Example Output

When Selenium succeeds, you'll see in import logs:

```
✅ 42: Rendered with Selenium (JavaScript) - Extracted from largest content block (3421 chars)
```

If it fails:

```
❌ 43: Selenium rendering failed: Chrome process crashed (out of memory)
```

## Further Reading

- [Selenium Documentation](https://www.selenium.dev/documentation/)
- [WebDriver Wait Strategies](https://www.selenium.dev/documentation/webdriver/waits/)
- [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/)
