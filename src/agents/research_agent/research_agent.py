
"""

Full ResearchAgent:
- Uses local_llm.llm.get_llm() (Gemini when online / Ollama fallback)
- SerpAPI for web search
- Readability + BeautifulSoup for article extraction
- Claim extraction (LLM) + verification (LLM) with retries/backoff
- Aggregation of evidence
- Sanitized ReportLab PDF (human-readable main body; provenance saved separately)
- Terminal logging (verbose option)
- LangGraph node wrapper available

Requirements:
    pip install requests beautifulsoup4 readability-lxml reportlab tqdm

Environment:
    export SERPAPI_API_KEY="..."
    export GOOGLE_API_KEY="..."   # if using Gemini via langchain_google_genai in your local_llm.llm.get_llm()

Usage:
    python research_agent.py "Theory of Relativity" --top-k 4 --claim-limit 6 --verify-per-claim 3 --workers 4 --verbose
"""

import os
import sys
import time
import json
import hashlib
import datetime
import argparse
import traceback
import logging
import re
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from readability import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether,
    ListFlowable, ListItem
)
from reportlab.lib import colors
from tqdm import tqdm

# Attempt to import LangGraph if present (optional)
try:
    from langgraph.graph import StateGraph, END
except Exception:
    StateGraph = None
    END = None

# Import user's llm getter
try:
    from local_llm.llm import get_llm
except Exception as e:
    print("[ERROR] Could not import local_llm.llm.get_llm(). Ensure local_llm/llm.py exists and defines get_llm().")
    raise

# -------------------------
# Configuration & logging
# -------------------------
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
DEFAULT_TOP_K = 4
DEFAULT_CLAIM_LIMIT = 8
DEFAULT_VERIFY_PER_CLAIM = 3
DEFAULT_WORKERS = 4

HEADERS = {"User-Agent": "ResearchAgent/1.0 (+https://example.local)"}

MAX_LLM_RETRIES = 4
INITIAL_BACKOFF = 2.0

logger = logging.getLogger("research_agent")
logger.setLevel(logging.INFO)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")
stream_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(stream_handler)

# -------------------------
# Utilities
# -------------------------
def safe_filename(s: str) -> str:
    h = hashlib.sha1(s.encode("utf8")).hexdigest()[:8]
    base = "".join(c for c in s if c.isalnum() or c in " _-")[:40].strip()
    if not base:
        base = "report"
    fname = f"{base}_{h}.pdf"
    return fname

def has_internet(host="8.8.8.8", port=53, timeout=3) -> bool:
    import socket
    try:
        socket.setdefaulttimeout(timeout)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.close()
        return True
    except Exception:
        return False

def get_text_from_llm_response(resp: Any) -> str:
    if resp is None:
        return ""
    for attr in ("content", "text", "message", "output"):
        if hasattr(resp, attr):
            try:
                return str(getattr(resp, attr))
            except Exception:
                pass
    if isinstance(resp, dict):
        if "choices" in resp and resp["choices"]:
            c = resp["choices"][0]
            if isinstance(c, dict):
                if "message" in c and isinstance(c["message"], dict) and "content" in c["message"]:
                    return str(c["message"]["content"])
                for k in ("text", "content"):
                    if k in c:
                        return str(c[k])
        return json.dumps(resp)
    return str(resp)

# -------------------------
# SerpAPI search
# -------------------------

