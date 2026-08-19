#!/usr/bin/env python3
"""fetch_paper.py — resolve a paper reference to a local PDF.

Supported inputs:
  - local PDF file path
  - arXiv ID ("1706.03762", "arXiv:1706.03762") or arXiv abs/pdf URL
  - direct PDF URL
  - DOI ("10.1038/...") or https://doi.org/... URL
  - IEEE Xplore / ScienceDirect article page URL

For IEEE Xplore / ScienceDirect URLs it first tries the publisher's PDF
endpoint directly. That succeeds when you have institutional access —
either by IP authorization (campus network / school VPN) or by reusing
browser cookies after an SSO login:

  fetch_paper.py "https://ieeexplore.ieee.org/document/1234567" --cookies cookies.txt

NEVER put your institutional account password in this script, a config
file, or the command line. Log in via your browser and export cookies
instead (see README). Treat cookies.txt as a secret: delete after use.

Without institutional access it falls back to legal open-access copies:
  1. OpenAlex API (no key needed) -> primary/best OA location
  2. Unpaywall API (when UNPAYWALL_EMAIL is set)
  3. Semantic Scholar (when S2_API_KEY is set)

For Elsevier content, setting ELSEVIER_API_KEY (free personal key from
https://dev.elsevier.com for researchers at subscribing institutions)
enables the official Full-Text API; entitled content also requires
institutional IP (campus network / VPN) or an institutional token.

Pure standard library. Prints a JSON object on stdout:
  {"ok": true, "pdf_path": ..., "paper_dir": ..., "title": ..., "doi": ...,
   "arxiv_id": ..., "openalex_id": ..., "journal_ref": ...,
   "preferred_version": ..., "analyzed_version": ..., "year": ...,
   "venue": ..., "authors": [...], "source": ...}
or
  {"ok": false, "error": ..., "hint": ...}

Output layout: each paper gets its own directory <outdir>/<name>/ containing
<name>.pdf and meta.json (the same JSON as printed on stdout).

Human-readable progress goes to stderr.
"""

import argparse
import http.cookiejar
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 45

