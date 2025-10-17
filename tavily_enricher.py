"""
Optimized Tavily-based lead enrichment
Uses Tavily AI search to find emails and LinkedIn when direct scraping fails
"""
import os
import re
import time
from dotenv import load_dotenv
import html
import tldextract
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

load_dotenv(override=True)

# ---------- config ----------
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
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
    
    # Extract city from location for more targeted searches
    city = None
    if location:
        # Try to extract city name (first part before comma)
        city = location.split(',')[0].strip()
    
    # Only query what we need
    if need_emails and need_linkedin:
        # Comprehensive query first
        if company_domain:
            queries.append(f'site:{company_domain} (email OR contact OR linkedin)')
        # Add location to make more specific
        if city:
            queries.append(f'"{name}" {city} contact email')
            queries.append(f'"{name}" {city} linkedin')
        else:
            queries.append(f'"{name}" contact email linkedin')
    
    elif need_emails:
        # Email-focused
        if company_domain:
            queries.append(f'site:{company_domain} (email OR contact)')
        if city:
            queries.append(f'"{name}" {city} contact email')
        else:
            queries.append(f'"{name}" contact email')
    
    elif need_linkedin:
        # LinkedIn-focused  
        if city:
            queries.append(f'"{name}" {city} linkedin')
        else:
            queries.append(f'"{name}" linkedin company profile')
    
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
    
    if not TAVILY_API_KEY:
        print("[ERROR] TAVILY_API_KEY is not set in environment variables.")
        return {
            "emails": [],
            "linkedin": None,
            "sources": {},
            "queries_run": [],
            "api_calls_made": 0,
            "cost_estimate_usd": 0.0,
            "error": "TAVILY_API_KEY is not set in environment variables."
        }
    
    print("[DEBUG] tavily_enrich_lead called with:", {
        "name": name,
        "website": website,
        "location": location,
        "existing_emails": existing_emails,
        "existing_linkedin": existing_linkedin,
        "max_queries": max_queries,
        "fetch_pages": fetch_pages
    })
    # Determine what we need
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
    queries = queries[:max_queries]

    found_emails = set()
    found_linkedins = set()
    sources = {}
    api_calls = 0

    # Run queries sequentially
    for q in queries:
        results = _tavily_search(q, max_results=5)
        api_calls += 1
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

    # Filter and rank emails
    filtered_emails = []
    if need_emails:
        # First try company emails (if we have a domain)
        if company_domain:
            filtered_emails = [e for e in found_emails if _is_company_email(e, company_domain)]
        
        # If no company emails found (or no domain), accept any non-free emails
        if not filtered_emails:
            filtered_emails = [e for e in found_emails if e.split("@")[-1].lower() not in FREE_DOMAINS]
        
        # Sort by quality
        filtered_emails = sorted(filtered_emails, key=_rank_email, reverse=True)
    else:
        filtered_emails = existing_emails or []

    linkedin = sorted(found_linkedins)[0] if found_linkedins else (existing_linkedin or None)
    cost_estimate = api_calls * 0.005

    return {
        "emails": filtered_emails,
        "linkedin": linkedin,
        "sources": {k: sorted(v) for k, v in sources.items()},
        "queries_run": queries,
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
