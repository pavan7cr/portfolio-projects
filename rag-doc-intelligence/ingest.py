"""Ingest .txt documents from docs/ + extract text from simple PDFs.
PDF extraction here is stdlib-only (zlib streams + Tj text operators)
and works for simple text PDFs; for complex PDFs, install PyPDF and
replace extract_pdf_text() - that upgrade is documented in README.
Usage: python3 ingest.py  -> writes docs_index.json (source, text)
"""
import json, os, re, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
def extract_pdf_text(path):
    data = open(path, "rb").read()
    texts = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try: raw = zlib.decompress(m.group(1))
        except Exception: continue
        for t in re.findall(rb"\((.*?)\)\s*Tj", raw):
            texts.append(t.decode("utf-8", "ignore"))
    return " ".join(texts)
def main():
    docs = {}
    d = os.path.join(HERE, "docs"); os.makedirs(d, exist_ok=True)
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if f.endswith(".txt"): docs[f] = open(p, encoding="utf-8", errors="ignore").read()
        elif f.endswith(".pdf"): docs[f] = extract_pdf_text(p)
    json.dump(docs, open(os.path.join(HERE, "docs_index.json"), "w"), indent=2)
    print(f"Ingested {len(docs)} documents: {list(docs)}")
if __name__ == "__main__":
    main()