ARXIV_NEW = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
ARXIV_OLD = re.compile(r"^([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
IEEE_RE = re.compile(
    r"ieeexplore\.ieee\.org/(?:document/|stamp(?:PDF)?/getPDF\.jsp\?.*?arnumber=)(\d+)"
)
SD_RE = re.compile(r"sciencedirect\.com/science/article/pii/([A-Za-z0-9-]+)")

COOKIE_JAR = None     # http.cookiejar.MozillaCookieJar or None
COOKIE_HEADER = None  # raw "k=v; k2=v2" string or None

_SSL_CTX = None


def log(msg):
    print(f"[fetch_paper] {msg}", file=sys.stderr)


def _ssl_context():
    """Default context; fall back to certifi, then to unverified (with a warning).

    python.org macOS builds ship without root certificates until
    "Install Certificates.command" is run, so the default context often fails.
    """
    global _SSL_CTX
    if _SSL_CTX is not None:
        return _SSL_CTX
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    _SSL_CTX = ctx
    return ctx


def _open(req, ctx):
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    if COOKIE_JAR is not None:
        handlers.append(urllib.request.HTTPCookieProcessor(COOKIE_JAR))
    return urllib.request.build_opener(*handlers).open(req, timeout=TIMEOUT)


def http_get(url, accept=None, referer=None, extra_headers=None):
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    if referer:
        headers["Referer"] = referer
    if extra_headers:
        headers.update(extra_headers)
    if COOKIE_HEADER:
        headers["Cookie"] = COOKIE_HEADER
    req = urllib.request.Request(url, headers=headers)
    try:
        with _open(req, _ssl_context()) as resp:
            return resp.read(), resp.headers
    except (ssl.SSLCertVerificationError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", e)
        if not isinstance(reason, ssl.SSLCertVerificationError) and (
            "CERTIFICATE_VERIFY_FAILED" not in str(reason)
        ):
            raise
        raise RuntimeError(
            f"TLS certificate verification failed for {url}. Fix the proxy, "
            "DNS, or CA configuration; refusing an insecure retry."
        ) from e


def http_json(url, accept="application/json", extra_headers=None):
    data, _ = http_get(url, accept=accept, extra_headers=extra_headers)
    return json.loads(data.decode("utf-8", "replace"))


def slugify(text, maxlen=60):
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    return (text[:maxlen].strip("-") or "paper")


def public_id_slug(prefix, value, maxlen=48):
    if not value:
        return None
    value = urllib.parse.unquote(str(value)).lower().strip()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if not value:
        return None
    return f"{prefix}-{value}"[:maxlen].strip("-")


def url_identity_slug(url):
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    parts = [part for part in parsed.path.split("/") if part]
    path = "-".join(parts[-3:])
    public_query = []
    for key, values in urllib.parse.parse_qs(parsed.query).items():
        if key.lower() in {"id", "paper", "article", "pii", "arnumber"}:
            public_query.extend([key, values[0]])
    value = "-".join([host, path, *public_query])
    return public_id_slug("url", value)


def paper_name(meta, source_ref=None, fallback="paper"):
    title = meta.get("title")
    base = slugify(title or fallback, maxlen=60)
    suffix = None
    if meta.get("doi"):
        suffix = public_id_slug("doi", meta["doi"])
    elif meta.get("arxiv_id"):
        suffix = public_id_slug("arxiv", meta["arxiv_id"])
    elif meta.get("openalex_id"):
        suffix = public_id_slug("openalex", meta["openalex_id"])
    elif source_ref and re.match(r"https?://", source_ref):
        suffix = url_identity_slug(source_ref)
    if suffix:
        return f"{base}--{suffix}"[:110].strip("-")
    return base


def download_pdf(url, dest, referer=None, extra_headers=None):
    log(f"downloading {url}")
    data, headers = http_get(url, accept="application/pdf,*/*", referer=referer,
                             extra_headers=extra_headers)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(
            f"URL did not return a PDF (got {headers.get('Content-Type', '?')}, "
            f"{len(data)} bytes). It may be an HTML interstitial/login page."
        )
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    log(f"saved {len(data)} bytes -> {dest}")


# ---------- input parsing ----------

def detect_arxiv_id(s):
    s = s.strip()
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#\s]+)", s)
    if m:
        ident = m.group(1)
        ident = re.sub(r"\.pdf$", "", ident)
        return ident
    s = re.sub(r"^arxiv:\s*", "", s, flags=re.IGNORECASE)
    m = ARXIV_NEW.match(s) or ARXIV_OLD.match(s)
    if m:
        return m.group(1) + (m.group(2) or "")
    return None


def detect_doi(s):
    s = s.strip()
    m = re.search(r"doi\.org/([^\s?#]+)", s)
    if m:
        return urllib.parse.unquote(m.group(1))
    if DOI_RE.match(s):
        return s
    return None


def publisher_pdf_endpoint(url):
    """Map an IEEE/ScienceDirect article page URL to its PDF endpoint.

    Returns (pdf_url, referer, fallback_name) or None.
    """
    m = IEEE_RE.search(url)
    if m:
        ar = m.group(1)
        return (
            f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={ar}&ref=",
            f"https://ieeexplore.ieee.org/document/{ar}",
            f"ieee-{ar}",
        )
    m = SD_RE.search(url)
    if m:
        pii = m.group(1)
        return (
            f"https://www.sciencedirect.com/science/article/pii/{pii}"
            f"/pdfft?isDTMRedir=true&download=true",
            url,
            f"sd-{pii}",
        )
    return None


def _cookie_dict(host=None):
    """Flatten cookies to a name->value dict, optionally scoped to a host.

    Scoping matters: the jar accumulates response cookies from every site we
    touch (S2, arXiv, ...), and cross-site name collisions (cf_clearance & co.)
    would silently overwrite the target site's cookies.
    """
    def domain_match(cookie_domain, host):
        d = cookie_domain.lstrip(".")
        return host == d or host.endswith("." + d)

    if COOKIE_JAR is not None:
        return {
            c.name: c.value for c in COOKIE_JAR
            if host is None or domain_match(c.domain, host)
        }
    if COOKIE_HEADER:
        return dict(
            p.split("=", 1) for p in
            (kv.strip() for kv in COOKIE_HEADER.split(";")) if "=" in p
        )
    return {}


def extract_meta_from_html(html):
    """Pull metadata from a publisher article page.

    Tries standard citation_* meta tags first, then IEEE's
    xplGlobal.document.metadata JSON block.
    """
    def m1(name):
        for pat in (
            r'<meta[^>]+name=["\']' + re.escape(name) + r'["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']' + re.escape(name) + r'["\']',
        ):
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return m.group(1)
        return None
    authors = re.findall(
        r'<meta[^>]+name=["\']citation_author["\'][^>]+content=["\']([^"\']+)',
        html, re.IGNORECASE)
    meta = {
        "title": m1("citation_title"),
        "doi": m1("citation_doi"),
        "year": (m1("citation_publication_date") or "")[:4] or None,
        "venue": m1("citation_journal_title") or m1("citation_conference_title"),
        "authors": authors[:8] or None,
    }
    if not meta.get("title"):
        m = re.search(r"xplGlobal\.document\.metadata\s*=\s*(\{.*?\});", html, re.S)
        if m:
            try:
                j = json.loads(m.group(1))
            except Exception:
                j = None
            if j:
                meta = {
                    "title": j.get("title"),
                    "doi": j.get("doi"),
                    "year": str(j.get("publicationYear") or "")[:4] or None,
                    "venue": j.get("publicationTitle"),
                    "authors": [a.get("name") for a in (j.get("authors") or [])][:8] or None,
                }
    return meta


def ieee_download(arnumber, dest):
    """Download an IEEE Xplore PDF via the real browser flow.

    IEEE sits behind AWS WAF + JS challenges that fingerprint TLS, so plain
    urllib gets an interstitial even with valid session cookies. This uses
    curl_cffi's Chrome TLS impersonation when available.

    Flow: document page (metadata) -> stamp.jsp wrapper -> iframe URL -> PDF.
    Returns a metadata dict extracted from the document page (best effort).
    """
    try:
        from curl_cffi import requests as creq
    except ImportError:
        raise RuntimeError(
            "IEEE downloads require curl_cffi (TLS impersonation): "
            "pip install curl_cffi  (or use the skill's .venv, see README)"
        )
    cookies = _cookie_dict("ieeexplore.ieee.org")
    doc_url = f"https://ieeexplore.ieee.org/document/{arnumber}"
    stamp_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}"
    s = creq.Session(impersonate="chrome")

    meta = {}
    try:
        r0 = s.get(doc_url, cookies=cookies, timeout=TIMEOUT * 2)
        meta = {k: v for k, v in extract_meta_from_html(r0.text).items() if v}
        if not meta:
            log(f"IEEE document page yielded no metadata ({len(r0.content)} bytes)")
    except Exception as e:
        log(f"IEEE document page metadata failed: {e}")

    log(f"fetching IEEE stamp page for arnumber {arnumber}")
    r1 = s.get(stamp_url, cookies=cookies,
               headers={"Referer": doc_url}, timeout=TIMEOUT * 2)
    m = re.search(r'<iframe\s+src="([^"]*stampPDF/getPDF\.jsp[^"]+)"', r1.text)
    if m:
        pdf_url = m.group(1).replace("&amp;", "&")
    else:
        # iframe not found (layout change) — construct the URL ourselves
        import base64
        ref = base64.b64encode(doc_url.encode()).decode()
        pdf_url = (
            f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}"
            f"&ref={urllib.parse.quote(ref)}"
        )
    log(f"downloading {pdf_url}")
    r2 = s.get(pdf_url, cookies=cookies,
               headers={"Referer": stamp_url, "Accept": "application/pdf,*/*"},
               timeout=TIMEOUT * 2)
    if not r2.content.startswith(b"%PDF"):
        raise RuntimeError(
            "IEEE returned HTML instead of a PDF (login page / WAF challenge). "
            "Cookies may be expired or missing — re-export cookies.txt after "
            "completing institutional SSO in the browser."
        )
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(r2.content)
    log(f"saved {len(r2.content)} bytes -> {dest}")
    return meta


