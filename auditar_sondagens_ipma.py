#!/usr/bin/env python3
"""Diagnóstico não invasivo da página de tefigramas do IPMA.
Não interpreta imagens como perfis numéricos nem inventa observações.
"""
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

PAGE = "https://www.ipma.pt/pt/otempo/obs.sondagens/"
OUT = Path("auditoria_skewt/ipma_fontes.json")

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.resources = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("src", "href", "data-src"):
            if a.get(k):
                self.resources.append({"tag": tag, "url": urljoin(PAGE, a[k])})

def download(url):
    req = Request(url, headers={"User-Agent": "MeteoFox/1.0 (IPMA sounding source audit)", "Accept": "text/html,application/javascript,*/*"})
    with urlopen(req, timeout=25) as resp:
        return resp.read(800_000).decode("utf-8", "replace"), resp.headers.get("Content-Type", "")

def main():
    result = {"checked_utc": datetime.now(timezone.utc).isoformat(), "page": PAGE,
              "page_status": "unavailable", "resources": [], "candidate_references": [],
              "numeric_profile_endpoint_verified": False, "errors": []}
    try:
        html, content_type = download(PAGE)
        result["page_status"] = "accessible"
        result["content_type"] = content_type
        parser = Links()
        parser.feed(html)
        result["resources"] = [r for r in parser.resources if urlparse(r["url"]).netloc.endswith("ipma.pt")][:100]
        scripts = [r["url"] for r in result["resources"] if r["tag"] == "script" and urlparse(r["url"]).netloc.endswith("ipma.pt")][:12]
        sources = [(PAGE, html)]
        for script in scripts:
            try:
                body, _ = download(script)
                sources.append((script, body))
            except Exception as exc:
                result["errors"].append({"url": script, "error": str(exc)})
        pattern = re.compile(r"[^\s\"'<>]{0,110}(?:sondag|tefig|sounding|TEMP|BUFR|\.json|\.csv)[^\s\"'<>]{0,150}", re.I)
        for url, body in sources:
            for match in pattern.findall(body):
                if len(result["candidate_references"]) >= 100:
                    break
                result["candidate_references"].append({"source": url, "snippet": match[:240]})
        result["note"] = "Referências candidatas não provam acesso a perfis numéricos; validar formato, origem e autorização antes de integrar."
    except Exception as exc:
        result["errors"].append({"url": PAGE, "error": str(exc)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"page_status": result["page_status"], "references": len(result["candidate_references"]), "errors": result["errors"]}, ensure_ascii=False))
    if result["page_status"] != "accessible":
        raise SystemExit("Página IPMA inacessível; auditoria guardada.")

if __name__ == "__main__":
    main()
