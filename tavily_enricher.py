"""
Optimized Tavily-based lead enrichment
Uses Tavily AI search to find emails and LinkedIn when direct scraping fails
"""
import os
import re
import time
import html
import tldextract
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

# ---------- config ----------
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") or "YOUR_TAVILY_KEY"
UA = os.getenv("USER_AGENT") or "LeadFinderBot/1.0 (+contact@example.com)"
REQ_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT") or "12")
BACKOFF = 0.5

FREE_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com",
    "proton.me", "protonmail.com", "yandex.com", "zoho.com"
}

EMAIL_FUZZY = re.compile(r"""
    (?<![\w.+-])
    [A-Z0-9._%+\-]+
    \s*(?:\[at\]|\(at\)|@|\s+at\s+)\s*
    [A-Z0-9.\-]+
    \s*(?:\[dot\]|\(dot\)|\.|\s+dot\s+)\s*
    [A-Z]{2,24}
""", re.I | re.X)

# ---------- helpers ----------
def _normalize_email(raw: str) -> Optional[str]:
    s = html.unescape(raw)
    s = re.sub(r"\s*\(at\)\s*|\s*\[at\]\s*|\s+at\s+", "@", s, flags=re.I)
    s = re.sub(r"\s*\(dot\)\s*|\s*\[dot\]\s*|\s+dot\s+", ".", s, flags=re.I)
    s = s.strip().strip(".,;:()[]{}<>")
    m = re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", s, re.I)
    return m.group(0).lower() if m else None

def _extract_linkedins(text: str) -> set[str]:
    found = set()
    for m in re.findall(r"https?://(www\.)?linkedin\.com/(in|company)/[A-Za-z0-9\-_]+", text or "", flags=re.I):
        url = "https://linkedin.com/" + "/".join(m[1:])
        found.add(url.split("?")[0])  # strip tracking
    return found

def _extract_emails(text: str) -> set[str]:
    found = set()
    for m in EMAIL_FUZZY.findall(text or ""):
        e = _normalize_email(m)
        if e:
            found.add(e)
    # Also check mailto: links
    for mailto in re.findall(r'href=["\']mailto:([^"\']+)["\']', text or "", flags=re.I):
        e = _normalize_email(mailto)
        if e:
            found.add(e)
    return found

def _is_company_email(email: str, company_domain: Optional[str]) -> bool:
    dom = email.split("@")[-1].lower()
    if dom in FREE_DOMAINS:
        return False
    return (company_domain is None) or (company_domain in dom)

def _rank_email(email: str) -> int:
    local = email.split("@")[0].lower()
    # Prefer non-generic mailboxes
    if local in {"info", "hello", "contact", "support", "admin", "sales"}:
        return 10
    if re.fullmatch(r"[a-z]+\.[a-z]+", local) or re.fullmatch(r"[a-z]+", local):
        return 50  # Looks like a person
    return 30

def _company_domain_from_website(website: Optional[str]) -> Optional[str]:
    if not website:
        return None
    ext = tldextract.extract(website)
    if not ext.suffix:
        return None
    return f"{ext.domain}.{ext.suffix}".lower()

