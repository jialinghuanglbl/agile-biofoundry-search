# Handling Blocked Content in Agile Biofoundry Search

## Why Some Articles Can't Be Downloaded

Many academic and scientific journals implement **bot detection and access restrictions** that prevent automated downloading. These include:

### Common Blocked Domains
- **Annual Reviews** (`annualreviews.org`) - Strict bot detection
- **ACS Publications** (`acs.org`) - Chemical Society paywalls
- **Nature** (`nature.com`) - Premium scientific journal
- **Science** (`science.org`) - Premium scientific journal
- **Elsevier** (`sciencedirect.com`) - Large journal publisher
- **Wiley** (`wiley.com`) - Academic publisher
- **Springer** (`springer.com`) - Academic publisher
- **IEEE** (`ieeexplore.ieee.org`) - Engineering/technology paywalls

## Solutions

### 1. **Use Your Institutional Access** (Recommended)
Most universities and research institutions have subscriptions to these publishers.

**Steps:**
1. Visit the article link directly in your browser while on your institutional network
2. If prompted, log in with your institutional credentials
3. Note: Institutional cookies work better when you're authenticated

### 2. **Use a VPN** (If Remote)
If you're off-campus, use your institution's VPN:

1. Connect to your institution's VPN
2. Paste your institutional credentials into the app's cookie field
3. Re-run the import batch

### 3. **Use Library Proxy URLs**
Many institutions provide proxy URLs that authenticate you. Example format:
```
https://proxy.youruni.edu/login?url=https://example.com/article
```

Ask your institution's library for their proxy URL format.

### 4. **Use DOI Links as Fallback**
The app stores DOI identifiers. You can use them to access articles:

1. Go to https://doi.org/{DOI} (e.g., https://doi.org/10.1146/example)
2. Often redirects to a publicly available version or a better access method
3. Some authors self-archive papers on repositories like arXiv or their institution

### 5. **Check Open Access Repositories**
For open-access versions:
- **arXiv** (`arxiv.org`) - Physics, math, CS preprints
- **bioRxiv** (`biorxiv.org`) - Biology preprints
- **PubMed Central** (`pmc.ncbi.nlm.nih.gov`) - Open access biomedical articles
- **SSRN** (`ssrn.com`) - Social science and other papers

## Best Practices

### Optimize Cookie Authentication
1. Log into your institutional account on a journal site
2. Open DevTools → Application → Cookies
3. Copy **all** cookies from the domain
4. Paste into the app's cookie field
5. Click "Validate cookies"
6. Re-run the import

### Batch Import Strategy
- **Start with small batches** (10 items) to identify which domains are blocking you
- **Check the import summary** for a list of blocked domains
- **Address auth issues** before larger imports (adds 20+ articles at a time)

### Track What Works
Keep notes on which:
- Cookies succeed with which domains
- VPNs work best for your region
- DOI links provide good fallback access

## Example Workflow

1. **First import (10 items)** → See which sites block you
2. **Get institutional credentials/VPN** → Connect and validate cookies
3. **Second import (next 10 items)** → Many previously-blocked items now succeed
4. **Batch larger imports** → Once you've confirmed auth works

## When to Give Up on a Domain

If after trying auth and VPN an article still fails:
- The content may be **truly inaccessible** outside that institution
- Use the **DOI link** (https://doi.org/xxxx) as an alternative
- Check if a **preprint version** exists on arXiv or the author's website
- Some recent papers have **freely available** author versions

## Support

If you have questions about specific institutions or domains:
1. Check your institution's library website for proxy/VPN info
2. Contact your institution's research support team
3. Email the paper's authors for a copy (many authors will send you their work directly)

---

**Last updated:** December 10, 2025