def extract_doi_from_page(url):
    """Fetch a publisher landing page and pull the DOI from meta tags."""
    log(f"fetching landing page {url}")
    data, _ = http_get(url, accept="text/html,*/*")
    html = data.decode("utf-8", "replace")
    for pat in (
        r'<meta[^>]+name=["\']citation_doi["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_doi["\']',
        r'"doi"\s*:\s*"([^"]+)"',
    ):
        m = re.search(pat, html, flags=re.IGNORECASE)
        if m and DOI_RE.match(m.group(1)):
            return m.group(1)
    m = DOI_RE.search(html)
    return m.group(0).rstrip(".;,)\"]'" ) if m else None


def local_pdf_metadata(path):
    """Read basic local PDF metadata, with a filename fallback."""
    meta = {}
    if shutil.which("pdfinfo"):
        try:
            completed = subprocess.run(
                ["pdfinfo", path], check=True, capture_output=True, text=True
            )
            fields = {}
            for line in completed.stdout.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    fields[key.strip().lower()] = value.strip()
            if fields.get("title"):
                meta["title"] = fields["title"]
            if fields.get("author"):
                meta["authors"] = [fields["author"]]
            date_value = fields.get("creationdate") or fields.get("moddate") or ""
            year = re.search(r"(?:19|20)\d{2}", date_value)
            if year:
                meta["year"] = year.group(0)
        except Exception as e:
            log(f"local PDF metadata lookup failed: {e}")
    if not meta.get("title"):
        stem = os.path.splitext(os.path.basename(path))[0]
        meta["title"] = re.sub(r"[_-]+", " ", stem).strip() or "Local paper"
    meta["preferred_version"] = "local PDF"
    meta["analyzed_version"] = "local PDF"
    return meta


