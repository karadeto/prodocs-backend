"""Folder-classification eval: run the real extraction against a golden set.

    uv run python evals/run_folder_eval.py [evals/golden/folders.sample.jsonl]

Golden file format (JSONL), one document per line:
    {"name": "...", "text": "<full document text>",
     "expected_code": "VERS-KRANKEN" | null, "expected_vendor": "<normalized>" | null}

Grow this file from real (anonymized) documents — especially every document
the system ever misfiled. Run it before shipping any prompt, taxonomy, or
model change; the accuracy number replaces "it feels better".
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.extract import evidence_ok, extract_record  # noqa: E402
from app.ingestion.routing import normalize_vendor  # noqa: E402

CONCURRENCY = 4


async def eval_case(sem: asyncio.Semaphore, case: dict) -> dict:
    async with sem:
        try:
            record = await extract_record(case["text"])
        except Exception as e:
            return {"name": case["name"], "ok": False, "error": str(e)[:200]}

    got_code = record.subcategory_code.value if record.subcategory_code else None
    code_ok = got_code == case["expected_code"]
    vendor_ok = True
    if case.get("expected_vendor"):
        vendor_ok = normalize_vendor(record.vendor_name) == case["expected_vendor"]

    return {
        "name": case["name"],
        "ok": code_ok and vendor_ok,
        "expected_code": case["expected_code"],
        "got_code": got_code,
        "vendor_ok": vendor_ok,
        "got_vendor": normalize_vendor(record.vendor_name),
        "evidence_ok": evidence_ok(record, case["text"]),
    }


async def main() -> None:
    golden_path = Path(sys.argv[1] if len(sys.argv) > 1 else "evals/golden/folders.sample.jsonl")
    cases = [json.loads(line) for line in golden_path.read_text().splitlines() if line.strip()]

    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(eval_case(sem, c) for c in cases))

    passed = sum(1 for r in results if r["ok"])
    print(f"\n{'=' * 64}\nFolder classification eval — {golden_path}\n{'=' * 64}")
    for r in results:
        mark = "✅" if r["ok"] else "❌"
        if "error" in r:
            print(f"{mark} {r['name']}: ERROR {r['error']}")
        else:
            detail = f"expected={r['expected_code']} got={r['got_code']}"
            if not r["vendor_ok"]:
                detail += f" vendor={r['got_vendor']}"
            if not r["evidence_ok"]:
                detail += " [evidence-failed]"
            print(f"{mark} {r['name']}: {detail}")
    print(f"{'=' * 64}\nAccuracy: {passed}/{len(results)} = {passed / len(results):.0%}\n")

    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