def _fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Single Tavily API call"""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
        "include_images": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=REQ_TIMEOUT, headers={"User-Agent": UA})
        r.raise_for_status()
        data = r.json()
        return data.get("results", []) or []
    except Exception:
        return []

def _build_smart_queries(name: str, website: Optional[str], location: Optional[str],
                        need_emails: bool, need_linkedin: bool) -> list[str]:
    """
    Build optimized query list - only what's needed
    OPTIMIZATION: Reduced from 9 queries to 2-4 based on needs
    """
    company_domain = _company_domain_from_website(website)
    queries = []
    
    # Only query what we need
    if need_emails and need_linkedin:
        # Comprehensive query first
        if company_domain:
            queries.append(f'site:{company_domain} (email OR contact OR linkedin)')
        queries.append(f'{name} contact email linkedin')
        if location:
            queries.append(f'{name} {location} contact email')
    
    elif need_emails:
        # Email-focused
        if company_domain:
            queries.append(f'site:{company_domain} (email OR contact)')
        queries.append(f'{name} contact email')
    
    elif need_linkedin:
        # LinkedIn-focused  
        queries.append(f'{name} linkedin company profile')
        if location:
            queries.append(f'{name} {location} linkedin')
    
    return queries[:3]  # Max 3 queries to control costs

def tavily_enrich_lead(
    name: str,
    website: Optional[str] = None,
    location: Optional[str] = None,
    existing_emails: Optional[list[str]] = None,
    existing_linkedin: Optional[str] = None,
    max_queries: int = 3,
    fetch_pages: bool = False
) -> dict:
    """
    OPTIMIZED: Use Tavily to find missing emails/LinkedIn
    
    Args:
        name: Business name
        website: Optional website URL
        location: Optional location
        existing_emails: Skip email search if provided
        existing_linkedin: Skip LinkedIn search if provided
        max_queries: Limit API calls (default 3, max 5)
        fetch_pages: Whether to fetch and parse result pages (slower, more thorough)
    
    Returns:
        {
            "emails": [...],
            "linkedin": "...",
            "sources": {...},
            "api_calls_made": int,
            "cost_estimate_usd": float
        }
    """
    # Skip what we already have
    need_emails = not existing_emails or len(existing_emails) == 0
    need_linkedin = not existing_linkedin
    
    if not need_emails and not need_linkedin:
        return {
            "emails": existing_emails or [],
            "linkedin": existing_linkedin,
            "sources": {},
            "api_calls_made": 0,
            "cost_estimate_usd": 0.0,
            "skipped": "Already has all data"
        }
    
    company_domain = _company_domain_from_website(website)
    queries = _build_smart_queries(name, website, location, need_emails, need_linkedin)
    queries = queries[:max_queries]  # Enforce limit
    
    found_emails: set[str] = set()
    found_linkedins: set[str] = set()
    sources: dict[str, set[str]] = {}
    api_calls = 0
    
    # OPTIMIZATION: Parallel queries instead of sequential
    def run_query(q):
        results = _tavily_search(q, max_results=5)
        return q, results
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_query, q) for q in queries]
        
        for future in as_completed(futures):
            query, results = future.result()
            if results:
                api_calls += 1
            
            # Extract from snippets
            for res in results:
                content = f"{res.get('title','')}\n{res.get('content','')}\n{res.get('url','')}"
                
                if need_emails:
                    for e in _extract_emails(content):
                        found_emails.add(e)
                        sources.setdefault(e, set()).add(res.get("url", ""))
                
                if need_linkedin:
                    for l in _extract_linkedins(content):
                        found_linkedins.add(l)
                        sources.setdefault(l, set()).add(res.get("url", ""))
            
            # OPTIMIZATION: Early exit when both found
            has_good_emails = any(_is_company_email(e, company_domain) for e in found_emails)
            has_linkedin = len(found_linkedins) > 0
            
            if (not need_emails or has_good_emails) and (not need_linkedin or has_linkedin):
                break
    
    # Optional: Fetch pages for deeper extraction (adds time & complexity)
    if fetch_pages and api_calls > 0:
        # Only fetch if we didn't find enough from snippets
        has_good_emails = any(_is_company_email(e, company_domain) for e in found_emails)
        if (need_emails and not has_good_emails) or (need_linkedin and not found_linkedins):
            # Fetch top 2 results only
            all_results = []
            for _, results in [executor.submit(run_query, q).result() for q in queries[:1]]:
                all_results.extend(results[:2])
            
            for res in all_results:
                url = res.get("url")
                if not url:
                    continue
                netloc = urlparse(url).netloc.lower()
                if any(s in netloc for s in ("facebook.com", "instagram.com", "x.com", "twitter.com")):
                    continue
                
                html_text = _fetch(url)
                if html_text:
                    if need_emails:
                        for e in _extract_emails(html_text):
                            found_emails.add(e)
                            sources.setdefault(e, set()).add(url)
                    if need_linkedin:
                        for l in _extract_linkedins(html_text):
                            found_linkedins.add(l)
                            sources.setdefault(l, set()).add(url)
                    time.sleep(BACKOFF)
    
    # Filter and rank emails
    filtered_emails = []
    if need_emails:
        filtered_emails = [e for e in found_emails if _is_company_email(e, company_domain)]
        if not filtered_emails:
            filtered_emails = [e for e in found_emails if e.split("@")[-1].lower() not in FREE_DOMAINS]
        filtered_emails = sorted(filtered_emails, key=_rank_email, reverse=True)
    else:
        filtered_emails = existing_emails or []
    
    # LinkedIn
    linkedin = sorted(found_linkedins)[0] if found_linkedins else (existing_linkedin or None)
    
    # Tavily pricing: ~$0.005 per search (advanced mode)
    cost_estimate = api_calls * 0.005
    
    return {
        "emails": filtered_emails,
        "linkedin": linkedin,
        "sources": {k: sorted(v) for k, v in sources.items()},
        "queries_run": queries[:api_calls],
        "api_calls_made": api_calls,
        "cost_estimate_usd": round(cost_estimate, 4),
        "company_domain": company_domain
    }

# Batch processing
def tavily_enrich_batch(leads: list[dict], max_queries_per_lead: int = 2) -> list[dict]:
    """
    Enrich multiple leads
    
    Args:
        leads: List of dicts with keys: name, website, location, emails, linkedin
        max_queries_per_lead: Limit queries per lead to control costs
    
    Returns:
        List of enrichment results
    """
    results = []
    total_cost = 0.0
    
    for lead in leads:
        result = tavily_enrich_lead(
            name=lead.get("name", ""),
            website=lead.get("website"),
            location=lead.get("location"),
            existing_emails=lead.get("emails", []) if isinstance(lead.get("emails"), list) else [],
            existing_linkedin=lead.get("linkedin"),
            max_queries=max_queries_per_lead,
            fetch_pages=False  # Keep it fast for batch
        )
        results.append(result)
        total_cost += result.get("cost_estimate_usd", 0)
        
        # Small delay between leads
        time.sleep(0.3)
    
    return {
        "leads": results,
        "total_api_calls": sum(r.get("api_calls_made", 0) for r in results),
        "total_cost_estimate_usd": round(total_cost, 2)
    }
