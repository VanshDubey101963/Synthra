import os
import sys
import time
import json
import math
import hashlib
import datetime
import google.generativeai as genai
from typing import List, Dict, Any, Tuple


import requests 
from bs4 import BeautifulSoup
from readability import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors



try: 
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass 



GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")


LLM_MODEL = os.getenv("LLM_MODEL", "gemini-1.5-flash-latest")



HEADERS = {"User-Agent": "ResearchAgent/1.0 (+https://github.com/YugShrivastava/AI-TaskForce)"}\




# ========Utilities=======

def has_internet(url = 'https://www.google.com', timeout=3) -> bool:
    try:
        requests.get(url, timeout=timeout)
        return True
    except Exception:
        return False
    

# print(has_internet())


def safe_filename(s: str) -> str:
    h = hashlib.sha1(s.encode("utf8")).hexdigest()[:8]
    return "".join(c for c in s if c.isalnum() or c in " _-")[:40] + "_" + h




#-------------------------search SerpAPI---------------------------------------------

def search_serpapi(query:str, num_results:int = 5) -> List[Dict[str,Any]]:
    if not SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY not set.")
    params = {'engine': 'google', 'q': query, 'num': num_results, 'api_key':SERPAPI_API_KEY}
    rsp = requests.get("https://serpapi.com/search.json", params=params, headers=HEADERS, timeout=15)
    rsp.raise_for_status()
    data = rsp.json()
    results = []
    organic = data.get("organic_results") or data.get("organic") or []
    for r in organic[:num_results]:
        results.append({
            "title": r.get("title"),
            "url": r.get("link") or r.get("url"),
            "snippet": r.get("snippet") or r.get("snippet_text") or ""
        })
    return results



#----------------fetch & extract ------------------------------
def fetch_page_text(url: str, save_snapshot: bool = True) -> Tuple[str, Dict[str, Any]]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return f"", {"url": url, "error": str(e)}
    # Save snapshot
    if save_snapshot:
        os.makedirs("snapshots", exist_ok=True)
        fn = os.path.join("snapshots", safe_filename(url) + ".html")
        with open(fn, "w", encoding="utf8") as f:
            f.write(html)
    # Extract main content with readability
    try:
        doc = Document(html)
        content_html = doc.summary()
        title = doc.short_title()
        text = BeautifulSoup(content_html, "html.parser").get_text("\n")
        meta = {"url": url, "title": title}
        return text.strip(), meta
    except Exception:
        # fallback: plain text
        text = BeautifulSoup(html, "html.parser").get_text("\n")
        return text.strip(), {"url": url, "title": None}
    


########################LLM WRAPPER(gemini)#######################

def call_gemini_chat(prompt: str, system: str = "You are an assistant that helps with research tasks.", max_tokens: int = 2048) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set. Please set environment variable or provide key.")

    genai.configure(api_key=GEMINI_API_KEY)
    
    # New generation config
    generation_config = {
        "temperature": 0.0,
        "max_output_tokens": max_tokens,
    }

    # Initialize model with the system instruction
    model = genai.GenerativeModel(
        model_name=LLM_MODEL,
        generation_config=generation_config,
        system_instruction=system,
    )

    try:
        # Correct way to call the API
        response = model.generate_content(prompt)
        # Ensure response text is accessed correctly
        if response.parts:
            return response.text.strip()
        else:
            # Handle cases where the response might be blocked or empty
            return "[LLM_ERROR] Received an empty response from the API."
    except Exception as e:
        return f"[LLM_ERROR] {e}"

    

# ==== Prompt templates ====
CLAIM_EXTRACTION_PROMPT = """You are an extractor that reads an article and returns a JSON array of concise factual claims.
Return strictly valid JSON with the structure:
{{"claims":[{{"id":1,"claim":"...","span":"text snippet (short)"}}, ...]}}

Article text:
<<ARTICLE>>
"""

VERIFY_CLAIM_PROMPT = """You are an evidence evaluator. Given a single claim and a short source excerpt, answer ONLY in JSON:
{{"support":"supports|contradicts|neutral|uncertain", "confidence":0.0-1.0, "evidence":"short excerpt showing support or contradiction", "reason":"one-sentence reason"}}

Claim:
<<CLAIM>>

Source excerpt:
<<EXCERPT>>

Source URL: <<URL>>
"""

