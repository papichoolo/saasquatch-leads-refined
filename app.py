# app_optimized.py
import json
import time
import ssl
from typing import Optional, List
import asyncio
from email.message import EmailMessage
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
import os
from dotenv import load_dotenv

# Import functions from the notebook code
import httpx
import re
import html
import tldextract
from urllib.parse import urljoin
import smtplib
from urllib import robotparser
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import Tavily enrichment module
from tavily_enricher import tavily_enrich_lead, tavily_enrich_batch
from email_gen import generate_email as gen_email, EmailContent
from email_gen import generate_email, EmailContent

# Load environment variables
load_dotenv(override=True)

app = FastAPI(title="Lead Enrichment API (Optimized)", version="2.0.0")

# Configuration
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_MAPS") or "YOUR_GOOGLE_PLACES_KEY"
#BING_API_KEY = os.getenv("BING_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")          # e.g. your@gmail.com
SMTP_PASS = os.getenv("GMAIL_PASSWORD")
UA = os.getenv("USER_AGENT") or "SaasquatchLeadsBot/1.0 (+contact@example.com)"
REQ_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT") or "8")  # Reduced from 12s
MAX_WORKERS = int(os.getenv("MAX_WORKERS") or "5")  # Parallel requests

CLEANERS = [
    (re.compile(r"\s*\(at\)\s*|\s*\[at\]\s*|\s+at\s+", re.I), "@"),
    (re.compile(r"\s*\(dot\)\s*|\s*\[dot\]\s*|\s+dot\s+", re.I), "."),
    (re.compile(r"\s+"), ""),
]

FREE_DOMAINS = {
    "gmail.com","yahoo.com","outlook.com","hotmail.com","aol.com","icloud.com",
    "proton.me","protonmail.com","yandex.com","zoho.com"
}

# Pydantic models
class EnrichRequest(BaseModel):
    keyword: str
    location: str
    max_results: Optional[int] = 20
    skip_enrichment: Optional[bool] = False  # Skip slow website crawling
    max_pages_per_site: Optional[int] = 2    # Limit pages crawled (was 6)

class TavilyEnrichRequest(BaseModel):
    name: str
    website: Optional[str] = None
    location: Optional[str] = None
    existing_emails: Optional[list[str]] = None
    existing_linkedin: Optional[str] = None
    max_queries: Optional[int] = 3
    fetch_pages: Optional[bool] = False

class TavilyBatchRequest(BaseModel):
    leads: list[dict]  # Each dict has: name, website, location, emails, linkedin
    max_queries_per_lead: Optional[int] = 2

class GenerateEmailRequest(BaseModel):
    name: str
    website: str
    rec_email: str
    
class SendEmailRequest(BaseModel):
    to: List[EmailStr] = Field(..., description="Recipient emails")
    subject: str
    body: str
    is_html: bool = False
    from_addr: Optional[EmailStr] = None     # default to SMTP_USER
    smtp_user: Optional[str] = None          # user-defined SMTP email
    smtp_pass: Optional[str] = None          # user-defined app password

class SendEmailResponse(BaseModel):
    sent: bool
    to: List[EmailStr]
    subject: str

# Helper functions - optimized versions
def google_places_search_text(text_query, field_mask):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": field_mask,
    }
    with httpx.Client(timeout=REQ_TIMEOUT) as client:
        resp = client.post(
            "https://places.googleapis.com/v1/places:searchText",
            json={"textQuery": text_query},
            headers=headers)
        resp.raise_for_status()
        return resp.json().get("places", [])

def google_place_details(place_resource_name, field_mask):
    headers = {
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": field_mask,
    }
    url = f"https://places.googleapis.com/v1/{place_resource_name}"
    with httpx.Client(timeout=REQ_TIMEOUT) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()

def fetch_with_timeout(url, timeout=5):
    """Fetch URL with shorter timeout - fail fast"""
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers={"User-Agent": UA}, follow_redirects=True)
            r.raise_for_status()
            return r.text
    except Exception:
        return None

