#!/usr/bin/env python3
"""End-to-end check of sinclair-gws: the real server process, over MCP stdio, against Google.

Runs every tool on one thread. Needs SINCLAIR_GWS_SA_KEY_PATH and a recent message from
--from-addr in Paul's mailbox. Without --send, the reply draft is deleted instead of sent.
Prints ids, headers and booleans only, never message bodies.

    uv run --directory tools/sinclair-gws python scripts/e2e.py            # no send
    uv run --directory tools/sinclair-gws python scripts/e2e.py --send     # sends the reply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sinclair_gws.google import Google  # cleanup only; the checks go through the MCP tools

PASS, FAIL = "  ok ", " FAIL"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{PASS if ok else FAIL}  {name}{'  ' + detail if detail else ''}")


async def call(s: ClientSession, tool: str, **args):
    r = await s.call_tool(tool, args)
    sc = getattr(r, "structured_content", None)
    if sc is not None:
        # the SDK wraps non-object results (lists) as {"result": ...}
        return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
    blocks = [json.loads(c.text) for c in r.content if getattr(c, "type", "") == "text"]
    return blocks[0] if len(blocks) == 1 else blocks


async def run(from_addr: str, do_send: bool) -> int:
    g = Google()
    cleanup: list = []
    params = StdioServerParameters(command="uv", args=["run", "-q", "--directory", ".", "sinclair-gws"], env={**os.environ})
    when = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=21)
    st, en = when.isoformat(timespec="seconds"), (when + timedelta(minutes=15)).isoformat(timespec="seconds")
    try:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = sorted(t.name for t in (await s.list_tools()).tools)
                check("tools registered", len(tools) == 12, ",".join(tools))

                who = await call(s, "whoami")
                check("whoami: both identities mint and Gmail agrees",
                      all(who["checks"][a]["token"] and who["checks"][a]["gmail"] for a in ("sinclair", "paul")))

                # ---- mail: one thread from --from-addr in Paul's mailbox
                hits = await call(s, "search", mailbox="paul", query=f"from:{from_addr} newer_than:2d", max_results=1)
                if not hits:
                    check("search: fresh message from the personal address in Paul's mailbox", False, "none found; send one and rerun")
                else:
                    orig = hits[0]
                    check("search: fresh message found", True, f"id={orig['id'][:8]}.. holder={orig['holder']}")
                    m = await call(s, "read", message_id=orig["id"])
                    check("read: holder is paul", m.get("holder") == "paul", f"thread={m.get('thread_id','')[:8]}..")

                    rep = await call(s, "draft_reply", message_id=orig["id"],
                                     body="sinclair-gws end-to-end (VIE-75): drafted as you by the server over MCP, promoted by draft id. Nothing to action.")
                    check("draft_reply: sender derived, From display-named",
                          rep.get("as") == "paul" and rep.get("from") == "Paul Monaghan <paul.monaghan@viewbridge.ai>")
                    check("draft_reply: same thread, Re: subject",
                          rep.get("thread_id") == orig["thread_id"] and rep.get("subject", "").startswith("Re:"))

                    if do_send:
                        sent = await call(s, "send_draft", draft_id=rep["draft_id"])
                        check("send_draft: sent as paul in thread", sent.get("as") == "paul" and sent.get("thread_id") == orig["thread_id"],
                              f"message={str(sent.get('message_id'))[:8]}..")
                        again = await call(s, "send_draft", draft_id=rep["draft_id"])
                        check("send_draft again: not_found (Gmail deleted the draft)", again.get("error") == "not_found")
                        back = await call(s, "read", message_id=sent["message_id"])
                        check("sent message readable, SENT label, same thread",
                              "SENT" in back.get("labels", []) and back.get("thread_id") == orig["thread_id"])
                    else:
                        cleanup.append(("draft", "paul", rep["draft_id"]))
                        check("send_draft: skipped (no --send); draft will be deleted", True)

                    fwd = await call(s, "forward", message_id=orig["id"], to="sinclair.viewbridge@viewbridge.ai", note="e2e forward check")
                    cleanup.append(("draft", "paul", fwd["draft_id"]))
                    check("forward: from holder (paul), Fwd: subject",
                          fwd.get("as") == "paul" and fwd.get("subject", "").startswith("Fwd:") and "Forwarded message" in fwd.get("body", ""))

                bad = await call(s, "draft_new", as_="someone-else", to="a@b.c", subject="x", body="y")
                check("draft_new as unknown identity refused cleanly", bad.get("error") == "unknown_identity")

                # ---- calendar
                ev = await call(s, "create_event", as_="sinclair", summary="e2e meet", start=st, end=en, meet=True)
                cleanup.append(("event", "sinclair", ev["id"]))
                check("create_event(meet): hangoutLink present", bool(ev.get("meet")))

                hold = await call(s, "create_event", as_="paul", summary="e2e hold", start=st, end=en, tentative=True)
                cleanup.append(("event", "paul", hold["id"]))
                check("hold on Paul's calendar: tentative, HOLD: prefix",
                      hold.get("status") == "tentative" and hold.get("summary", "").startswith("HOLD: "))
                conf = await call(s, "update_event", as_="paul", event_id=hold["id"], confirm=True)
                check("confirm hold: confirmed, prefix dropped", conf.get("status") == "confirmed" and conf.get("summary") == "e2e hold")

                # Sinclair must not be able to remove an event Paul organised. Google answers 404 for an
                # event that is not on his calendar and the organiser check refuses one that is; either way
                # the event must still exist for Paul afterwards. (The organiser branch is unit-tested;
                # an attendee copy does not appear on his calendar via the API without an invite email.)
                refused = await call(s, "delete_event", as_="sinclair", event_id=hold["id"])
                still = await call(s, "agenda", as_="paul", days=30)
                check("sinclair deleting Paul's event: refused and event survives",
                      refused.get("error") in ("not_organizer", "google") and any(e["id"] == hold["id"] for e in still),
                      refused.get("error", ""))
                gone = await call(s, "delete_event", as_="sinclair", event_id="does-not-exist")
                check("deleting an unknown event: clean google 404", gone.get("error") == "google" and gone.get("status") == 404)

                fb = await call(s, "freebusy", identities=["sinclair", "paul"], time_min=when.strftime("%Y-%m-%dT00:00:00Z"),
                                time_max=(when + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"))
                check("freebusy: both identities answer", set(fb) == {"sinclair", "paul"} and not fb["paul"]["errors"])
                ag = await call(s, "agenda", as_="paul", days=30)
                check("agenda: the hold is visible on Paul's agenda", any(e["id"] == hold["id"] for e in ag))
    finally:
        for kind, alias, ident in cleanup:
            try:
                if kind == "draft":
                    g.gmail_delete_draft(alias, ident)
                else:
                    g.request(alias, "DELETE", f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{ident}")
            except Exception as e:  # noqa: BLE001
                print(f" WARN  cleanup {kind} {ident[:8]}.. as {alias}: {type(e).__name__}")
        print(f"cleaned up {len(cleanup)} artefacts")
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-addr", default="personal@example.com")
    ap.add_argument("--send", action="store_true", help="actually promote the reply draft")
    a = ap.parse_args()
    sys.exit(asyncio.run(run(a.from_addr, a.send)))
