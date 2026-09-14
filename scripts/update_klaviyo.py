#!/usr/bin/env python3
"""Pull Klaviyo product stats for the last 5 Pacific days and write data/latest.json."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

API_KEY = os.environ["KLAVIYO_API_KEY"]
REV = "2026-01-15"
BASE = "https://a.klaviyo.com/api"
PT = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "latest.json"

METRICS = {
    "install": "TF2uEs",
    "registration": "UAMbHw",
    "trial": "V5TWMT",
    "paired": "WM4Tkh",
    "imported": "XWK9pN",
    "tru8": "SLPnpe",
    "opened_app": "Sm8cTj",
    "received_email": "WnHjkX",
    "opened_email": "SaQvHn",
    "clicked_email": "TXgpdR",
    "received_push": "SPvuUk",
    "opened_push": "UCi5Th",
}

ONBOARDING = "Ufq8UQ"
TRIAL_FLOW = "TRVmes"
L801 = "YaPzNc"


def req(url: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, method="GET" if body is None else "POST")
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
            if e.code == 429:
                time.sleep(2 + attempt * 2)
                continue
            raise
    raise RuntimeError("klaviyo retries exhausted")


def page_events(metric_id: str, start: str, end: str) -> list[dict]:
    filt = f'equals(metric_id,"{metric_id}"),greater-or-equal(datetime,{start}),less-than(datetime,{end})'
    url = BASE + "/events/?filter=" + urllib.parse.quote(filt) + "&sort=datetime"
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


def day_pt(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PT)
    return dt.date().isoformat()


def main() -> None:
    now = datetime.now(PT)
    start_day = (now - timedelta(days=4)).date()  # 5 calendar days including today
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=PT).astimezone(
        ZoneInfo("UTC")
    )
    end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(
        ZoneInfo("UTC")
    )
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    installs = page_events(METRICS["install"], start_iso, end_iso)
    regs = page_events(METRICS["registration"], start_iso, end_iso)
    trials = page_events(METRICS["trial"], start_iso, end_iso)
    paired = page_events(METRICS["paired"], start_iso, end_iso)
    imported = page_events(METRICS["imported"], start_iso, end_iso)
    tru8 = page_events(METRICS["tru8"], start_iso, end_iso)
    recv_e = page_events(METRICS["received_email"], start_iso, end_iso)
    open_e = page_events(METRICS["opened_email"], start_iso, end_iso)
    click_e = page_events(METRICS["clicked_email"], start_iso, end_iso)
    recv_p = page_events(METRICS["received_push"], start_iso, end_iso)
    open_p = page_events(METRICS["opened_push"], start_iso, end_iso)
    opens = page_events(METRICS["opened_app"], start_iso, end_iso)

    reg_ids = {pid(ev) for ev in regs if pid(ev)}
    trial_ids = {pid(ev) for ev in trials if pid(ev)}

    android = 0
    ios = 0
    for ev in regs:
        src = str(props(ev).get("custom_source") or "").lower()
        plat = str(props(ev).get("Platform") or props(ev).get("OS Name") or src)
        # Klaviyo registration often only has custom_source; fall back to install overlap later
        if "ios" in plat or "iphone" in plat:
            ios += 1
        elif "android" in plat:
            android += 1

    # Platform from matching install events on the same profiles
    install_plat = {}
    for ev in installs:
        p = pid(ev)
        if not p:
            continue
        osn = str(props(ev).get("OS Name") or props(ev).get("Platform") or "").lower()
        if osn:
            install_plat[p] = osn
    android = sum(1 for p in reg_ids if "android" in install_plat.get(p, ""))
    ios = sum(1 for p in reg_ids if "ios" in install_plat.get(p, "") or "iphone" in install_plat.get(p, ""))
    if android + ios < len(reg_ids):
        # leftover unknown — keep split if we have it, else leave unlabeled in totals only
        pass

    paired_new = {pid(ev) for ev in paired if pid(ev) in reg_ids}
    imported_new = {pid(ev) for ev in imported if pid(ev) in reg_ids}
    tru8_new = {pid(ev) for ev in tru8 if pid(ev) in reg_ids}
    opened_new = {pid(ev) for ev in opens if pid(ev) in reg_ids}

    def flow_people(events, flow):
        return {pid(ev) for ev in events if pid(ev) in reg_ids and props(ev).get("$flow") == flow}

    onb_people = flow_people(recv_e, ONBOARDING)
    onb_open = flow_people(open_e, ONBOARDING)
    onb_click = flow_people(click_e, ONBOARDING)
    l801 = sum(1 for ev in recv_e if props(ev).get("$flow") == L801)
    trial_open = flow_people(open_e, TRIAL_FLOW)
    push_open = {pid(ev) for ev in open_p if pid(ev) in reg_ids}

    days = []
    cursor = start_day
    today = now.date()
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    while cursor <= today:
        ds = cursor.isoformat()
        days.append(
            {
                "date": ds,
                "label": labels[cursor.weekday()],
                "installs": sum(1 for ev in installs if day_pt(ev["attributes"]["datetime"]) == ds),
                "registrations": sum(1 for ev in regs if day_pt(ev["attributes"]["datetime"]) == ds),
                "trials": sum(1 for ev in trials if day_pt(ev["attributes"]["datetime"]) == ds),
            }
        )
        cursor += timedelta(days=1)

    n_reg = len(reg_ids)
    n_ins = len({pid(ev) for ev in installs if pid(ev)}) or len(installs)
    alerts = []
    if len(imported_new) == 0:
        alerts.append("Password import is 0.")
    if n_ins and ios and n_reg:
        alerts.append(f"New accounts this window: {n_reg}. Desktop sync {len(paired_new)}.")
    if len(trial_open) == 0 and len(trial_ids):
        alerts.append("Trial emails: 0 opens on new accounts.")
    if len(push_open) == 0:
        alerts.append("Push: 0 opens on new accounts.")

    prev = {}
    if OUT.exists():
        prev = json.loads(OUT.read_text())

    payload = {
        "updated_at": now.isoformat(timespec="seconds"),
        "timezone": "America/Los_Angeles",
        "window": {
            "label": f"{start_day.strftime('%a %b %-d')} – {today.strftime('%a %b %-d')}",
            "start": start_day.isoformat(),
            "end": today.isoformat(),
        },
        "product": {
            "app_installs": len(installs),
            "registrations_android": android,
            "registrations_ios": ios,
            "registrations": n_reg,
            "install_to_account_pct": round(100 * n_reg / len(installs), 1) if installs else 0,
            "trials": len(trial_ids),
            "desktop_sync": len(paired_new),
            "password_import": len(imported_new),
            "tru8_usernames": len(tru8_new),
            "paid_plans": prev.get("product", {}).get("paid_plans", 0),
            "cancels": prev.get("product", {}).get("cancels", 0),
            "opened_app_people": len(opened_new),
            "open_events": sum(1 for ev in opens if pid(ev) in reg_ids),
        },
        "paid": prev.get("paid")
        or {
            "spend_50pct": None,
            "cpa_50pct": None,
            "cpi_50pct": None,
            "note": "Paid ads are not auto-pulled yet. Last snapshot stays until the next full review.",
        },
        "email_push": {
            "l801_delivered": l801,
            "onboarding_people": len(onb_people),
            "onboarding_opened": len(onb_open),
            "onboarding_clicked": len(onb_click),
            "trial_email_opened": len(trial_open),
            "push_opened": len(push_open),
        },
        "daily": days,
        "alerts": alerts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT} regs={n_reg} installs={len(installs)}")


if __name__ == "__main__":
    main()
