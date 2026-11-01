"""Generate the cycle-1 held-out long-page set and hash it before any run.

Writes `heldout_long_pages.json` and `manifest.json` into the evidence run
directory, and a readable copy under `evidence/cycles/1/`. The experiment reads
only the run-directory copy, which the runner hashes in the ledger.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evidence" / "experiments"))

from _common import ROOT, emit, run_dir  # noqa: E402

OUT = run_dir()
CANON = ROOT / "evidence" / "cycles" / "1"
CANON.mkdir(parents=True, exist_ok=True)

pages = []
for i in range(30):
    head = f"HEAD-{i:02d}-ALPHA"
    mid = f"MID-{i:02d}-BETA"
    tail = f"TAIL-{i:02d}-GAMMA"
    paras = []
    for j in range(220):
        if j == 0:
            paras.append(f"<p>{head} is the first marker in this document.</p>")
        elif j == 70:
            paras.append(f"<p>{mid} is the middle marker in this document.</p>")
        elif j == 219:
            paras.append(f"<p>{tail} is the final marker in this document.</p>")
        else:
            paras.append(f"<p>Section {j} contains routine operational text without any marker.</p>")
    html = "<!doctype html><html><head><title>Held-out long page</title></head><body><main><article>" + "".join(paras) + "</article></main></body></html>"
    pages.append({"id": f"long-{i:02d}", "html": html, "head": head, "mid": mid, "tail": tail})

payload = {"version": "cycle1-heldout-v1", "kind": "SIMULATED", "pages": pages}
data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
digest = hashlib.sha256(data).hexdigest()

(OUT / "heldout_long_pages.json").write_bytes(data)
(CANON / "heldout_long_pages.json").write_bytes(data)
manifest = {
    "dataset": "cycle1 held-out long pages",
    "version": payload["version"],
    "records": len(pages),
    "sha256": digest,
    "generated_by": "evidence/cycles/1/make_heldout.py",
    "used_by": ["EXP-101", "EXP-102"],
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
(CANON / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

emit(
    {
        "experiment": "EXP-100",
        "kind": "heldout-dataset",
        "class": "SIMULATED",
        "rows": [{**manifest}],
        "summary": {"records": len(pages), "sha256": digest},
        "limitations": [
            "Synthetic pages, SIMULATED class; they test passage selection, not live-web extraction.",
            "Generated after diagnosing the dev fixture; the dev fixture is not in this set.",
        ],
    }
)
print("dataset sha256", digest)
