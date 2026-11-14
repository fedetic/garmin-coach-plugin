"""Direct Hevy access for athletes who log their lifting in the Hevy app.

Uses Hevy's official public API (https://api.hevyapp.com/docs, Hevy Pro required)
with the standard library only, so there is no third-party code between the
coach and the API key. Returns small, already-parsed values; raw Hevy JSON
never leaves this module.

Endpoints and field names were taken from Hevy's published OpenAPI spec
(2026-11). Hevy says the API may change without notice. Two facts shape the design:
- there is no calendar: a routine is a template in the athlete's library, so the
  coach keeps one routine per planned session and updates it in place each week;
- there is no DELETE for routines: a bad write is reported, never silently "undone".

The API key comes from $HEVY_API_KEY or from ~/.hevy/api-key (owner-only file
written by `coach-hevy-auth`).
"""
from __future__ import annotations

import getpass
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from . import garmin

API = "https://api.hevyapp.com"
KEY_FILE = "~/.hevy/api-key"
AUTH_HINT = ("Hevy API key missing or rejected. Hevy Pro is required. Create a key at "
             "https://hevy.com/settings?developer, then run once in a terminal: "
             "uvx --from \"git+https://github.com/fedetic/garmin-coach-plugin#subdirectory=server\" coach-hevy-auth")
UA = "garmin-coach (open-source training coach)"

_client = None
_templates: list[dict] | None = None


class HevyError(RuntimeError):
    pass


def set_client(client) -> None:
    """Inject a client (tests) or reset (None)."""
    global _client, _templates
    _client, _templates = client, None


def key_path() -> Path:
    return Path(os.path.expanduser(os.path.expandvars(os.environ.get("HEVY_KEY_FILE") or KEY_FILE)))


def api_key() -> str | None:
    k = (os.environ.get("HEVY_API_KEY") or "").strip()
    if k:
        return k
    p = key_path()
    return p.read_text().strip() or None if p.is_file() else None


def configured() -> bool:
    return api_key() is not None


class Client:
    """Minimal HTTP client: api-key header, JSON in/out, patient with rate limits."""

    def __init__(self, key: str):
        self.key = key

    def request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(4):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "api-key": self.key, "accept": "application/json", "user-agent": UA,
                **({"content-type": "application/json"} if data is not None else {})})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code == 429 and attempt < 3:
                    time.sleep(min(float(e.headers.get("Retry-After") or 2 * (attempt + 1)), 20))
                    continue
                if e.code in (401, 403) and "routine-limit" not in detail:
                    raise HevyError(f"{AUTH_HINT} (HTTP {e.code})") from e
                raise HevyError(f"Hevy {method} {path} -> HTTP {e.code}: {detail}") from e
            except urllib.error.URLError as e:
                raise HevyError(f"could not reach Hevy: {e.reason}") from e
        raise HevyError("Hevy kept rate-limiting; try again in a minute")


def client():
    global _client
    if _client is None:
        key = api_key()
        if not key:
            raise HevyError(AUTH_HINT)
        _client = Client(key)
    return _client


def pause() -> None:
    time.sleep(0.2)  # Hevy rate-limits; stay well under it


def _paged(path: str, key: str, page_size: int, params: dict | None = None):
    """Yield items page by page until the last page."""
    page = 1
    while True:
        r = client().request("GET", path, {**(params or {}), "page": page, "pageSize": page_size})
        yield from r.get(key) or []
        if page >= int(r.get("page_count") or 1):
            return
        page += 1
        pause()


# ---------------------------------------------------------------- reads

def user_info() -> dict:
    r = client().request("GET", "/v1/user/info")
    u = r.get("data") or r
    return {k: u.get(k) for k in ("username", "name", "weight_unit", "distance_unit", "is_pro")}


def _day(ts: str | None) -> str | None:
    return ts[:10] if ts else None


def list_workouts(start: str, end: str) -> list[dict]:
    """Workouts with start date in [start, end], oldest first. The API lists newest first, so
    stop paging once a whole page is older than `start`."""
    out = []
    for w in _paged("/v1/workouts", "workouts", 10):
        d = _day(w.get("start_time"))
        if d and d < start:
            break
        if d and d <= end:
            out.append(w)
    return sorted(out, key=lambda w: w.get("start_time") or "")


def body_measurements(start: str, end: str) -> list[dict]:
    out = []
    for m in _paged("/v1/body_measurements", "body_measurements", 10):
        d = (m.get("date") or "")[:10]
        if d and start <= d <= end:
            out.append({"date": d, "weight_kg": m.get("weight_kg"), "body_fat_pct": m.get("fat_percent")})
    return [m for m in out if m["weight_kg"] is not None or m["body_fat_pct"] is not None]


def exercise_templates(refresh: bool = False) -> list[dict]:
    """Every exercise the athlete can use: Hevy's library plus their custom ones (cached per process;
    refresh after they create a custom exercise)."""
    global _templates
    if _templates is None or refresh:
        _templates = [{"id": t["id"], "title": t.get("title") or "", "type": t.get("type"),
                       "muscle": t.get("primary_muscle_group"), "equipment": t.get("equipment"),
                       "custom": bool(t.get("is_custom"))}
                      for t in _paged("/v1/exercise_templates", "exercise_templates", 100)]
    return _templates