def search_serpapi(query: str, num_results: int = 4) -> List[Dict[str, Any]]:
    if not SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY not set. Export SERPAPI_API_KEY in your environment.")
    params = {"engine": "google", "q": query, "num": num_results, "api_key": SERPAPI_API_KEY}
    resp = requests.get("https://serpapi.com/search.json", params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    organic = data.get("organic_results") or data.get("organic") or []
    out = []
    for r in organic[:num_results]:
        out.append({
            "title": r.get("title"),
            "url": r.get("link") or r.get("url"),
            "snippet": r.get("snippet") or r.get("snippet_text") or ""
        })
    return out

# -------------------------
# Fetch & extract
# -------------------------
def fetch_page_text(url: str, save_snapshot: bool = True) -> Tuple[str, Dict[str, Any]]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return "", {"url": url, "error": str(e)}
    if save_snapshot:
        os.makedirs("snapshots", exist_ok=True)
        fn = os.path.join("snapshots", hashlib.sha1(url.encode()).hexdigest() + ".html")
        try:
            with open(fn, "w", encoding="utf8") as f:
                f.write(html)
        except Exception:
            pass
    try:
        doc = Document(html)
        content_html = doc.summary()
        title = doc.short_title()
        text = BeautifulSoup(content_html, "html.parser").get_text("\n")
        return text.strip(), {"url": url, "title": title}
    except Exception:
        text = BeautifulSoup(html, "html.parser").get_text("\n")
        return text.strip(), {"url": url, "title": None}

# -------------------------
# Robust LLM wrapper
# -------------------------
def llm_call_with_retry(prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> str:
    last_exc = None
    for attempt in range(MAX_LLM_RETRIES):
        try:
            logger.debug(f"LLM attempt {attempt+1}/{MAX_LLM_RETRIES} (tokens={max_tokens})")
            model = get_llm()
            if hasattr(model, "invoke"):
                resp = model.invoke(prompt)
                return get_text_from_llm_response(resp)
            if hasattr(model, "generate"):
                resp = model.generate(prompt)
                return get_text_from_llm_response(resp)
            if callable(model):
                resp = model(prompt)
                return get_text_from_llm_response(resp)
            return str(model)
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            logger.warning(f"LLM error: {e}")
            if ("429" in msg) or ("quota" in msg) or ("rate limit" in msg):
                wait = INITIAL_BACKOFF * (2 ** attempt)
                logger.info(f"Rate limit/quota detected. Backing off for {wait}s (attempt {attempt+1}).")
                time.sleep(wait)
                continue
            if attempt < MAX_LLM_RETRIES - 1:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                logger.info(f"Transient LLM error: backing off {wait}s (attempt {attempt+1}).")
                time.sleep(wait)
                continue
            tb = traceback.format_exc()
            return f"[LLM_ERROR] {e}\n{tb}"
    return f"[LLM_ERROR] {last_exc}"

# -------------------------
# Prompts & extract/verify
# -------------------------
CLAIM_EXTRACTION_PROMPT_TEMPLATE = """You are an extractor. Read the article text and return STRICT JSON with this structure:
{{"claims":[{{"id":1,"claim":"short factual claim","span":"text snippet"}}, ...]}}

Only include short, verifiable factual claims (not opinions). If you find no factual claims, return {{"claims":[]}}.

Article:
<<ARTICLE>>
"""

VERIFY_CLAIM_PROMPT_TEMPLATE = """You are an evidence evaluator. Given a single claim and a short source excerpt, return STRICT JSON:

{{"support":"supports|contradicts|neutral|uncertain", "confidence":0.0, "evidence":"short excerpt", "reason":"one-sentence reason"}}

Claim:
<<CLAIM>>

Excerpt:
<<EXCERPT>>

URL: <<URL>>
"""

def extract_claims_from_text(article_text: str) -> List[Dict[str, Any]]:
    if not article_text or len(article_text.strip()) < 80:
        return []
    prompt = CLAIM_EXTRACTION_PROMPT_TEMPLATE.replace("<<ARTICLE>>", article_text[:4000])
    logger.info("Calling LLM to extract claims from article...")
    out = llm_call_with_retry(prompt, max_tokens=700)
    # save raw for debugging
    try:
        os.makedirs("llm_debug", exist_ok=True)
        idx = hashlib.sha1(article_text.encode()).hexdigest()[:8]
        with open(f"llm_debug/extract_{idx}.txt", "w", encoding="utf8") as f:
            f.write("PROMPT:\n" + prompt + "\n\nOUTPUT:\n" + out)
    except Exception:
        pass
    try:
        j = json.loads(out)
        claims = j.get("claims", [])
        logger.info(f"LLM extracted {len(claims)} claims (parsed JSON).")
        return claims
    except Exception:
        import re
        m = re.search(r"\{.*\}", out, flags=re.S)
        if m:
            try:
                j = json.loads(m.group(0))
                claims = j.get("claims", [])
                logger.info(f"LLM extracted {len(claims)} claims (salvaged JSON).")
                return claims
            except Exception:
                pass
        logger.info("LLM did not produce JSON; performing heuristic extraction (short, numeric/date lines).")
        heur = []
        for line in article_text.split('\n'):
            s = line.strip()
            if not s:
                continue
            if len(s) < 300 and (re.search(r"\b(19|20)\d{2}\b", s) or (len(s.split()) < 14 and '.' in s[:80])):
                heur.append({"claim": s[:300]})
                if len(heur) >= 6:
                    break
        for i,c in enumerate(heur, start=1):
            c["id"] = i
        logger.info(f"Heuristic extracted {len(heur)} candidate claims.")
        return heur

def evaluate_claim_vs_excerpt(claim: str, excerpt: str, url: str) -> Dict[str, Any]:
    """
    Call the LLM to evaluate a claim vs an excerpt.
    Always returns a normalized dict:
      {"support": str, "confidence": float, "evidence": str, "reason": str, "url": url, "note": human_text}
    The 'note' will be sanitized for human display (no raw JSON).
    """
    prompt = VERIFY_CLAIM_PROMPT_TEMPLATE.replace("<<CLAIM>>", claim).replace("<<EXCERPT>>", excerpt[:1200]).replace("<<URL>>", url)
    out = llm_call_with_retry(prompt, max_tokens=400)

    # default fallback
    normalized = {"support": "uncertain", "confidence": 0.0, "evidence": (excerpt or "")[:300], "reason": "", "url": url}
    if not out:
        normalized["note"] = "No response from verifier."
        return normalized

    # try parse JSON
    try:
        j = json.loads(out)
        # Map fields safely
        normalized["support"] = j.get("support", normalized["support"])
        try:
            normalized["confidence"] = float(j.get("confidence", normalized["confidence"]) or normalized["confidence"])
        except Exception:
            normalized["confidence"] = normalized["confidence"]
        normalized["evidence"] = j.get("evidence", normalized["evidence"]) or normalized["evidence"]
        normalized["reason"] = j.get("reason", normalized["reason"]) or normalized["reason"]
        normalized["url"] = url
        # Create human note: short sentence summarizing verifier output
        note_parts = []
        note_parts.append(f"verifier says: {normalized['support']}")
        note_parts.append(f"confidence: {normalized['confidence']:.2f}")
        if normalized.get("reason"):
            note_parts.append(f"reason: {str(normalized['reason'])[:200]}")
        normalized["note"] = "; ".join(note_parts)
        return normalized
    except Exception:
        # not JSON: sanitize free-text output and put in note
        sanitized = _sanitize_note(out)
        normalized["note"] = sanitized
        # if out contains obvious support strings, try to pick them
        low = out.lower()
        if "supports" in low and "contradict" not in low:
            normalized["support"] = "supports"
        elif "contradict" in low or "contradicts" in low:
            normalized["support"] = "contradicts"
        elif "neutral" in low:
            normalized["support"] = "neutral"
        # try to extract a numeric confidence
        m = re.search(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%?", out)
        if m:
            try:
                val = float(m.group(1))
                if val > 1: val = val/100.0
                normalized["confidence"] = max(0.0, min(1.0, val))
            except:
                pass
        normalized["evidence"] = (excerpt or "")[:300]
        normalized["url"] = url
        return normalized
    

def aggregate_evaluations(claim_id: int, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates normalized verifier outputs. Expects each ev to have:
      - support, confidence, evidence, reason, url, note (human).
    Returns:
      {"claim_id": id, "aggregate_support":label, "score":0.0-1.0, "best_evidence":{url,excerpt,confidence}, "notes": [human notes]}
    """
    mapping = {"supports": 1.0, "neutral": 0.5, "contradicts": -1.0, "uncertain": 0.0}
    total = 0.0
    count = 0
    best = None
    best_score = -999
    human_notes = []
    for ev in evaluations:
        s = ev.get("support", "uncertain") or "uncertain"
        try:
            conf = float(ev.get("confidence", 0.0) or 0.0)
        except Exception:
            conf = 0.0
        score = mapping.get(s, 0.0) * conf
        total += score
        count += 1
        if score > best_score:
            best_score = score
            best = {"url": ev.get("url", ""), "excerpt": ev.get("evidence", "") or "", "confidence": conf}
        # prefer sanitized human note if present
        note = ev.get("note") or ev.get("reason") or ""
        if note:
            human_notes.append(_sanitize_note(note))
        else:
            # fallback short summary
            human_notes.append(f"{s} (confidence {conf:.2f})")
    if count == 0:
        return {"claim_id": claim_id, "aggregate_support": "insufficient", "score": 0.0, "best_evidence": None, "notes": human_notes}
    raw = total / count
    agg_score = (raw + 1) / 2
    agg_score = max(0.0, min(1.0, agg_score))
    if agg_score > 0.66:
        label = "supports"
    elif agg_score < 0.33:
        label = "contradicts"
    else:
        label = "mixed"
    # deduplicate notes and trim them
    notes_clean = []
    seen = set()
    for n in human_notes:
        t = n.strip()
        if not t: continue
        if t in seen: continue
        seen.add(t)
        notes_clean.append(t if len(t) <= 400 else t[:400] + " ...")
        if len(notes_clean) >= 6:
            break
    return {"claim_id": claim_id, "aggregate_support": label, "score": round(agg_score, 3), "best_evidence": best, "notes": notes_clean}

# -------------------------
# PDF sanitization helpers
# -------------------------
def _md_to_reportlab_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__(.+?)__", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<font name='Courier'>\1</font>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)
    s = s.replace("`", "").replace("**", "")
    return s

def _is_list_like_summary(s: str) -> bool:
    if not s: return False
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines: return False
    count_marked = sum(1 for ln in lines if re.match(r"^(-|\*|\d+\.)\s+", ln))
    return count_marked >= max(1, len(lines)//2)

def _extract_bullet_lines(s: str) -> List[str]:
    lines = []
    for ln in s.splitlines():
        ln = ln.strip()
        if not ln: continue
        m = re.match(r"^(-|\*|\d+\.)\s*(.+)", ln)
        if m:
            lines.append(m.group(2).strip())
        else:
            if len(ln) < 200 and "{" not in ln and ":" not in ln and not ln.lower().startswith("claim"):
                lines.append(ln)
    return lines

def _sanitize_note(n: str) -> str:
    """
    Turn messy note (JSON, fenced blocks, raw PDF fragments) into a short human string.
    - Extract JSON fields support/confidence/evidence/reason if present.
    - Remove code fences and excessive whitespace.
    - Truncate long text.
    """
    if not n:
        return ""
    try:
        s = n.strip()
        # remove fenced code blocks ```...```
        s = re.sub(r"```[a-zA-Z]*\n([\s\S]*?)```", r"\1", s)
        # If there's a JSON substring, try to parse it and extract useful keys
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            jtxt = m.group(0)
            try:
                j = json.loads(jtxt)
                parts = []
                if j.get("support") is not None:
                    parts.append(f"support: {j.get('support')}")
                if j.get("confidence") is not None:
                    parts.append(f"confidence: {float(j.get('confidence')):.2f}")
                if j.get("reason"):
                    parts.append(f"reason: {str(j.get('reason'))[:200]}")
                if j.get("evidence"):
                    ev = str(j.get("evidence")).replace("\n"," ").strip()
                    parts.append(f"evidence: {ev[:200]}{'...' if len(ev)>200 else ''}")
                if parts:
                    return "; ".join(parts)
            except Exception:
                # not valid JSON -> fall through
                pass
        # Avoid binary/pdf garbage
        if re.search(r"%PDF-|<</Filter|stream", s, re.I):
            return "Excerpt not available (binary/pdf content)."
        # collapse whitespace & truncate
        s = re.sub(r"\s+", " ", s)
        if len(s) > 500:
            s = s[:500] + " ..."
        # remove leftover JSON-like brackets if still present
        s = re.sub(r"\{.*\}", "", s)
        s = s.strip()
        return s
    except Exception:
        return (str(n)[:300] + " ...")
# -------------------------
# PDF generator (sanitized)
# -------------------------
def generate_pdf_report(query: str, claims: List[Dict[str, Any]], verified: List[Dict[str, Any]],
                        articles: List[Dict[str, Any]], warnings: List[str], out_path: str = None) -> str:
    """
    Replacement generate_pdf_report that:
      - sanitizes notes (no raw JSON/code fences in main body)
      - displays Findings (Finding 1, Finding 2...) instead of raw Claim # dumps
      - saves full provenance JSON to reports/<query>_provenance.json and shows only its path in appendix
    """
    os.makedirs("reports", exist_ok=True)
    if out_path is None:
        out_path = os.path.join("/c/Users/91969/reports", safe_filename(query))

    # Save full provenance externally (machine-readable)
    provenance_filename = safe_filename(query).replace(".pdf", "_provenance.json")
    provenance_path = os.path.join("/c/Users/91969/reports", provenance_filename)
    try:
        with open(provenance_path, "w", encoding="utf8") as pf:
            json.dump({"claims": claims, "verified": verified, "sources": articles}, pf, indent=2, ensure_ascii=False)
    except Exception as e:
        warnings = warnings or []
        warnings.append(f"Could not write provenance file: {e}")

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]
    normal = styles["BodyText"]
    italic = ParagraphStyle("Italic", parent=styles["BodyText"], fontName="Helvetica-Oblique")
    mono = ParagraphStyle("Mono", parent=styles["Code"], fontName="Courier", fontSize=8)

    flow = []

    # Title and metadata
    flow.append(Paragraph(f"Research Report: {query}", h1))
    flow.append(Spacer(1, 6))
    flow.append(Paragraph(f"Generated: {datetime.datetime.utcnow().isoformat()} UTC", normal))
    flow.append(Spacer(1, 12))

    # Warnings
    if warnings:
        flow.append(Paragraph("Warnings", h2))
        for w in warnings:
            flow.append(Paragraph(f"- {w}", normal))
        flow.append(Spacer(1, 12))

    # Executive summary (sanitized) - use existing llm_call_with_retry and md helper if available
    flow.append(Paragraph("Executive Summary", h2))
    try:
        summary_prompt = f"Summarize research findings for query: {query} with {len(claims)} claims."
        raw_summary = llm_call_with_retry(summary_prompt, max_tokens=300)
    except Exception as e:
        raw_summary = f"[SUMMARY_ERROR] {e}"

    # remove JSON blocks and Claim lines, keep short human lines
    raw_summary = re.sub(r"\{[\s\S]*?\}", "", raw_summary)
    summary_lines = [ln for ln in raw_summary.splitlines() if ln.strip() and not re.match(r"^\s*Claim\s*#?\d+", ln, re.I) and "{" not in ln]
    summary_clean = "\n".join(summary_lines).strip()

    if _is_list_like_summary(summary_clean):
        bullets = _extract_bullet_lines(summary_clean)
        items = []
        for b in bullets:
            items.append(ListItem(Paragraph(_md_to_reportlab_html(b), normal)))
        if items:
            flow.append(ListFlowable(items, bulletType="bullet", start="circle"))
        else:
            for para in summary_clean.split("\n\n"):
                if para.strip():
                    flow.append(Paragraph(_md_to_reportlab_html(para.strip()), normal))
    else:
        for para in summary_clean.split("\n\n"):
            p = para.strip()
            if not p or p.lower().startswith("findings") or p.lower().startswith("claims"):
                continue
            flow.append(Paragraph(_md_to_reportlab_html(p), normal))
            flow.append(Spacer(1, 6))

    flow.append(Spacer(1, 12))

    # Findings (human-friendly; do NOT print raw JSON)
    flow.append(Paragraph("Findings", h2))
    if not claims:
        flow.append(Paragraph("No verifiable claims were extracted.", normal))
    else:
        for idx, (cl, v) in enumerate(zip(claims, verified), start=1):
            claim_text = (cl.get("claim") if isinstance(cl, dict) else str(cl)).strip()
            flow.append(Paragraph(f"Finding {idx}: {claim_text}", h3))

            agg = v.get("aggregate_support", "uncertain")
            score = v.get("score", 0.0)
            flow.append(Paragraph(f"Overall assessment: {agg} (score={score})", normal))
            flow.append(Spacer(1, 4))

            be = v.get("best_evidence") or {}
            if isinstance(be, dict) and be.get("url"):
                flow.append(Paragraph("Representative evidence:", normal))
                flow.append(Paragraph(be.get("url"), italic))
                excerpt = be.get("excerpt") or ""
                excerpt = excerpt.strip()
                if excerpt:
                    excerpt = excerpt.replace("\n", " ").strip()
                    excerpt = excerpt[:900] + ("..." if len(excerpt) > 900 else "")
                    flow.append(Paragraph(f"Excerpt: {excerpt}", normal))
                    flow.append(Spacer(1, 4))

            # notes: sanitized bullets
            notes = v.get("notes") or []
            if notes:
                note_items = []
                for n in notes[:6]:
                    note_txt = _sanitize_note(n)
                    if not note_txt:
                        continue
                    note_items.append(ListItem(Paragraph(note_txt, normal)))
                if note_items:
                    flow.append(Paragraph("Notes:", normal))
                    flow.append(ListFlowable(note_items, bulletType="bullet"))
            flow.append(Spacer(1, 12))

    # Appendix: Sources table
    flow.append(PageBreak())
    flow.append(Paragraph("Appendix — Sources", h2))
    table_data = [["Title", "URL"]]
    for a in articles:
        table_data.append([a.get("title") or "-", a.get("url")])
    t = Table(table_data, colWidths=[200, 300], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    flow.append(t)
    flow.append(Spacer(1, 12))

    # Appendix: provenance pointer (no raw JSON dump)
    flow.append(Paragraph("Appendix — Provenance & Raw Data", h2))
    flow.append(Paragraph("Full machine-readable provenance (claims, per-source verification details and snapshots) saved to:", normal))
    flow.append(Paragraph(provenance_path, italic))
    flow.append(Spacer(1, 12))
    flow.append(Paragraph("Snapshots (raw HTML) are stored under the `snapshots/` directory.", normal))

    try:
        doc.build(flow)
    except Exception as e:
        # fallback minimal PDF so user gets something
        print("[PDF_ERROR] build failed:", e)
        doc = SimpleDocTemplate(out_path, pagesize=A4)
        doc.build([Paragraph(f"Research report for: {query}", h1), Spacer(1,6), Paragraph("Failed to build full report.", normal)])

    return out_path
# -------------------------
# Main pipeline
# -------------------------
def run_research_pipeline(query: str, top_k: int = DEFAULT_TOP_K, claim_limit: int = DEFAULT_CLAIM_LIMIT, verify_per_claim_k: int = DEFAULT_VERIFY_PER_CLAIM, workers: int = DEFAULT_WORKERS, verbose: bool = False) -> str:
    if verbose:
        logger.setLevel(logging.DEBUG)
        stream_handler.setLevel(logging.DEBUG)
    warnings = []
    logger.info(f"Starting research pipeline for: {query}")
    if not has_internet():
        warnings.append("No outbound internet detected; search/remote LLM calls may fail.")
        logger.warning("No internet detected.")

    # 1) search
    logger.info("Searching web (SerpAPI)...")
    try:
        hits = search_serpapi(query, num_results=top_k)
        logger.info(f"Search returned {len(hits)} hits.")
    except Exception as e:
        logger.error("Search failed: %s", e)
        raise

    # 2) fetch & extract
    articles = []
    for i, h in enumerate(hits, start=1):
        url = h.get("url")
        logger.info(f"[{i}/{len(hits)}] Fetching: {url}")
        text, meta = fetch_page_text(url)
        if not text:
            logger.warning(f"Fetched but empty text for {url} (error: {meta.get('error')})")
        articles.append({"url": url, "title": h.get("title") or meta.get("title"), "text": text})
        time.sleep(0.2)

    # 3) extract claims
    all_claims = []
    cid = 1
    for i, art in enumerate(articles, start=1):
        if not art.get("text"):
            logger.debug(f"Skipping article #{i} (no text).")
            continue
        logger.info(f"[{i}/{len(articles)}] Extracting claims from article: {art.get('title') or art.get('url')}")
        claims = extract_claims_from_text(art["text"])
        for cl in claims:
            cl["id"] = cid
            cid += 1
            all_claims.append(cl)
        time.sleep(0.12)

    logger.info(f"Total claims extracted (before limiting): {len(all_claims)}")
    if not all_claims:
        pdf = generate_pdf_report(query, [], [], articles, warnings)
        logger.info(f"No claims found. Minimal report generated: {pdf}")
        return pdf

    limited_claims = all_claims[:claim_limit]
    logger.info(f"Verifying top {len(limited_claims)} claims (claim_limit={claim_limit})")

    # 4) parallel verification
    grouped = {}
    futures = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for cl in limited_claims:
            claim_text = cl.get("claim", "")
            logger.debug(f"Searching support sources for claim #{cl.get('id')}")
            try:
                hits_for_claim = search_serpapi(claim_text, num_results=verify_per_claim_k)
            except Exception as e:
                hits_for_claim = []
                warnings.append(f"Search for claim {cl.get('id')} failed: {e}")
                logger.warning("Search for claim failed: %s", e)
            for hf in hits_for_claim:
                text_s, _ = fetch_page_text(hf.get("url"), save_snapshot=False)
                excerpt = (text_s or "")[:1200]
                fut = ex.submit(evaluate_claim_vs_excerpt, claim_text, excerpt, hf.get("url"))
                futures[fut] = (cl["id"], hf.get("url"))
                time.sleep(0.08)

        logger.info(f"Launched {len(futures)} verification tasks using {workers} workers.")
        for fut in tqdm(as_completed(list(futures.keys())), total=len(futures), desc="Verifying"):
            cid_url = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"support":"uncertain","confidence":0.0,"evidence":"", "reason": f"[task_error] {e}"}
            cid, url = cid_url
            res["url"] = url
            grouped.setdefault(cid, []).append(res)

    # aggregate results
    verified_results = []
    for cl in limited_claims:
        evals = grouped.get(cl["id"], [])
        agg = aggregate_evaluations(cl["id"], evals)
        verified_results.append(agg)

    # 5) generate PDF
    logger.info("Generating PDF report...")
    pdf_path = generate_pdf_report(query, limited_claims, verified_results, articles, warnings)
    logger.info(f"Report generated: {pdf_path}")
    return pdf_path

# -------------------------
# LangGraph wrapper (optional)
# -------------------------
def research_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    query = state.get("query", "").strip()
    if not query:
        raise ValueError("state['query'] is required")
    top_k = int(state.get("top_k", DEFAULT_TOP_K))
    claim_limit = int(state.get("claim_limit", DEFAULT_CLAIM_LIMIT))
    verify_per_claim_k = int(state.get("verify_per_claim_k", DEFAULT_VERIFY_PER_CLAIM))
    workers = int(state.get("workers", DEFAULT_WORKERS))
    pdf = run_research_pipeline(query, top_k=top_k, claim_limit=claim_limit, verify_per_claim_k=verify_per_claim_k, workers=workers)
    return {"pdf": pdf, "query": query}

def build_research_graph():
    if StateGraph is None:
        raise RuntimeError("LangGraph not available in this environment.")
    GraphState = dict
    graph = StateGraph(GraphState)
    graph.add_node("research_agent", research_agent_node)
    graph.set_entry_point("research_agent")
    graph.add_edge("research_agent", END)
    app = graph.compile()
    return app

# -------------------------
# CLI
# -------------------------
def main():
    parser = argparse.ArgumentParser(description="ResearchAgent (improved)")
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--claim-limit", type=int, default=DEFAULT_CLAIM_LIMIT)
    parser.add_argument("--verify-per-claim", type=int, default=DEFAULT_VERIFY_PER_CLAIM)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs")
    args = parser.parse_args()
    pdf = run_research_pipeline(args.query, top_k=args.top_k, claim_limit=args.claim_limit, verify_per_claim_k=args.verify_per_claim, workers=args.workers, verbose=args.verbose)
    print("DONE. PDF:", pdf)

if __name__ == "__main__":
    main()
