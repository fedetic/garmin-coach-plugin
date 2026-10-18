"""Weekly upstream check for the two Garmin dependencies that are pinned on purpose.

- Taxuspt/garmin_mcp: pinned to a reviewed commit (its login tool sees the user's
  password, its server holds a full-access token). New commits -> compare link,
  commit list, and an automated scan of the added code for the things that matter.
- garminconnect on PyPI: pinned in server/pyproject.toml (and by garmin_mcp itself).

Prints a markdown issue body to stdout, or nothing when everything is current.
Exit code 0 either way; network errors fail loudly. Stdlib only.

    python .github/scripts/check_upstream.py            # uses GITHUB_TOKEN if set
    PIN_OVERRIDE=<sha> python .github/scripts/...       # pretend an older pin (testing)
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = "Taxuspt/garmin_mcp"
URL = f"git+https://github.com/{REPO}@"
# every file that runs the pinned commit; they must all agree
PIN_FILES = [".mcp.json", "server/coach_mcp/codex.py", "scripts/setup.sh", "scripts/setup.ps1",
             "server/coach_mcp/garmin_live.py", "skills/coach-core/references/garmin-data.md", "README.md"]
OK_HOSTS = {"connect.garmin.com", "connectapi.garmin.com", "sso.garmin.com", "connect.garmin.cn",
            "github.com", "www.topografix.com"}
RISKY = [
    (r"\bsubprocess\b|os\.system|os\.popen|\bpty\b", "runs shell commands"),
    (r"\beval\(|\bexec\(|__import__\(|importlib\.import_module", "evaluates or imports code dynamically"),
    (r"\bsocket\.|urllib\.request|http\.client|\bhttpx\b|requests\.(get|post|put|patch|request)",
     "makes network calls outside the Garmin client"),
    (r"\bpickle\b|\bmarshal\b", "deserializes pickled data"),
    (r"chmod|0o6[0-7][0-7]|0o7[0-7][0-7]", "changes file permissions"),
    (r"token|password|GARMINTOKENS", "touches tokens or the password"),
]


def get(url: str, raw: bool = False):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "garmin-coach-upstream-check"})
    if os.environ.get("GITHUB_TOKEN") and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    return body if raw else json.loads(body)


def pins() -> dict[str, set[str]]:
    found = {}
    for f in PIN_FILES:
        found[f] = set(re.findall(re.escape(URL) + r"([0-9a-f]{40})", (ROOT / f).read_text()))
        if f == "server/coach_mcp/codex.py":  # GARMIN_MCP = f"{GARMIN_MCP_REPO}@<sha>"
            found[f] |= set(re.findall(r'GARMIN_MCP = f"\{GARMIN_MCP_REPO\}@([0-9a-f]{40})"', (ROOT / f).read_text()))
    return found


def scan(files: list[dict]) -> list[str]:
    """Added code lines (comments skipped) that match a risk, grouped per file: count + one example."""
    hits: dict[tuple[str, str], list[str]] = {}
    notes = []
    for f in files:
        name = f["filename"]
        if not name.endswith((".py", ".toml", ".sh", ".cfg", ".txt")) or name.startswith("tests/"):
            continue
        if "patch" not in f:
            notes.append(f"`{name}`: diff too large for the API, review it in full")
            continue
        added = [ln[1:].strip() for ln in f["patch"].splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        if name in ("pyproject.toml", "uv.lock"):
            if added:
                notes.append(f"`{name}`: dependencies changed ({len(added)} added lines), check versions and new packages")
            continue
        for ln in added:
            if not ln or ln.startswith("#"):
                continue
            for host in re.findall(r"https?://([a-zA-Z0-9.{}_-]+)", ln):
                if "{" in host or host.endswith("."):
                    hits.setdefault((name, "builds a URL host at runtime"), []).append(ln)
                elif host not in OK_HOSTS:
                    hits.setdefault((name, f"new host `{host}`"), []).append(ln)
            for pat, why in RISKY:
                if re.search(pat, ln):
                    hits.setdefault((name, why), []).append(ln)
    return notes + [f"`{name}`: {why} ({len(lns)} line{'s' if len(lns) > 1 else ''}), e.g. `{lns[0][:110]}`"
                    for (name, why), lns in sorted(hits.items())]


def main() -> None:
    found = pins()
    shas = set().union(*found.values())
    sections = []
    if len(shas) != 1 or not all(found.values()):
        sections.append("## Pins disagree\n\nEvery file should pin the same commit:\n\n"
                        + "\n".join(f"- `{f}`: {', '.join(s)[:12] if s else 'MISSING'}" for f, s in found.items()))
    pinned = os.environ.get("PIN_OVERRIDE") or (next(iter(shas)) if len(shas) == 1 else sorted(shas)[0])

    head = get(f"https://api.github.com/repos/{REPO}/commits/HEAD")["sha"]
    if head != pinned:
        cmp = get(f"https://api.github.com/repos/{REPO}/compare/{pinned}...{head}")
        commits = cmp.get("commits") or []
        lines = [f"- [`{c['sha'][:7]}`]({c['html_url']}) {c['commit']['message'].splitlines()[0][:100]} "
                 f"({c['commit']['author']['date'][:10]})" for c in commits[-30:]]
        flags = scan(cmp.get("files") or [])
        sections.append(
            f"## {REPO}: {cmp.get('ahead_by', len(commits))} new commit(s)\n\n"
            f"Pinned `{pinned[:7]}`, upstream `{head[:7]}`. "
            f"[Full diff](https://github.com/{REPO}/compare/{pinned}...{head})\n\n"
            + ("\n".join(lines) or "_no commit list returned_") + "\n\n"
            "### Automated scan of added lines\n\n"
            + ("\n".join(f"- {x}" for x in flags) if flags else "Nothing flagged.")
            + "\n\nThe scan is a pointer, not a review: read the diff before bumping.")

    # garminconnect: alert when garmin_mcp moves its own pin (upstream validated a new version),
    # not on every PyPI release - an issue that can't be acted on stays open and gets ignored.
    pin_re = r'garminconnect==([0-9][^"\s,]*)'
    m = re.search(pin_re, (ROOT / "server/pyproject.toml").read_text())
    ours = m.group(1) if m else None
    m = re.search(pin_re, get(f"https://raw.githubusercontent.com/{REPO}/{head}/pyproject.toml", raw=True))
    theirs = m.group(1) if m else None
    if ours and theirs and theirs != ours:
        latest = get("https://pypi.org/pypi/garminconnect/json")["info"]["version"]
        sections.append(
            f"## garminconnect: garmin_mcp now pins {theirs}, we pin {ours}\n\n"
            f"Latest on PyPI: {latest} ([releases](https://github.com/cyberjunky/python-garminconnect/releases)). "
            f"Move `server/pyproject.toml` to `garminconnect=={theirs}` with the garmin_mcp bump, `uv lock`, "
            f"and re-run the live checks (daily snapshot, weekly sync, a test push): the coach server "
            f"parses raw Garmin responses through this library.")

    if not sections:
        return
    print("Automated weekly check: something we pin on purpose has a newer version.\n\n"
          + "\n\n".join(sections)
          + "\n\n## To bump\n\n"
          "- [ ] Read the diff: hosts contacted, shell/eval, token and password handling, file permissions, new dependencies\n"
          "- [ ] Update the commit in every pinned file (`.mcp.json`, `codex.py`, `setup.sh`, `setup.ps1`, "
          "`garmin_live.py`, `garmin-data.md`, `README.md`) and the sha/date in the README security section\n"
          "- [ ] `uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp@<new> garmin-mcp` starts and logs in\n"
          "- [ ] Tests pass (`cd server && uv run --with pytest pytest -q`)\n\n"
          "This issue is updated in place by `.github/workflows/upstream-check.yml`; close it after bumping.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # make failures visible in the Actions log
        print(f"upstream check failed: {e}", file=sys.stderr)
        sys.exit(1)
