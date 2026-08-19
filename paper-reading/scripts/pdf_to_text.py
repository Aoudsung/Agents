#!/usr/bin/env python3
"""Extract text or markdown from a PDF and report extraction quality.

In auto mode, the first available engine is kept unless its output is clearly
empty or corrupted. Clearly poor output triggers the next available engine.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


AUTO_ORDER = ["pdftotext", "pymupdf", "pdfplumber", "pypdf"]


def log(msg):
    print(f"[pdf_to_text] {msg}", file=sys.stderr)


def extract_pdftotext(pdf_path, out_path):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext not on PATH")
    subprocess.run(
        ["pdftotext", "-layout", pdf_path, out_path],
        check=True,
        capture_output=True,
    )
    return None


def extract_pymupdf4llm(pdf_path, out_path):
    import pymupdf4llm

    return pymupdf4llm.to_markdown(pdf_path)


def extract_pymupdf(pdf_path, out_path):
    import fitz

    doc = fitz.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


def extract_pdfplumber(pdf_path, out_path):
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return "\n\n".join((page.extract_text() or "") for page in pdf.pages)


def extract_pypdf(pdf_path, out_path):
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


ENGINES = {
    "pdftotext": extract_pdftotext,
    "pymupdf4llm": extract_pymupdf4llm,
    "pymupdf": extract_pymupdf,
    "pdfplumber": extract_pdfplumber,
    "pypdf": extract_pypdf,
}


def count_pages(pdf_path):
    try:
        with open(pdf_path, "rb") as handle:
            data = handle.read()
        return max(data.count(b"/Type /Page") - data.count(b"/Type /Pages"), 1)
    except Exception:
        return None


def assess_text_quality(text, pages=None):
    stripped = text.strip()
    chars = len(stripped)
    alnum = sum(char.isalnum() for char in stripped)
    bad_chars = stripped.count("\ufffd") + stripped.count("\x00")
    reasons = []
    expected_floor = max(200, (pages or 1) * 80)
    if chars < expected_floor:
        reasons.append("very little extracted text")
    if chars >= 200 and alnum / max(chars, 1) < 0.12:
        reasons.append("too few readable word characters")
    if bad_chars / max(chars, 1) > 0.03:
        reasons.append("many replacement or null characters")

    sample_hits = 0
    if chars:
        sample_size = min(500, max(100, chars // 6))
        starts = [0, max(0, chars // 2 - sample_size // 2), max(0, chars - sample_size)]
        for start in starts:
            sample = stripped[start:start + sample_size]
            if sum(char.isalnum() for char in sample) >= 30:
                sample_hits += 1
    if chars >= 600 and sample_hits < 2:
        reasons.append("readable text is not present across the document sample")

    score = alnum - bad_chars * 10 + sample_hits * 100
    return {
        "clearly_poor": bool(reasons),
        "reasons": reasons,
        "chars": chars,
        "score": score,
    }


def _read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def extract_best(pdf_path, out_path, engine_req="auto"):
    pages = count_pages(pdf_path)
    candidates = AUTO_ORDER if engine_req == "auto" else [engine_req]
    attempts = []
    successful = []
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)

    for name in candidates:
        temp_handle = tempfile.NamedTemporaryFile(
            prefix=".pdf-to-text-", suffix=".txt", dir=out_dir, delete=False
        )
        temp_path = temp_handle.name
        temp_handle.close()
        try:
            text = ENGINES[name](pdf_path, temp_path)
            if text is not None:
                with open(temp_path, "w", encoding="utf-8") as handle:
                    handle.write(text)
            extracted = _read_text(temp_path)
            quality = assess_text_quality(extracted, pages)
            attempts.append({
                "engine": name,
                "chars": quality["chars"],
                "clearly_poor": quality["clearly_poor"],
                "reasons": quality["reasons"],
            })
            successful.append((quality["score"], name, temp_path, extracted, quality))
            if engine_req != "auto" or not quality["clearly_poor"]:
                os.replace(temp_path, out_path)
                for _, _, other_path, _, _ in successful:
                    if other_path != temp_path and os.path.exists(other_path):
                        os.unlink(other_path)
                return name, extracted, quality, attempts, pages
            log(f"{name} output is clearly poor; trying the next available engine")
        except Exception as exc:
            attempts.append({"engine": name, "error": str(exc)})
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    if not successful:
        errors = "; ".join(
            f"{item['engine']}: {item.get('error', 'no usable output')}" for item in attempts
        )
        raise RuntimeError("no PDF text extractor available (" + errors + ")")

    _, name, best_path, extracted, quality = max(successful, key=lambda item: item[0])
    os.replace(best_path, out_path)
    for _, _, other_path, _, _ in successful:
        if other_path != best_path and os.path.exists(other_path):
            os.unlink(other_path)
    return name, extracted, quality, attempts, pages


def main(argv):
    args = argv[1:]
    if not args:
        print(json.dumps({
            "ok": False,
            "error": "usage: pdf_to_text.py <input.pdf> [-o output.txt] [--engine NAME]",
        }))
        return 1

    pdf_path = args[0]
    out_path = None
    engine_req = "auto"
    if "-o" in args:
        index = args.index("-o")
        if index + 1 < len(args):
            out_path = args[index + 1]
    if "--engine" in args:
        index = args.index("--engine")
        if index + 1 < len(args):
            engine_req = args[index + 1]

    if engine_req != "auto" and engine_req not in ENGINES:
        print(json.dumps({
            "ok": False,
            "error": f"unknown engine: {engine_req}",
            "hint": f"choose from auto, {', '.join(ENGINES)}",
        }))
        return 1
    if not os.path.isfile(pdf_path):
        print(json.dumps({"ok": False, "error": f"file not found: {pdf_path}"}))
        return 1
    if not out_path:
        out_path = os.path.splitext(pdf_path)[0] + ".txt"

    try:
        engine, text, quality, attempts, pages = extract_best(
            pdf_path, out_path, engine_req=engine_req
        )
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "error": str(exc),
            "hint": "install poppler or one of pymupdf, pdfplumber, pypdf",
        }))
        return 1

    warning = None
    if quality["clearly_poor"]:
        warning = "all available extraction results were clearly poor: " + "; ".join(
            quality["reasons"]
        )
    elif pages and len(text) / pages < 500:
        warning = "low text density; inspect the output before relying on formulas or figures"

    print(json.dumps({
        "ok": True,
        "text_path": os.path.abspath(out_path),
        "pages": pages,
        "chars": len(text),
        "engine": engine,
        "attempts": attempts,
        "warning": warning,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
