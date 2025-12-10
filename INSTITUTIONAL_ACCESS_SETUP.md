# Setting Up Institutional Access for Article Import

## Quick Start: Get Institutional Cookies Working

### Step 1: Authenticate
1. Open your browser in a **new private/incognito window**
2. Go to a blocked journal (e.g., `https://www.annualreviews.org/`)
3. You should see a login screen or redirect
4. **Log in with your institutional email** (first.last@youruni.edu)
5. Confirm you can access an article on the journal site

### Step 2: Extract Cookies
1. Open **DevTools** (F12 or Right-click → Inspect)
2. Go to the **Application** tab (or "Storage" in Firefox)
3. In the sidebar, click **Cookies** → expand and click the **journal domain** (e.g., www.annualreviews.org)
4. You should see a table of cookies with columns: Name, Value, Domain, Path, etc.
5. **Select all rows** (Ctrl+A)
6. **Copy** (Ctrl+C)

### Step 3: Configure in App
1. Open the Agile Biofoundry app
2. Scroll to **"Paste cookies here (will auto-format)"** text area
3. **Paste** the cookies (Ctrl+V)
4. Click **"Validate cookies"** button
5. You should see ✅ "Cookies look valid"

### Step 4: Import Articles
1. Go to **"Batch size"** slider → set to `10`
2. Click **"Import next batch and extract content"**
3. Watch for articles from the journal you authenticated with to succeed

---

## Troubleshooting

### "Cookies validate but articles still fail (403)"
**Problem:** Cookies are valid but specific domains still block requests.

**Solutions:**
1. **Try a different journal first** to confirm some domains work
2. **Re-authenticate** on that journal (cookies may have expired)
3. **Use VPN** for that institution's proxy
4. **Check if it's a paywall limit** (sometimes institutions limit simultaneous downloads)

### "Validation succeeds but app crashes"
**Problem:** Cookies are valid but cause issues during import.

**Solution:**
1. **Start with a smaller batch** (batch size = 5)
2. **Clear browser cookies** and re-extract (sometimes corrupted cookies cause issues)
3. **Try without cookies** (some public sites work fine without auth)

### "I don't see my institution's cookies"
**Problem:** You're not actually logged in.

**Steps to verify login:**
1. In DevTools, go to **Console** tab
2. Type: `document.cookie`
3. If you see a list of cookies → you ARE logged in, extract them
4. If it's empty → you're NOT logged in, redo Step 1 of Quick Start

---

## Advanced: Using Library Proxy

Some institutions offer a **proxy URL** that authenticates you automatically.

### Example (Check with Your Library)
Format: `https://proxy.youruni.edu/login?url=TARGET_URL`

**To use with Agile Biofoundry:**
1. Convert blocked URLs using your proxy
2. Edit the article URLs to use the proxy format
3. Or contact your library for a browser extension that auto-proxies

---

## Finding Your Institution's Details

### University Library Websites
1. Go to youruni.edu/library (or similar)
2. Search for: "proxy", "remote access", "off-campus access"
3. Download any **VPN client** listed
4. Note the **proxy URL format** (if available)

### Email Support
- Library email: `library@youruni.edu` or `reference@youruni.edu`
- Ask: "How do I access journals off-campus?"
- They'll provide VPN details and proxy instructions

---

## Multi-Institution Setup (Researchers at Multiple Schools)

If you have access to multiple institutions:

1. **Create separate batches** (one per institution)
2. **Authenticate to each institution's network** or use their VPN
3. **Extract cookies for each domain** separately
4. **Note which cookies are for which journals**
5. **You can add multiple cookies** to the app (paste all at once, separated by semicolons)

---

## When Articles Still Won't Load

### Last Resorts (in order of effectiveness)

1. **Search Google Scholar**
   - Go to https://scholar.google.com/
   - Search article title
   - Click "[PDF]" if available
   - Often links to freely available versions

2. **Try preprint servers**
   - arXiv: https://arxiv.org/ (physics, math, CS)
   - bioRxiv: https://www.biorxiv.org/ (biology)
   - medRxiv: https://www.medrxiv.org/ (medicine)
   - SSRN: https://ssrn.com/ (social science)

3. **Email the authors**
   - Find contact info on paper's first page
   - Email: "Hi, I'd love a copy of your paper [title]. Could you share it?"
   - Most researchers will send it immediately

4. **Check ResearchGate**
   - https://www.researchgate.net/
   - Many researchers post their papers here
   - Search by title or author

5. **Check institutional repositories**
   - Go to youruni.edu/repository or similar
   - Search for papers by your institution's authors
   - Often have full-text access

---

## Summary Table

| Method | Success Rate | Setup Time | Access |
|--------|------|---------|---------|
| Institutional Login + Cookies | 90%+ | 5 min | Any network |
| VPN + Auth | 85%+ | 10 min | Requires VPN client |
| Library Proxy | 80% | 5 min | Limited per institution |
| Google Scholar | 60% | 1 min | Any network |
| arXiv/bioRxiv | 40% | 1 min | Any network |
| Email authors | 70% | 24+ hrs | Requires author contact |

---

**Last updated:** December 10, 2025
**Questions?** Check your institution's library support or contact your research advisor.