def _tokens(text: str) -> set[str]:
    t = garmin._norm(text)
    return {p for p in t.split("_") if p}


def find_templates(query: str, limit: int = 6, refresh: bool = False) -> list[dict]:
    """Rank the athlete's Hevy exercises against a name ("barbell_bench_press", "Bench Press (Barbell)").
    A candidate with exactly the same words scores 2+, so callers can auto-accept only those."""
    q = _tokens(query)
    scored = []
    for t in exercise_templates(refresh):
        e = _tokens(t["title"])
        hit = len(q & e)
        if not hit:
            continue
        score = hit / len(q) + hit / len(e) + (2 if q == e else 0) + (0.1 if t["custom"] else 0)
        scored.append((score, t))
    scored.sort(key=lambda s: (-s[0], len(s[1]["title"])))
    return [{**t, "score": round(s, 2)} for s, t in scored[:limit]]


def resolve_template(query: str) -> tuple[str | None, list[dict]]:
    """(template_id, candidates). The id is returned only for one unambiguous exact match."""
    cands = find_templates(query, 4)
    exact = [c for c in cands if c["score"] >= 2]
    return (exact[0]["id"] if len(exact) == 1 else None), cands


# ---------------------------------------------------------------- workouts -> db rows

_GARMIN_CACHE: dict[str, tuple[str | None, str]] = {}


def exercise_key(title: str) -> tuple[str | None, str]:
    """Hevy title -> (garmin category or None, exercise key). Goal metrics (e1rm:BARBELL_BENCH_PRESS)
    and muscle-group counts use Garmin's taxonomy, so map a Hevy exercise onto it when it has
    exactly the same words; otherwise keep the title as an UPPER_SNAKE key."""
    if title not in _GARMIN_CACHE:
        want = _tokens(title)
        hit = next((m for m in garmin.find_exercise(title, limit=3)
                    if set(m["exercise"].split("_")) == want), None)
        _GARMIN_CACHE[title] = (hit["category"], hit["exercise"]) if hit else \
            (None, re.sub(r"[^A-Z0-9]+", "_", title.upper()).strip("_") or "UNKNOWN")
    return _GARMIN_CACHE[title]