def normalize_email(raw):
    s = html.unescape(raw)
    for pat, repl in CLEANERS:
        s = pat.sub(repl, s)
    s = s.strip().strip(".,;:()[]{}<>")
    m = re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", s, re.I)
    return m.group(0).lower() if m else None

def extract_emails_from_html(html_text):
    if not html_text:
        return []
    found = set()
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        for a in soup.select('a[href^="mailto:"]'):
            raw = a.get("href","")[7:]
            e = normalize_email(raw)
            if e:
                found.add(e)
    except Exception:
        pass
    return sorted(found)

def find_linkedin_on_site(html_text):
    if not html_text:
        return None
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "linkedin.com/company/" in href or "linkedin.com/in/" in href:
                return href.split("?")[0]
    except Exception:
        pass
    return None

def likely_company_emails(emails, site_domain):
    out = []
    for e in emails:
        dom = e.split("@")[-1]
        if dom in FREE_DOMAINS:
            continue
        out.append(e)
    return sorted(set(out))

def candidate_paths_limited(base, max_pages=2):
    """Return limited candidate paths for faster crawling"""
    base = base.rstrip("/")
    all_paths = [
        base,              # Homepage (most likely)
        base+"/contact",   # Contact page (most likely)
        base+"/contact-us",
        base+"/about",
        base+"/team",
        base+"/support"
    ]
    return all_paths[:max_pages]

def enrich_site_fast(website, max_pages=2):
    """Optimized version - parallel fetching, shorter timeouts, limited pages"""
    if not website:
        return [], None
    
    extracted = tldextract.extract(website)
    reg_domain = f"{extracted.domain}.{extracted.suffix}" if extracted.suffix else extracted.domain
    base = website if website.startswith("http") else "http://" + website
    
    emails, linkedin = set(), None
    urls_to_check = candidate_paths_limited(base, max_pages)
    
    # Parallel fetch with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_url = {executor.submit(fetch_with_timeout, url, 5): url for url in urls_to_check}
        
        for future in as_completed(future_to_url):
            html_text = future.result()
            if html_text:
                try:
                    emails |= set(extract_emails_from_html(html_text))
                    if not linkedin:
                        linkedin = find_linkedin_on_site(html_text)
                except Exception:
                    continue
    
    filtered_emails = likely_company_emails(sorted(emails), reg_domain)
    return filtered_emails, linkedin

# Streaming generator - optimized
def iter_enrich(keyword: str, location: str, max_results: int = 20, 
                skip_enrichment: bool = False, max_pages_per_site: int = 2):
    """Optimized generator with timing information"""
    field_mask_search = "places.name,places.id,places.displayName,places.formattedAddress"
    field_mask_details = "id,displayName,formattedAddress,internationalPhoneNumber,websiteUri"
    
    start_time = time.time()
    
    try:
        places = google_places_search_text(f"{keyword} in {location}", field_mask_search)
    except Exception as e:
        yield json.dumps({"type": "error", "message": f"Failed to search places: {str(e)}"}) + "\n"
        return
    
    search_time = time.time() - start_time
    
    places = places[:max_results]
    total = len(places)
    
    yield json.dumps({
        "type": "meta",
        "total": total,
        "keyword": keyword,
        "location": location,
        "search_time_ms": round(search_time * 1000, 2),
        "skip_enrichment": skip_enrichment
    }) + "\n"
    
    for idx, p in enumerate(places, 1):
        item_start = time.time()
        
        name = (p.get("displayName") or {}).get("text")
        addr = p.get("formattedAddress")
        resource_name = p.get("name") or p.get("id")
        
        if not resource_name:
            yield json.dumps({
                "type": "skip",
                "idx": idx,
                "name": name,
                "reason": "No resource name"
            }) + "\n"
            continue
        
        try:
            det = google_place_details(resource_name, field_mask_details)
        except Exception as e:
            yield json.dumps({
                "type": "error",
                "idx": idx,
                "name": name,
                "error": str(e)
            }) + "\n"
            continue
        
        website = det.get("websiteUri")
        phone = det.get("internationalPhoneNumber")
        
        # Conditionally enrich based on flag
        emails, linkedin = [], None
        enrichment_time_ms = 0
        
        if not skip_enrichment and website:
            enrich_start = time.time()
            try:
                emails, linkedin = enrich_site_fast(website, max_pages_per_site)
            except Exception as e:
                pass
            enrichment_time_ms = round((time.time() - enrich_start) * 1000, 2)
        
        item_time_ms = round((time.time() - item_start) * 1000, 2)
        
        payload = {
            "type": "item",
            "idx": idx,
            "name": name,
            "address": addr,
            "phone": phone,
            "website": website,
            "emails": emails,
            "linkedin": linkedin,
            "timing": {
                "total_ms": item_time_ms,
                "enrichment_ms": enrichment_time_ms
            }
        }
        yield json.dumps(payload, separators=(",", ":")) + "\n"
    
    total_time = time.time() - start_time
    
    yield json.dumps({
        "type": "complete",
        "total_processed": total,
        "total_time_ms": round(total_time * 1000, 2),
        "avg_time_per_lead_ms": round((total_time / total * 1000) if total > 0 else 0, 2)
    }) + "\n"

