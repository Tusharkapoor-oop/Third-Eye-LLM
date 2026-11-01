"""EXP-101 / EXP-102: long-page passage reachability before and after the cycle-1 fix.

Reads the hashed held-out set from evidence/raw/EXP-100/, serves it locally, and
records whether head/middle/tail markers appear in returned passages. No query is
passed, matching the measured loss.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from _common import ROOT, emit

from weblens.cache import Cache
from weblens.config import Settings
from weblens.extract.service import ExtractionService
from weblens.net import SafeFetcher

DATASET = ROOT / "evidence" / "raw" / "EXP-100b" / "heldout_long_pages.json"
PAGES = json.loads(DATASET.read_text(encoding="utf-8"))["pages"]
BY_PATH = {f"/p{i}": p for i, p in enumerate(PAGES)}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        page = BY_PATH.get(self.path)
        if page is None:
            body = b"not found"
            self.send_response(404)
        else:
            body = page["html"].encode("utf-8")
            self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()


async def main() -> list[dict]:
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            cache_dir=Path(tmp) / "cache",
            cache_enabled=False,
            allow_private_networks=True,
            allow_browser=False,
            total_timeout_s=20,
        )
        cache = Cache(settings)
        fetcher = SafeFetcher(settings, cache)
        svc = ExtractionService(settings, fetcher, cache)
        for i, page in enumerate(PAGES):
            started = time.perf_counter()
            try:
                out = await svc.extract(f"http://127.0.0.1:{port}/p{i}", query=None, max_tokens=1200)
                payload = svc.payload(out)
                text = " ".join(p.get("x", "") for p in payload.get("ps", []))
                status = payload["status"]
                tok = payload["tok"]
                passages = len(payload.get("ps", []))
            except Exception as exc:
                text, status, tok, passages = "", f"exception:{type(exc).__name__}", 0, 0
            ms = (time.perf_counter() - started) * 1000
            rows.append(
                {
                    "page": page["id"],
                    "status": status,
                    "head_found": page["head"] in text,
                    "mid_found": page["mid"] in text,
                    "tail_found": page["tail"] in text,
                    "tok": tok,
                    "passages": passages,
                    "ms": round(ms, 3),
                }
            )
        await fetcher.close()
        cache.close()
    return rows


rows = asyncio.run(main())
server.shutdown()
emit(
    {
        "experiment": "EXP-101/102",
        "kind": "long-page-reachability",
        "class": "SIMULATED",
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "rows": rows,
        "summary": {
            "pages": len(rows),
            "head_found": sum(r["head_found"] for r in rows),
            "mid_found": sum(r["mid_found"] for r in rows),
            "tail_found": sum(r["tail_found"] for r in rows),
            "tokens_total": sum(r["tok"] for r in rows),
        },
        "limitations": [
            "Synthetic pages, SIMULATED class; n=30 meets the aggregate threshold but is not live-web evidence.",
            "No query is passed, matching the measured loss; query-focused selection is unchanged by the fix.",
        ],
    }
)