def set_version_fields(meta, analyzed_version=None):
    if not meta.get("preferred_version"):
        meta["preferred_version"] = (
            meta.get("doi")
            or meta.get("journal_ref")
            or meta.get("arxiv_id")
            or meta.get("openalex_id")
        )
    if analyzed_version and not meta.get("analyzed_version"):
        meta["analyzed_version"] = analyzed_version
    if not meta.get("analyzed_version"):
        meta["analyzed_version"] = meta.get("preferred_version")
    return meta


# ---------- metadata & OA lookup ----------

def arxiv_metadata(arxiv_id):
    try:
        url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
        data, _ = http_get(url)
        xml = data.decode("utf-8", "replace")
        titles = re.findall(r"<title>(.*?)</title>", xml, flags=re.DOTALL)
        authors = re.findall(r"<name>(.*?)</name>", xml)
        published = re.search(r"<published>(\d{4})", xml)
        title = re.sub(r"\s+", " ", titles[1]).strip() if len(titles) > 1 else None
        jref = re.search(r"<arxiv:journal_ref[^>]*>(.*?)</arxiv:journal_ref>", xml, re.DOTALL)
        adoi = re.search(r"<arxiv:doi[^>]*>(.*?)</arxiv:doi>", xml, re.DOTALL)
        return {
            "title": title,
            "authors": authors[:8],
            "year": published.group(1) if published else None,
            "venue": "arXiv",
            "journal_ref": jref.group(1).strip() if jref else None,
            "doi": adoi.group(1).strip() if adoi else None,
        }
    except Exception as e:  # metadata is best-effort
        log(f"arXiv metadata lookup failed: {e}")
        return {}