# API Endpoints
@app.get("/")
def read_root():
    return {
        "service": "Lead Enrichment API (Optimized)",
        "version": "2.0.0",
        "optimizations": [
            "Parallel website fetching",
            "Reduced timeouts (8s -> 5s per page)",
            "Limited pages per site (2 instead of 6)",
            "Option to skip enrichment entirely",
            "Performance timing in responses",
            "Tavily AI-powered fallback enrichment"
        ],
        "endpoints": {
            "/v1/enrich.ndjson": "POST - Stream enriched leads as NDJSON",
            "/v1/enrich-fast.ndjson": "POST - Fast mode (no enrichment)",
            "/v1/tavily-enrich": "POST - Enrich single lead with Tavily AI search",
            "/v1/tavily-enrich-batch": "POST - Batch enrich with Tavily (max 50 leads)",
            "/v1/generate-email": "POST - Generate a personalized cold email (Google GenAI)",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
def health_check():
    api_key_configured = bool(GOOGLE_PLACES_API_KEY and GOOGLE_PLACES_API_KEY != "YOUR_GOOGLE_PLACES_KEY")
    return {
        "status": "healthy",
        "google_api_configured": api_key_configured,
        "max_workers": MAX_WORKERS
    }

@app.post("/v1/enrich.ndjson")
def enrich_ndjson(request: EnrichRequest):
    """
    Stream enriched lead data as NDJSON with optimization options.
    
    Parameters:
    - skip_enrichment: Skip slow website crawling (2-3x faster)
    - max_pages_per_site: Limit pages crawled per website (default: 2)
    """
    if not GOOGLE_PLACES_API_KEY or GOOGLE_PLACES_API_KEY == "YOUR_GOOGLE_PLACES_KEY":
        raise HTTPException(status_code=500, detail="Google Places API key not configured")
    
    return StreamingResponse(
        iter_enrich(
            request.keyword,
            request.location,
            request.max_results,
            request.skip_enrichment,
            request.max_pages_per_site
        ),
        media_type="application/x-ndjson"
    )

@app.post("/v1/enrich-fast.ndjson")
def enrich_fast_ndjson(request: EnrichRequest):
    """
    Fast mode: Get places with contact info, skip email/LinkedIn enrichment.
    This is 5-10x faster than full enrichment.
    """
    if not GOOGLE_PLACES_API_KEY or GOOGLE_PLACES_API_KEY == "YOUR_GOOGLE_PLACES_KEY":
        raise HTTPException(status_code=500, detail="Google Places API key not configured")
    
    return StreamingResponse(
        iter_enrich(
            request.keyword,
            request.location,
            request.max_results,
            skip_enrichment=True,  # Fast mode
            max_pages_per_site=0
        ),
        media_type="application/x-ndjson"
    )

def _send_email(from_addr: str, to_addrs: List[str], subject: str, body: str, is_html: bool, smtp_user: str, smtp_pass: str):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    if is_html:
        msg.set_content("Your client may not support HTML.")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

@app.post("/v1/send", response_model=SendEmailResponse)
def send(req: SendEmailRequest):
    from_addr = req.from_addr or req.smtp_user or SMTP_USER
    smtp_user = req.smtp_user or SMTP_USER
    smtp_pass = req.smtp_pass or SMTP_PASS
    if not smtp_user or not smtp_pass:
        raise HTTPException(status_code=400, detail="SMTP user and app password required.")
    try:
        _send_email(from_addr, req.to, req.subject, req.body, req.is_html, smtp_user, smtp_pass)
        return SendEmailResponse(sent=True, to=req.to, subject=req.subject)
    except smtplib.SMTPAuthenticationError as e:
        raise HTTPException(status_code=401, detail="SMTP auth failed")
    except smtplib.SMTPException as e:
        raise HTTPException(status_code=502, detail=f"SMTP error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@app.post("/v1/tavily-enrich")
def tavily_enrich(request: TavilyEnrichRequest):
    """
    Use Tavily AI search to enrich a single lead with emails and LinkedIn.
    
    This is a fallback/supplementary enrichment tool when direct scraping fails.
    Uses AI-powered web search to find contact information.
    
    Cost: ~$0.005-0.015 per lead (based on number of queries)
    
    Request body:
    - name: Business name (required)
    - website: Optional website URL
    - location: Optional location
    - existing_emails: Skip email search if already have emails
    - existing_linkedin: Skip LinkedIn search if already have it
    - max_queries: Limit API calls (default 3, max 5) to control costs
    - fetch_pages: Whether to fetch result pages for deeper extraction (slower)
    
    Response includes:
    - emails: List of found emails (ranked)
    - linkedin: LinkedIn profile/company URL
    - sources: URLs where data was found
    - api_calls_made: Number of Tavily API calls
    - cost_estimate_usd: Estimated cost of this enrichment
    """
    import os
    tavily_key = os.getenv("TAVILY_API_KEY")
    print(tavily_key)
    if not tavily_key or tavily_key == "YOUR_TAVILY_KEY":
        print("[ERROR] Tavily API key not configured. Set TAVILY_API_KEY environment variable.")
        return {
            "error": "Tavily API key not configured. Set TAVILY_API_KEY environment variable.",
            "status": "failed"
        }

    try:
        result = tavily_enrich_lead(
            name=request.name,
            website=request.website,
            location=request.location,
            existing_emails=request.existing_emails,
            existing_linkedin=request.existing_linkedin,
            max_queries=min(request.max_queries, 5),  # Cap at 5
            fetch_pages=request.fetch_pages
        )
        print(f"Tavily Enrich Result: {result}")
        if not result or (isinstance(result, dict) and result.get("error")):
            print(f"[ERROR] Tavily enrichment failed: {result}")
            return {
                "error": "Tavily enrichment failed.",
                "details": result,
                "status": "failed"
            }
        return result
    except Exception as e:
        print(f"[ERROR] Exception during Tavily enrichment: {e}")
        return {
            "error": "Exception during Tavily enrichment.",
            "details": str(e),
            "status": "failed"
        }

@app.post("/v1/generate-email", response_model=EmailContent)
def generate_email_endpoint(request: GenerateEmailRequest):
    """Generate a personalized email grounded on the company's website content."""
    try:
        # Delegate to email_gen.generate_email which returns EmailContent
        result = gen_email(name=request.name, website=request.website, rec_email=request.rec_email)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email generation failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