def parse_workout(w: dict) -> tuple[dict, list[dict]]:
    """Hevy workout -> (workouts row, workout_sets rows). Warm-up sets are dropped (they would
    inflate volume and distort e1RM); failure and drop sets count as working sets."""
    start, end = w.get("start_time"), w.get("end_time")
    dur = None
    try:
        dur = (datetime.fromisoformat(end.replace("Z", "+00:00")) -
               datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
    except (AttributeError, ValueError):
        pass
    row = {"hevy_workout_id": w["id"], "hevy_routine_id": w.get("routine_id"), "date": _day(start),
           "name": w.get("title"), "sport": "strength_training", "duration_sec": dur,
           "notes": w.get("description")}
    sets, n = [], 0
    for ex in sorted(w.get("exercises") or [], key=lambda e: e.get("index", 0)):
        cat, key = exercise_key(ex.get("title") or "")
        for s in sorted(ex.get("sets") or [], key=lambda s: s.get("index", 0)):
            if s.get("type") == "warmup":
                continue
            if not any(s.get(k) for k in ("reps", "duration_seconds", "weight_kg", "distance_meters")):
                continue
            n += 1
            sets.append({"set_order": n, "category": cat, "exercise": key,
                         "weight_kg": s.get("weight_kg"), "reps": int(s["reps"]) if s.get("reps") else None,
                         "duration_sec": s.get("duration_seconds"), "rpe": s.get("rpe")})
    return row, sets


# ---------------------------------------------------------------- block session -> routine

def _set(p: dict) -> dict:
    reps = p.get("reps")
    s: dict = {"type": "normal", "weight_kg": p.get("weight_kg")}
    if isinstance(reps, str) and (m := re.fullmatch(r"\s*(\d+)\s*[-–]\s*(\d+)\s*", reps)):
        s["reps"], s["rep_range"] = None, {"start": int(m[1]), "end": int(m[2])}
    elif reps:
        try:
            s["reps"] = int(reps)
        except (TypeError, ValueError):
            raise ValueError(f"reps {reps!r} must be a number or a range like 8-12 (Hevy has no AMRAP target; "
                             "put it in `note`)") from None
    if p.get("duration_sec"):
        s["duration_seconds"] = int(p["duration_sec"])
    return {k: v for k, v in s.items() if v is not None}


def build_routine(session: dict, title: str, week: int, folder_id: int | None, notes: str,
                  prescription, resolve=None) -> dict:
    """Block strength session -> Hevy routine payload. `prescription(item, week)` applies the week's
    overrides. Each exercise needs `hevy: {template_id}` in the yml; without one it is looked up by
    name and accepted only on one exact match. ValueError names what is missing, with candidates."""
    resolve = resolve or resolve_template
    exercises, missing = [], []
    for e in session.get("exercises", []):
        p = prescription(e, week)
        name = p.get("name") or str(p.get("exercise", "")).replace("_", " ")
        tid = (p.get("hevy") or {}).get("template_id")
        if not tid:
            tid, cands = resolve(name)
            if not tid:
                missing.append({"exercise": name, "candidates": [f"{c['id']} {c['title']}" for c in cands]})
                continue
        note = " · ".join(x for x in (f"target RPE {p['rpe']:g}" if p.get("rpe") else None, p.get("note")) if x)
        n_sets = int(p.get("sets") or 1)
        ex = {"exercise_template_id": tid, "sets": [_set(p) for _ in range(n_sets)]}
        if p.get("rest_sec"):
            ex["rest_seconds"] = int(p["rest_sec"])
        if note:
            ex["notes"] = note
        if p.get("superset") is not None:
            ex["superset_id"] = int(p["superset"])
        exercises.append(ex)
    if missing:
        raise ValueError("no Hevy exercise chosen for: " + "; ".join(
            f"{m['exercise']} (candidates: {', '.join(m['candidates']) or 'none found'})" for m in missing)
            + ". Pick one and write `hevy: {template_id: ...}` on that exercise in the block yml.")
    if not exercises:
        raise ValueError("strength session has no exercises")
    return {"routine": {"title": title, "folder_id": folder_id, "notes": notes, "exercises": exercises}}


def _flat(sets: list[dict]) -> list[tuple]:
    out = []
    for s in sets:
        rr = s.get("rep_range") or {}
        out.append((s.get("type") or "normal",
                    round(float(s["weight_kg"]), 2) if s.get("weight_kg") is not None else None,
                    int(s["reps"]) if s.get("reps") is not None else None,
                    (rr.get("start"), rr.get("end")) if rr and rr.get("start") is not None else None,
                    int(s["duration_seconds"]) if s.get("duration_seconds") else None))
    return out


def verify(built: dict, stored: dict) -> list[str]:
    """Compare what we sent with what Hevy stored (exercise order, template ids, every set)."""
    a, b = built["routine"].get("exercises") or [], (stored.get("routine") or stored).get("exercises") or []
    diffs = []
    if len(a) != len(b):
        diffs.append(f"exercise count planned {len(a)} got {len(b)}")
    for i, (x, y) in enumerate(zip(a, b), 1):
        if x["exercise_template_id"] != y.get("exercise_template_id"):
            diffs.append(f"exercise {i}: planned {x['exercise_template_id']} got {y.get('exercise_template_id')}")
        elif _flat(x["sets"]) != _flat(y.get("sets") or []):
            diffs.append(f"exercise {i} ({y.get('title')}): sets planned {_flat(x['sets'])} got {_flat(y.get('sets') or [])}")
    return diffs[:10]


# ---------------------------------------------------------------- routines and folders

def find_folder(title: str, create: bool = True) -> int | None:
    for f in _paged("/v1/routine_folders", "routine_folders", 10):
        if (f.get("title") or "").strip().lower() == title.strip().lower():
            return int(f["id"])
    if not create:
        return None
    r = client().request("POST", "/v1/routine_folders", body={"routine_folder": {"title": title}})
    return int((r.get("routine_folder") or r)["id"])


def create_routine(payload: dict) -> dict:
    r = client().request("POST", "/v1/routines", body=payload)
    rt = r.get("routine") or r
    rt = rt[0] if isinstance(rt, list) and rt else rt
    return rt


def update_routine(routine_id: str, payload: dict) -> dict | None:
    """PUT in place. None when the routine no longer exists (the athlete deleted it)."""
    try:
        r = client().request("PUT", f"/v1/routines/{routine_id}", body=payload)
    except HevyError as e:
        if "HTTP 404" in str(e):
            return None
        raise
    return r.get("routine") or r


def get_routine(routine_id: str) -> dict:
    r = client().request("GET", f"/v1/routines/{routine_id}")
    rt = r.get("routine") or r
    return rt[0] if isinstance(rt, list) and rt else rt


# ---------------------------------------------------------------- one-time login helper

def auth_main() -> None:
    """`coach-hevy-auth`: ask for the API key without echoing it, check it, save it owner-only."""
    print("Hevy API key (Hevy Pro): create one at https://hevy.com/settings?developer")
    key = getpass.getpass("Paste the key (nothing shows as you type) and press Enter: ").strip()
    if not key:
        sys.exit("No key entered.")
    try:
        info = Client(key).request("GET", "/v1/user/info")
    except HevyError as e:
        sys.exit(f"That key didn't work: {e}")
    u = info.get("data") or info
    p = key_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(key + "\n")
    p.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"Connected as {u.get('username') or u.get('name') or 'your Hevy account'}"
          f"{'' if u.get('is_pro') else ' (warning: this account is not Hevy Pro, so the API may refuse writes)'}."
          f"\nKey saved to {p} (readable only by you).")