def s2_lookup(identifier):
    """Look up a paper on Semantic Scholar by prefixed identifier.

    `identifier` is e.g. "DOI:10.1038/..." or "URL:https://ieeexplore.ieee.org/...".
    """
    key = os.environ.get("S2_API_KEY")
    if not key:
        return {}
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/"
        + urllib.parse.quote(identifier, safe="")
        + "?fields=title,year,venue,authors,openAccessPdf,externalIds,url"
    )
    try:
        j = http_json(url, extra_headers={"x-api-key": key})
    except Exception as e:
        log(f"Semantic Scholar lookup failed: {e}")
        return {}
    out = {
        "title": j.get("title"),
        "year": str(j.get("year")) if j.get("year") else None,
        "venue": j.get("venue"),
        "authors": [a.get("name") for a in (j.get("authors") or [])][:8],
        "arxiv_id": (j.get("externalIds") or {}).get("ArXiv"),
        "doi": (j.get("externalIds") or {}).get("DOI"),
        "s2_url": j.get("url"),
    }
    oapdf = j.get("openAccessPdf") or {}
    out["oa_pdf"] = oapdf.get("url")
    return out


def unpaywall_lookup(doi):
    email = os.environ.get("UNPAYWALL_EMAIL")
    if not email:
        return {}
    try:
        j = http_json(
            f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
        )
    except Exception as e:
        log(f"Unpaywall lookup failed: {e}")
        return {}
    loc = j.get("best_oa_location") or {}
    return {"oa_pdf": loc.get("url_for_pdf"), "title": j.get("title"), "year": str(j.get("year") or "") or None}


def openalex_lookup(doi):
    """OpenAlex work lookup by DOI. Free, no API key; mailto joins the polite pool."""
    url = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="")
    email = os.environ.get("UNPAYWALL_EMAIL")
    if email:
        url += "?mailto=" + urllib.parse.quote(email)
    try:
        j = http_json(url)
    except Exception as e:
        log(f"OpenAlex lookup failed: {e}")
        return {}
    prim = j.get("primary_location") or {}
    best = j.get("best_oa_location") or {}
    ids = j.get("ids") or {}
    authorships = j.get("authorships") or []
    source = prim.get("source") or {}
    primary_pdf = prim.get("pdf_url")
    formal_pdf = primary_pdf if source.get("type") != "repository" else None
    return {
        "openalex_id": j.get("id") or ids.get("openalex"),
        "doi": normalize_doi(j.get("doi") or ids.get("doi")),
        "arxiv_id": extract_arxiv_id(ids),
        "title": j.get("title"),
        "year": str(j.get("publication_year") or "") or None,
        "venue": source.get("display_name") or None,
        "authors": [(a.get("author") or {}).get("display_name") for a in authorships][:8],
        "formal_pdf": formal_pdf,
        "oa_pdf": best.get("pdf_url") or primary_pdf,
    }


def normalize_doi(value):
    if not value:
        return None
    value = urllib.parse.unquote(str(value)).strip()
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I) or None


def extract_arxiv_id(ids):
    value = (ids or {}).get("arxiv") or (ids or {}).get("ArXiv")
    if not value:
        return None
    value = str(value).strip()
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#\s]+)", value, re.I)
    if match:
        value = match.group(1)
    else:
        value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    value = re.sub(r"\.pdf$", "", value, flags=re.I)
    return value if ARXIV_NEW.match(value) or ARXIV_OLD.match(value) else None


def resolve_arxiv_source(arxiv_id):
    """Prefer a public formal-version PDF when the arXiv record names a DOI."""
    meta = arxiv_metadata(arxiv_id)
    meta["arxiv_id"] = arxiv_id
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    source = "arxiv"
    analyzed_version = arxiv_id
    doi = normalize_doi(meta.get("doi"))
    if doi:
        meta["doi"] = doi
        formal = openalex_lookup(doi)
        formal_pdf = formal.get("formal_pdf")
        if not formal_pdf:
            formal_pdf = unpaywall_lookup(doi).get("oa_pdf")
        meta = {
            **{k: v for k, v in meta.items() if v},
            **{k: v for k, v in formal.items() if v and k not in {"arxiv_id", "oa_pdf", "formal_pdf"}},
            "arxiv_id": arxiv_id,
            "doi": doi,
            "journal_ref": meta.get("journal_ref"),
        }
        if formal_pdf:
            pdf_url = formal_pdf
            source = "arxiv+formal-oa"
            analyzed_version = doi
    set_version_fields(meta, analyzed_version=analyzed_version)
    return pdf_url, source, meta


