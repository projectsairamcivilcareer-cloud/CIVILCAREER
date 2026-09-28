"""Fetch and version official public curriculum sources listed in data/official_sources.json.

Only sources explicitly configured by the project maintainers are fetched.
The script never fabricates syllabus content. It records source metadata and
content hashes; changed source documents are archived for later structured
verification before publication in the student-facing syllabus pages.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "official_sources.json"
ARCHIVE = ROOT / "data" / "official_source_archive"
STATE_FILE = ROOT / "data" / "official_source_state.json"
MAX_BYTES = 25 * 1024 * 1024
TIMEOUT = 30


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")[:100] or "source"


def fetch(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Only absolute HTTPS URLs are permitted")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CivilCareer-OfficialSourceMonitor/1.0 (public curriculum monitoring)"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"Source exceeded {MAX_BYTES} byte limit")
    return data, content_type, final_url


def main():
    registry = load_json(REGISTRY, {"sources": []})
    state = load_json(STATE_FILE, {"sources": {}})
    state.setdefault("sources", {})
    checked_at = datetime.now(timezone.utc).isoformat()
    changes = 0
    failures = 0

    for source in registry.get("sources", []):
        source_id = str(source.get("id", "")).strip()
        url = str(source.get("url", "")).strip()
        if not source_id or not url or "REPLACE_WITH" in url:
            print(f"SKIP unconfigured source: {source_id or '(missing id)'}")
            continue
        try:
            data, content_type, final_url = fetch(url)
            digest = hashlib.sha256(data).hexdigest()
            previous = state["sources"].get(source_id, {})
            record = {
                "id": source_id,
                "title": source.get("title", source_id),
                "authority": source.get("authority", ""),
                "category": source.get("category", ""),
                "source_url": url,
                "final_url": final_url,
                "checked_at": checked_at,
                "sha256": digest,
                "content_type": content_type,
                "bytes": len(data),
                "status": "unchanged" if previous.get("sha256") == digest else "changed",
            }
            if previous.get("sha256") != digest:
                ARCHIVE.mkdir(parents=True, exist_ok=True)
                suffix = ".pdf" if "pdf" in content_type.lower() or data[:4] == b"%PDF" else ".html"
                target = ARCHIVE / f"{safe_name(source_id)}-{digest[:16]}{suffix}"
                target.write_bytes(data)
                record["archive_file"] = str(target.relative_to(ROOT))
                record["review_status"] = "pending_official_content_validation"
                changes += 1
                print(f"CHANGED {source_id}: archived {target.name}; not auto-published")
            else:
                record["archive_file"] = previous.get("archive_file")
                record["review_status"] = previous.get("review_status", "pending_official_content_validation")
                print(f"UNCHANGED {source_id}")
            state["sources"][source_id] = record
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            failures += 1
            old = state["sources"].get(source_id, {})
            old.update({
                "id": source_id,
                "title": source.get("title", source_id),
                "source_url": url,
                "last_error_at": checked_at,
                "last_error": str(exc)[:500],
                "last_attempt_status": "fetch_failed",
            })
            state["sources"][source_id] = old
            print(f"ERROR {source_id}: {exc}", file=sys.stderr)

    state["last_run_at"] = checked_at
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Sync finished: {changes} changed, {failures} failed.")
    # A failed source is logged but does not erase the last successful archive.
    if failures and not changes:
        print("One or more sources failed; prior snapshots were retained.")


if __name__ == "__main__":
    main()
