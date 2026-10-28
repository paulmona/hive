#!/usr/bin/env python3
"""Publish one agent's vault status as a retained MQTT message.

Run by hive-vault-job after a nightly or health run. Deterministic: it calls the
skill's own vault_health.py, counts open conflict notes, and publishes a JSON
summary to hive/status/vault-health/<agent> with retain=true, so whoever reads
the topic next (Sunday's morning briefing) gets the latest without a live
session on this side. Broker settings come from the environment
(MQTT_BROKER_URL, MQTT_USERNAME, MQTT_PASSWORD, MQTT_TOPIC_PREFIX), the same
variables the MQTT channel plugin reads.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

TRASH_DIRS = {".trash", "_trash"}
SKIP_DIRS = {".obsidian", "Templates", "raw", ".claude-runs"} | TRASH_DIRS
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---", re.S)


def vault_health(skill_root: str, vault: str) -> dict:
    out = subprocess.run(
        ["uv", "run", "--directory", skill_root, "scripts/vault_health.py",
         "--path", vault, "--json"],
        capture_output=True, text=True, timeout=300,
    )
    if out.returncode != 0:
        return {"error": (out.stderr or out.stdout).strip()[-300:]}
    data = json.loads(out.stdout)
    by_sev: dict[str, int] = {}
    for issue in data.get("issues", []):
        sev = issue.get("severity", "info")
        by_sev[sev] = by_sev.get(sev, 0) + 1
    return {
        "notes": data.get("total_notes"),
        "issues": data.get("total_issues"),
        "by_severity": by_sev,
    }


def scan_conflicts(vault: str) -> tuple[list[str], list[str]]:
    """Open conflict notes, split into live ones and ones sitting in the trash.

    A note still marked `status: open` after being moved to the trash is
    invisible everywhere else: the health scanner skips trash folders, so the
    vault reports clean while the contradiction stands. Trashed ones are counted
    separately rather than dropped, because silence there and a genuinely clean
    vault are indistinguishable to whoever reads the status topic.
    """
    live, trashed = [], []
    for path in Path(vault).rglob("*.md"):
        parts = path.relative_to(vault).parts
        in_trash = any(part in TRASH_DIRS for part in parts)
        if not in_trash and any(part in SKIP_DIRS for part in parts):
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        m = FRONTMATTER.match(head)
        if not m:
            continue
        fm = m.group(1)
        if re.search(r"^type:\s*conflict\s*$", fm, re.M) and re.search(r"^status:\s*open\s*$", fm, re.M):
            (trashed if in_trash else live).append(str(path.relative_to(vault)))
    return sorted(live), sorted(trashed)


def latest_report(vault: str, date: str) -> str | None:
    hits = sorted(Path(vault).glob(f"**/Vault Health {date}.md"))
    return str(hits[-1].relative_to(vault)) if hits else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--job", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--skill-root", required=True)
    ap.add_argument("--exit-code", type=int, required=True)
    ap.add_argument("--duration", type=int, required=True)
    a = ap.parse_args()

    conflicts, trashed = scan_conflicts(a.vault)
    status = {
        "agent": a.agent,
        "job": a.job,
        "date": a.date,
        "ok": a.exit_code == 0,
        "exit_code": a.exit_code,
        "duration_sec": a.duration,
        "health": vault_health(a.skill_root, a.vault),
        "open_conflicts": len(conflicts),
        "conflict_notes": conflicts[:10],
        "trashed_conflicts": len(trashed),
        "trashed_conflict_notes": trashed[:10],
        "report": latest_report(a.vault, a.date) if a.job == "health" else None,
        "published_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    url = urlparse(os.environ.get("MQTT_BROKER_URL", "mqtt://localhost:1883"))
    prefix = os.environ.get("MQTT_TOPIC_PREFIX", "claude")
    topic = f"{prefix}/status/vault-health/{a.agent}"
    # Same envelope the channel plugin uses, so an inbox read shows
    # "[ts] vault-job/friday: {...}" rather than an anonymous payload.
    payload = json.dumps({"sender": f"vault-job/{a.agent}", "content": json.dumps(status, separators=(",", ":"))})

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if os.environ.get("MQTT_USERNAME"):
        client.username_pw_set(os.environ["MQTT_USERNAME"], os.environ.get("MQTT_PASSWORD"))
    if url.scheme in ("mqtts", "ssl"):
        client.tls_set()
    client.connect(url.hostname or "localhost", url.port or 1883, keepalive=30)
    client.loop_start()
    info = client.publish(topic, payload, qos=1, retain=True)
    info.wait_for_publish(timeout=15)
    client.loop_stop()
    client.disconnect()
    if not info.is_published():
        print(f"publish to {topic} did not complete", file=sys.stderr)
        return 1
    print(
        f"published {topic}: ok={status['ok']} conflicts={status['open_conflicts']} "
        f"trashed={status['trashed_conflicts']} issues={status['health'].get('issues')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