def enrich_doi_meta(meta, doi):
    doi = normalize_doi(doi)
    if not doi:
        return meta
    openalex = openalex_lookup(doi)
    return {
        **{k: v for k, v in openalex.items() if v},
        **{k: v for k, v in meta.items() if v},
        "doi": doi,
    }


def instsci_config():
    """Read non-interactive InstSci credentials without exposing them in shell startup files."""
    path = os.environ.get("INSTSCI_CONFIG") or os.path.expanduser("~/.instsci/config.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def elsevier_api_target(kind, ident):
    """Elsevier Full-Text API (https://dev.elsevier.com). Needs ELSEVIER_API_KEY;
    entitled subscription content additionally requires institutional IP or an
    institutional token from Elsevier. Returns (url, headers) or (None, None)."""
    config = instsci_config()
    key = os.environ.get("ELSEVIER_API_KEY") or config.get("elsevier_api_key")
    if not key:
        return None, None
    url = (
        f"https://api.elsevier.com/content/article/{kind}/{urllib.parse.quote(ident)}"
        f"?httpAccept=application/pdf"
    )
    headers = {"X-ELS-APIKey": key}
    token = os.environ.get("ELSEVIER_INST_TOKEN") or config.get("elsevier_inst_token")
    if token:
        headers["X-ELS-Insttoken"] = token
    return url, headers


# ---------- main ----------

def emit(result):
    print(json.dumps(result, ensure_ascii=False, indent=2))


def fail(error, hint=None):
    emit({"ok": False, "error": error, "hint": hint})
    sys.exit(1)


# ---------- output layout ----------

def paper_paths(outdir, name):
    """Per-paper directory layout: <outdir>/<name>/<name>.pdf"""
    d = os.path.join(outdir, name)
    return d, os.path.join(d, name + ".pdf")


def write_meta(paper_dir, result):
    os.makedirs(paper_dir, exist_ok=True)
    with open(os.path.join(paper_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in result.items() if v is not None},
                  f, ensure_ascii=False, indent=2)


def emit_ok(dest, source, meta, paper_dir=None):
    set_version_fields(meta)
    result = {
        "ok": True,
        "pdf_path": os.path.abspath(dest),
        "paper_dir": os.path.abspath(paper_dir or os.path.dirname(dest)),
        "source": source,
        "title": meta.get("title"),
        "authors": meta.get("authors"),
        "year": meta.get("year"),
        "venue": meta.get("venue"),
        "journal_ref": meta.get("journal_ref"),
        "doi": meta.get("doi"),
        "arxiv_id": meta.get("arxiv_id"),
        "openalex_id": meta.get("openalex_id"),
        "preferred_version": meta.get("preferred_version"),
        "analyzed_version": meta.get("analyzed_version"),
        "s2_url": meta.get("s2_url"),
    }
    try:
        write_meta(result["paper_dir"], result)
    except Exception as e:
        log(f"could not write meta.json: {e}")
    emit(result)


PAYWALL_HINT = (
    "no open-access copy was found. Options: (1) connect to your campus "
    "network / school VPN and retry the publisher URL — institutional IP "
    "authorization needs no credentials; (2) for Elsevier content, set a free "
    "personal ELSEVIER_API_KEY from https://dev.elsevier.com (works with "
    "institutional IP/VPN for subscribed content); (3) log in via your "
    "browser's institutional SSO, export cookies (Netscape format "
    "cookies.txt) and retry with --cookies cookies.txt; (4) download "
    "manually and pass the local .pdf path. Setting UNPAYWALL_EMAIL enables "
    "one more legal-OA lookup source. Never put your institutional password "
    "in scripts."
)


def main(argv):
    ap = argparse.ArgumentParser(description="resolve a paper reference to a local PDF")
    ap.add_argument("input", help="pdf path | arXiv ID/URL | PDF URL | DOI | publisher page URL")
    ap.add_argument("outdir", nargs="?", default="papers")
    ap.add_argument("--cookies", help="Netscape-format cookies.txt for institutional access")
    ap.add_argument("--cookie-header", help="raw Cookie header string (alternative to --cookies)")
    args = ap.parse_args(argv[1:])

    global COOKIE_JAR, COOKIE_HEADER
    if args.cookies:
        COOKIE_JAR = http.cookiejar.MozillaCookieJar(args.cookies)
        try:
            COOKIE_JAR.load(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            fail(f"could not load cookies file {args.cookies}: {e}",
                 "export cookies in Netscape format (e.g. a 'Get cookies.txt' browser extension)")
        log(f"loaded cookies from {args.cookies}")
    if args.cookie_header:
        COOKIE_HEADER = args.cookie_header

    inp = args.input
    outdir = args.outdir

    # 1. local file
    if os.path.isfile(inp):
        if not inp.lower().endswith(".pdf"):
            fail(f"local file is not a .pdf: {inp}")
        meta = local_pdf_metadata(inp)
        name = paper_name(meta, fallback=os.path.splitext(os.path.basename(inp))[0])
        pdir, _ = paper_paths(outdir, name)
        emit_ok(os.path.abspath(inp), "local", meta, paper_dir=pdir)
        return

    meta = {}
    pdf_url = None
    source = None

    # 2. arXiv
    arxiv_id = detect_arxiv_id(inp)
    if arxiv_id:
        pdf_url, source, meta = resolve_arxiv_source(arxiv_id)

    # 3. direct PDF URL
    elif re.match(r"https?://", inp) and re.search(r"\.pdf($|[?#])", inp, re.IGNORECASE):
        pdf_url = inp
        source = "direct-url"
        meta["analyzed_version"] = inp

    # 4. DOI / doi.org / publisher landing page
    else:
        doi = detect_doi(inp)
        is_page_url = not doi and re.match(r"https?://", inp)

        if is_page_url:
            # Publishers (IEEE etc.) often bot-block their pages; Semantic
            # Scholar can resolve many article URLs directly.
            meta = s2_lookup("URL:" + inp)
            doi = meta.get("doi") or None

            # Institutional access: try the publisher's own PDF route
            # (works with campus IP / school VPN, or with --cookies).
            m_ieee = IEEE_RE.search(inp)
            if m_ieee:
                arnumber = m_ieee.group(1)
                doc_url = f"https://ieeexplore.ieee.org/document/{arnumber}"
                name = paper_name(meta, source_ref=doc_url, fallback=f"ieee-{arnumber}")
                pdir, dest = paper_paths(outdir, name)
                try:
                    got = ieee_download(arnumber, dest) or {}
                    meta = {**got, **{k: v for k, v in meta.items() if v}}
                    meta["doi"] = meta.get("doi") or doi
                    if not meta.get("title"):
                        # the doc page sometimes gets WAF-challenged under
                        # curl_cffi; plain urllib usually gets the real page
                        try:
                            data, _ = http_get(doc_url, accept="text/html,*/*")
                            got2 = {k: v for k, v in extract_meta_from_html(
                                data.decode("utf-8", "replace")).items() if v}
                            meta = {**got2, **{k: v for k, v in meta.items() if v}}
                            meta["doi"] = meta.get("doi") or doi
                        except Exception as e:
                            log(f"IEEE metadata page scrape failed: {e}")
                    if meta.get("doi"):
                        if not meta.get("authors"):
                            enrich = s2_lookup("DOI:" + meta["doi"])
                            meta = {**{k: v for k, v in enrich.items() if v},
                                    **{k: v for k, v in meta.items() if v}}
                        meta = enrich_doi_meta(meta, meta["doi"])
                    if meta.get("title"):
                        final_name = paper_name(meta, source_ref=doc_url, fallback=f"ieee-{arnumber}")
                        final_dir, final_dest = paper_paths(outdir, final_name)
                        if final_dest != dest:
                            os.makedirs(final_dir, exist_ok=True)
                            os.replace(dest, final_dest)
                            dest = final_dest
                            try:
                                os.rmdir(pdir)  # drop the now-empty fallback dir
                            except OSError:
                                pass
                    emit_ok(dest, "institutional", meta)
                    return
                except Exception as e:
                    log(f"IEEE PDF download failed: {e}")
                    log("falling back to open-access lookup")
            elif publisher_pdf_endpoint(inp):
                ep_url, referer, fb_name = publisher_pdf_endpoint(inp)
                name = paper_name(meta, source_ref=inp, fallback=fb_name)
                _, dest = paper_paths(outdir, name)
                try:
                    download_pdf(ep_url, dest, referer=referer)
                    meta = enrich_doi_meta(meta, doi)
                    emit_ok(dest, "institutional", meta)
                    return
                except Exception as e:
                    log(f"publisher PDF endpoint failed: {e}")
                    log("not on campus network/VPN, or cookies missing/expired — "
                        "falling back to open-access lookup")

            # Elsevier's official Full-Text API (requires ELSEVIER_API_KEY).
            m_sd = SD_RE.search(inp)
            if m_sd:
                els_url, els_headers = elsevier_api_target("pii", m_sd.group(1))
                if els_url:
                    name = paper_name(meta, source_ref=inp, fallback=f"sd-{m_sd.group(1)}")
                    _, dest = paper_paths(outdir, name)
                    try:
                        download_pdf(els_url, dest, extra_headers=els_headers)
                        meta = enrich_doi_meta(meta, doi)
                        emit_ok(dest, "elsevier-api", meta)
                        return
                    except Exception as e:
                        log(f"Elsevier API (by PII) failed: {e}")

        if not doi and is_page_url:
            try:
                doi = extract_doi_from_page(inp)
            except Exception as e:
                log(f"could not fetch landing page: {e}")

        if not doi and not meta.get("title"):
            fail(
                f"unrecognized input: {inp}",
                "give a local .pdf path, an arXiv ID/URL, a direct .pdf URL, "
                "a DOI, or an IEEE/ScienceDirect article page URL. Publisher "
                "pages are often bot-blocked; passing the DOI works better.",
            )

        if doi:
            doi = normalize_doi(doi)
            log(f"DOI: {doi}")
            meta = enrich_doi_meta(meta, doi)
            if not meta.get("title"):
                meta = {
                    **{k: v for k, v in s2_lookup("DOI:" + doi).items() if v},
                    **{k: v for k, v in meta.items() if v},
                    "doi": doi,
                }

            # Elsevier's official Full-Text API (requires ELSEVIER_API_KEY).
            els_url, els_headers = elsevier_api_target("doi", doi)
            if els_url:
                name = paper_name(meta, source_ref=inp, fallback=doi)
                _, dest = paper_paths(outdir, name)
                try:
                    download_pdf(els_url, dest, extra_headers=els_headers)
                    emit_ok(dest, "elsevier-api", meta)
                    return
                except Exception as e:
                    log(f"Elsevier API (by DOI) failed: {e}")

        pdf_url = meta.get("formal_pdf") or meta.get("oa_pdf")
        source = "doi+openalex" if pdf_url else None
        if not pdf_url and doi:
            up = unpaywall_lookup(doi)
            if up.get("oa_pdf"):
                pdf_url = up["oa_pdf"]
                source = "doi+unpaywall"
                meta = {**meta, **{k: v for k, v in up.items() if v and not meta.get(k)}}
        if not pdf_url:
            fail(f"no open-access PDF found for {doi or inp}", PAYWALL_HINT)

    set_version_fields(meta, analyzed_version=meta.get("analyzed_version") or meta.get("doi") or arxiv_id)
    name = paper_name(meta, source_ref=inp, fallback=arxiv_id or meta.get("doi") or "paper")
    _, dest = paper_paths(outdir, name)
    try:
        download_pdf(pdf_url, dest)
    except Exception as e:
        fail(f"download failed: {e}", PAYWALL_HINT)

    emit_ok(dest, source, meta)


if __name__ == "__main__":
    main(sys.argv)
