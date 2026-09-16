#!/usr/bin/env python3
"""Refresh data/latest.json from Klaviyo from WINDOW_START through today Pacific."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API_KEY = os.environ.get("KLAVIYO_API_KEY", "")
REV = "2026-01-15"
BASE = "https://a.klaviyo.com/api"
PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "latest.json"

METRICS = {
    "Account Registration": "UAMbHw",
    "Trial Granted": "V5TWMT",
    "App Installed": "TF2uEs",
    "Received Email": "WnHjkX",
    "Opened Email": "SaQvHn",
    "Clicked Email": "TXgpdR",
    "Received Push": "SPvuUk",
    "Opened Push": "UCi5Th",
    "Application Paired": "WM4Tkh",
    "Passwords Imported": "XWK9pN",
    "Tru8 Connect Profile Created": "SLPnpe",
    "Opened App": "Sm8cTj",
    "Privacy Mate Scan Completed": "UArXPc",
    "Recovery Contact Added": "TRBaLt",
}

ONBOARDING = "Ufq8UQ"
TRIAL_FLOW = "TRVmes"
L801 = "YaPzNc"


def req(raw_url: str, method: str = "GET", body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(raw_url, data=data, method=method)
    r.add_header("Authorization", f"Klaviyo-API-Key {API_KEY}")
    r.add_header("accept", "application/vnd.api+json")
    r.add_header("revision", REV)
    if body is not None:
        r.add_header("content-type", "application/vnd.api+json")
    for attempt in range(6):
        try:
            with urllib.request.urlopen(r, timeout=75) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            if e.code == 429:
                time.sleep(2 + attempt * 2)
                continue
            raise RuntimeError(f"{e.code} {err[:400]}") from e
    raise RuntimeError("retries exhausted")


def page_events(metric_id: str, start: str, end: str) -> list[dict]:
    f = f'equals(metric_id,"{metric_id}"),greater-or-equal(datetime,{start}),less-than(datetime,{end})'
    url = BASE + "/events/?filter=" + urllib.parse.quote(f) + "&sort=datetime"
    out: list[dict] = []
    while url:
        d = req(url)
        out.extend(d.get("data") or [])
        nxt = (d.get("links") or {}).get("next")
        if not nxt or nxt == url:
            break
        url = nxt
        time.sleep(0.12)
    return out


def pid(ev: dict) -> str | None:
    return ((ev.get("relationships") or {}).get("profile") or {}).get("data", {}).get("id")


def props(ev: dict) -> dict:
    return ev.get("attributes", {}).get("event_properties") or {}


def iso_pt_midnight(d) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=PT).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    if not API_KEY:
        raise SystemExit("KLAVIYO_API_KEY is not set")

    now = datetime.now(PT)
    start_env = os.environ.get("WINDOW_START", "2026-09-10")
    start_day = datetime.fromisoformat(start_env).date()
    end_day = now.date() + timedelta(days=1)
    start = iso_pt_midnight(start_day)
    end = iso_pt_midnight(end_day)

    installs = page_events(METRICS["App Installed"], start, end)
    regs = page_events(METRICS["Account Registration"], start, end)
    trials = page_events(METRICS["Trial Granted"], start, end)
    paired = page_events(METRICS["Application Paired"], start, end)
    imported = page_events(METRICS["Passwords Imported"], start, end)
    tru8 = page_events(METRICS["Tru8 Connect Profile Created"], start, end)
    recv_e = page_events(METRICS["Received Email"], start, end)
    open_e = page_events(METRICS["Opened Email"], start, end)
    click_e = page_events(METRICS["Clicked Email"], start, end)
    recv_p = page_events(METRICS["Received Push"], start, end)
    open_p = page_events(METRICS["Opened Push"], start, end)
    opened_app = page_events(METRICS["Opened App"], start, end)
    scans = page_events(METRICS["Privacy Mate Scan Completed"], start, end)
    recovery = page_events(METRICS["Recovery Contact Added"], start, end)

    reg_ids = {pid(ev) for ev in regs if pid(ev)}
    trial_ids = {pid(ev) for ev in trials if pid(ev)} & reg_ids

    def day_key(ev: dict) -> str:
        dt = datetime.fromisoformat(ev["attributes"]["datetime"].replace("Z", "+00:00")).astimezone(PT)
        return dt.strftime("%a") + f" {dt.month}/{dt.day}"

    daily_map: dict[str, dict] = defaultdict(lambda: {"installs": 0, "registrations": 0, "trials": 0})
    for ev in installs:
        daily_map[day_key(ev)]["installs"] += 1
    for ev in regs:
        daily_map[day_key(ev)]["registrations"] += 1
    for ev in trials:
        daily_map[day_key(ev)]["trials"] += 1

    days = []
    cursor = start_day
    while cursor < end_day:
        label = datetime(cursor.year, cursor.month, cursor.day).strftime("%a") + f" {cursor.month}/{cursor.day}"
        row = daily_map.get(label, {"installs": 0, "registrations": 0, "trials": 0})
        days.append({"day": label, "installs": row["installs"], "registrations": row["registrations"], "trials": row["trials"]})
        cursor += timedelta(days=1)

    def people_in(events, flow=None):
        s = set()
        for ev in events:
            p = pid(ev)
            if p not in reg_ids:
                continue
            if flow and props(ev).get("$flow") != flow:
                continue
            s.add(p)
        return s

    onb_recv = people_in(recv_e, ONBOARDING)
    onb_open = people_in(open_e, ONBOARDING)
    onb_click = people_in(click_e, ONBOARDING)
    trial_open = people_in(open_e, TRIAL_FLOW)
    l801 = sum(1 for ev in recv_e if props(ev).get("$flow") == L801)
    push_open = people_in(open_p)

    n = len(reg_ids) or 1
    funnel = [
        {"action": "Opened the app this week", "people": len(people_in(opened_app)), "share": f"{round(100 * len(people_in(opened_app)) / n)}%"},
        {"action": "Trial Granted", "people": len(trial_ids), "share": f"{round(100 * len(trial_ids) / n)}%"},
        {"action": "Privacy Mate scan completed", "people": len(people_in(scans)), "share": f"{round(100 * len(people_in(scans)) / n)}%"},
        {"action": "Tru8 Connect profile created", "people": len({pid(ev) for ev in tru8 if pid(ev) in reg_ids}), "share": f"{round(100 * len({pid(ev) for ev in tru8 if pid(ev) in reg_ids}) / n)}%"},
        {"action": "Recovery contact added", "people": len(people_in(recovery)), "share": f"{round(100 * len(people_in(recovery)) / n)}%"},
        {"action": "Application paired (desktop sync)", "people": len({pid(ev) for ev in paired if pid(ev) in reg_ids}), "share": "—"},
        {"action": "Passwords Imported", "people": len({pid(ev) for ev in imported if pid(ev) in reg_ids}), "share": f"{round(100 * len({pid(ev) for ev in imported if pid(ev) in reg_ids}) / n)}%"},
    ]

    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text())
        except json.JSONDecodeError:
            prev = {}
    prev_product = prev.get("product") or {}

    ios = 0
    android = 0
    for ev in regs:
        src = (props(ev).get("custom_source") or props(ev).get("Platform") or props(ev).get("OS Name") or "").lower()
        if src == "ios" or "ios" in src or "iphone" in src:
            ios += 1
        elif src == "android" or "android" in src:
            android += 1

    alerts = []
    if len({pid(ev) for ev in imported if pid(ev) in reg_ids}) == 0:
        alerts.append("Password import is 0.")
    if len({pid(ev) for ev in paired if pid(ev) in reg_ids}) <= 1:
        alerts.append("Desktop sync is still almost unused.")
    if not trial_open:
        alerts.append("Trial emails: 0 opens among new accounts.")
    if not push_open:
        alerts.append("Push: 0 opens among new accounts.")
    if l801 == 0:
        alerts.append("L8-01 Email to Registration delivered 0.")

    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timezone": "America/Los_Angeles",
        "window": {
            "label": f"{start_day.strftime('%b')} {start_day.day}–{now.strftime('%b')} {now.day}, {now.year}",
            "start": start_day.isoformat(),
            "end": now.date().isoformat(),
        },
        "product": {
            "spend_50pct": prev_product.get("spend_50pct"),
            "cpa_50pct": prev_product.get("cpa_50pct"),
            "cpi_50pct": prev_product.get("cpi_50pct"),
            "installs": len(installs),
            "registrations": len(reg_ids),
            "registrations_android": android,
            "registrations_ios": ios,
            "trials": len(trial_ids),
            "desktop_sync": len({pid(ev) for ev in paired if pid(ev) in reg_ids}),
            "password_import": len({pid(ev) for ev in imported if pid(ev) in reg_ids}),
            "tru8_usernames": len({pid(ev) for ev in tru8 if pid(ev) in reg_ids}),
            "paid_plans": prev_product.get("paid_plans", 0),
            "cancels": prev_product.get("cancels", 0),
            "install_to_account_pct": round(100 * len(reg_ids) / max(1, len(installs))),
        },
        "funnel": funnel,
        "daily": days,
        "email_push": {
            "l8_01_delivered": l801,
            "onboarding_received_people": len(onb_recv),
            "onboarding_opened_people": len(onb_open),
            "onboarding_clicked_people": len(onb_click),
            "trial_email_opened": len(trial_open),
            "push_opened": len(push_open),
            "no_live_email": max(0, len(reg_ids) - len(onb_recv)),
        },
        "alerts": alerts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {OUT} installs={len(installs)} regs={len(reg_ids)}")


if __name__ == "__main__":
    main()