AGGREGATE_PROMPT = """You are an aggregator. Given evaluations of a claim across multiple sources (JSON list),
produce JSON: {{"claim_id":<id>,"aggregate_support":"supports|contradicts|mixed|insufficient","score":0.0-1.0,"best_evidence":{{"url":"...","excerpt":"...","confidence":...}},"notes":[ "..."]}}

Evaluations:
<<EVALS>>
"""

# ==== Verification helpers ====
def extract_claims_from_text(article_text: str) -> List[Dict[str, Any]]:
    prompt = CLAIM_EXTRACTION_PROMPT.replace("<<ARTICLE>>", article_text[:3000])  # truncate large articles
    out = call_gemini_chat(prompt, system="You extract factual claims from article text.")
    # Expecting JSON; try to parse
    try:
        j = json.loads(out)
        return j.get("claims", [])
    except Exception:
        # bit of robust parsing: try to find first JSON block
        import re
        m = re.search(r"\{.*\}", out, flags=re.S)
        if m:
            try:
                j = json.loads(m.group(0))
                return j.get("claims", [])
            except Exception:
                return []
        return []

def evaluate_claim_vs_excerpt(claim: str, excerpt: str, url: str) -> Dict[str, Any]:
    prompt = VERIFY_CLAIM_PROMPT.replace("<<CLAIM>>", claim).replace("<<EXCERPT>>", excerpt[:1200]).replace("<<URL>>", url)
    out = call_gemini_chat(prompt, system="You evaluate evidence for claims based on a short excerpt.")
    try:
        j = json.loads(out)
        return j
    except Exception:
        # fallback: try to parse a bit
        return {"support": "uncertain", "confidence": 0.0, "evidence": excerpt[:200], "reason": out}

def aggregate_evaluations(claim_id: int, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Simple numeric scoring: supports=+1, neutral=+0.5, contradicts=-1, uncertain=0
    mapping = {"supports": 1.0, "neutral": 0.5, "contradicts": -1.0, "uncertain": 0.0}
    total = 0.0
    count = 0
    best = None
    best_score = -999
    notes = []
    for ev in evaluations:
        s = ev.get("support", "uncertain")
        conf = float(ev.get("confidence", 0.0) or 0.0)
        score = mapping.get(s, 0.0) * conf
        total += score
        count += 1
        if score > best_score:
            best_score = score
            best = {"url": ev.get("url",""), "excerpt": ev.get("evidence",""), "confidence": conf}
        notes.append(f"{s} ({conf:.2f}) - {ev.get('reason','')[:120]}")
    if count == 0:
        agg_score = 0.0
    else:
        # normalize to 0..1 for convenience
        # we scale by possible max: supports=1*1 per item; min could be -1*1
        raw = total / count  # in range roughly -1..1
        agg_score = (raw + 1) / 2  # map -1..1 -> 0..1
        agg_score = max(0.0, min(1.0, agg_score))
    if agg_score > 0.66:
        label = "supports"
    elif agg_score < 0.33:
        label = "contradicts"
    elif count == 0:
        label = "insufficient"
    else:
        label = "mixed"
    return {"claim_id": claim_id, "aggregate_support": label, "score": round(agg_score, 3), "best_evidence": best, "notes": notes}

# ==== PDF generation ====
def generate_pdf_report(query: str, claims: List[Dict[str, Any]], verified: List[Dict[str, Any]], articles: List[Dict[str, Any]], out_path: str):
    os.makedirs("reports", exist_ok=True)
    if not out_path:
        out_path = os.path.join("reports", safe_filename(query) + ".pdf")
    doc = SimpleDocTemplate(out_path, pagesize=A4)
    styles = getSampleStyleSheet()
    body = []
    title_style = styles["Title"]
    body.append(Paragraph(f"Research Report: {query}", title_style))
    body.append(Spacer(1, 12))
    body.append(Paragraph(f"Generated: {datetime.datetime.utcnow().isoformat()} UTC", styles["Normal"]))
    body.append(Spacer(1, 12))
    body.append(Paragraph("Executive Summary:", styles["Heading2"]))
    # summary by LLM (optional)
    try:
        summ_prompt = f"Summarize findings for query: {query} given {len(claims)} claims and verifications."
        summ = call_gemini_chat(summ_prompt, system="You provide a short executive summary for research reports.", max_tokens=300)
    except Exception:
        summ = "Summary generation failed."
    body.append(Paragraph(summ, styles["BodyText"]))
    body.append(Spacer(1, 12))

    body.append(Paragraph("Findings (claims):", styles["Heading2"]))
    # Table per claim with aggregate label and score and evidence
    for c, v in zip(claims, verified):
        body.append(Paragraph(f"Claim #{c.get('id')}: {c.get('claim')}", styles["Heading3"]))
        body.append(Paragraph(f"Aggregate: {v.get('aggregate_support')} (score={v.get('score')})", styles["Normal"]))
        be = v.get("best_evidence") or {}
        if be:
            body.append(Paragraph("Best evidence:", styles["Normal"]))
            body.append(Paragraph(f"<a href='{be.get('url')}'>{be.get('url')}</a>", styles["Normal"]))
            body.append(Paragraph(f"Excerpt: {be.get('excerpt')}", styles["Italic"]))
        # notes
        body.append(Paragraph("Notes:", styles["Normal"]))
        for n in v.get("notes", [])[:5]:
            body.append(Paragraph(f"- {n}", styles["BodyText"]))
        body.append(Spacer(1, 10))
    body.append(Paragraph("Sources:", styles["Heading2"]))
    data = [["Title", "URL"]]
    for a in articles:
        data.append([a.get("title") or "-", a.get("url")])
    t = Table(data, colWidths=[200, 300])
    t.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.25, colors.grey)]))
    body.append(t)

    doc.build(body)
    return out_path

# ==== High-level pipeline ====
def run_research_pipeline(query: str, top_k: int = 4, verify_per_claim_k: int = 3):
    print(f"[+] Query: {query}")
    if not has_internet():
        print("[!] No internet connection. Aborting.")
        return None
    # 1) Search
    print("[+] Searching web...")
    hits = search_serpapi(query, num_results=top_k)
    print(f"[+] {len(hits)} search hits.")
    # 2) Fetch
    articles = []
    for h in hits:
        text, meta = fetch_page_text(h["url"])
        articles.append({"url": h["url"], "title": h.get("title") or meta.get("title"), "text": text})
        time.sleep(0.5)
    # 3) Extract claims from all article texts (aggregate)
    all_claims = []
    claim_id = 1
    for art in articles:
        if not art["text"]:
            continue
        print(f"[+] Extracting claims from: {art['url']}")
        claims = extract_claims_from_text(art["text"])
        for cl in claims:
            # ensure id unique
            cl["id"] = claim_id
            claim_id += 1
            all_claims.append(cl)
        time.sleep(0.5)
    if not all_claims:
        print("[!] No claims extracted; aborting or generating a simple report.")
        # produce a minimal PDF noting nothing found
        pdf = generate_pdf_report(query, [], [], articles, out_path=f"reports/{safe_filename(query)}_empty.pdf")
        return pdf
    # 4) For each claim, verify across fresh search results
    verified = []
    for cl in all_claims:
        claim_text = cl.get("claim")
        print(f"[+] Verifying Claim #{cl.get('id')}: {claim_text[:120]}")
        # search for the claim itself
        hits_for_claim = search_serpapi(claim_text, num_results=verify_per_claim_k)
        evaluations = []
        for hf in hits_for_claim:
            text_s, meta_s = fetch_page_text(hf["url"], save_snapshot=False)
            excerpt = (text_s or "")[:1200]
            ev = evaluate_claim_vs_excerpt(claim_text, excerpt, hf["url"])
            # enrich evaluation with url for aggregation
            ev["url"] = hf["url"]
            evaluations.append(ev)
            time.sleep(0.4)
        agg = aggregate_evaluations(cl.get("id"), evaluations)
        verified.append(agg)
    # 5) Generate PDF
    pdf = generate_pdf_report(query, all_claims, verified, articles, out_path=None)
    print(f"[+] Report generated: {pdf}")
    return pdf

# ==== CLI entry ====
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python research_agent.py \"Your research query here\"")
        sys.exit(1)
    q = " ".join(sys.argv[1:])
    pdf_path = run_research_pipeline(q, top_k=4, verify_per_claim_k=3)
    if pdf_path:
        print("DONE. PDF:", pdf_path)
    else:
        print("No PDF generated.")  