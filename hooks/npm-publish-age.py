#!/usr/bin/env python3
"""
PreToolUse hook for Bash.

Blocks installation of npm packages published/modified less than 24 hours
ago. Defense against supply-chain campaigns like "Mini Shai-Hulud"
(April-May 2026: malicious versions of @tanstack/router, @mistralai/*,
axios, etc. published with credential-stealing install scripts). A 24h
publish-age gate gives the registry time to yank compromised versions.

Strategy:
- Detect `npm install/i/add X`, `pnpm add/install/i X`, `yarn add X`,
  and `npx X` where a specific package name is given.
- Skip bare `npm install` (lockfile restore) and flags-only invocations.
- For each named package, fetch the publish time of the latest version
  (`npm view <pkg> dist-tags.latest time --json`, 5s timeout). Using the
  version publish time, NOT packument `time.modified`, avoids false
  positives from metadata-only touches (deprecations, tag moves).
- If the latest version was published < 24h ago -> DENY with explanation.
- On any error / timeout / unparseable output -> ALLOW (fail open;
  never block on registry flakiness).

Escape hatch: append ` # OK-FRESH` to the command to bypass.
"""
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone

MAX_AGE = timedelta(hours=24)
NPM_VIEW_TIMEOUT = 5  # seconds
MAX_LOOKUPS = 5  # cap registry calls per command

# Valid npm package name (optionally scoped), optionally with @version.
PKG_RE = re.compile(r"^(@[a-z0-9~._-]+/)?[a-z0-9~._-]+(@[^@\s]+)?$", re.IGNORECASE)

# Flags that consume the next token (so we don't mistake values for packages).
VALUE_FLAGS = {
    "-w", "--workspace", "--prefix", "-C", "--dir", "--registry",
    "--filter", "-F", "-p", "--package", "--loglevel", "--cwd",
}


def strip_version(spec: str) -> str:
    """`pkg@1.2.3` -> `pkg`, `@scope/pkg@^2` -> `@scope/pkg`."""
    if spec.startswith("@"):
        # scoped: version delimiter is an @ after the slash
        slash = spec.find("/")
        at = spec.find("@", slash if slash > 0 else 1)
        return spec[:at] if at > 0 else spec
    at = spec.find("@")
    return spec[:at] if at > 0 else spec


def is_package_spec(token: str) -> bool:
    """True if token looks like a registry package name (not a path/URL/tarball)."""
    if not token or token.startswith("-"):
        return False
    if token.startswith((".", "/", "~/", "file:", "git+", "git:", "github:",
                         "http:", "https:", "link:", "workspace:")):
        return False
    if token.endswith((".tgz", ".tar.gz")):
        return False
    return bool(PKG_RE.match(token))


def extract_packages(cmd: str):
    """Return the set of registry package names being installed by `cmd`."""
    packages = set()
    # Split compound commands on shell separators.
    for segment in re.split(r"(?:\|\||&&|;|\|)", cmd):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue  # unbalanced quotes etc. -> fail open on this segment
        if not tokens:
            continue
        # Skip leading env assignments (FOO=bar npm i ...).
        while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            continue
        tool = tokens[0].rsplit("/", 1)[-1]

        if tool == "npx":
            args = tokens[1:]
        elif tool in ("npm", "pnpm") and len(tokens) > 1 and tokens[1] in ("install", "i", "add"):
            args = tokens[2:]
        elif tool == "yarn" and len(tokens) > 1 and tokens[1] == "add":
            args = tokens[2:]
        else:
            continue

        skip_next = False
        for tok in args:
            if skip_next:
                skip_next = False
                continue
            if tok in VALUE_FLAGS:
                skip_next = True
                continue
            if tok.startswith("-"):
                continue
            if is_package_spec(tok):
                packages.add(strip_version(tok))
            if tool == "npx":
                break  # for npx, only the first non-flag token is the package
    return packages


def package_age(pkg: str):
    """Return (timedelta since latest version's publish, version) or None on any failure."""
    try:
        result = subprocess.run(
            ["npm", "view", pkg, "dist-tags.latest", "time", "--json"],
            capture_output=True, text=True, timeout=NPM_VIEW_TIMEOUT,
        )
        if result.returncode != 0:
            return None
        info = json.loads(result.stdout)
        latest = info.get("dist-tags.latest")
        raw = (info.get("time") or {}).get(latest) if latest else None
        if not raw:
            return None
        published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - published, latest
    except Exception:
        return None  # fail open: timeout, npm missing, bad JSON/date, etc.


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    cmd = data.get("tool_input", {}).get("command", "")

    # OK-FRESH escape hatch: explicit operator acknowledgement
    if "# OK-FRESH" in cmd or "#OK-FRESH" in cmd:
        sys.exit(0)

    # Cheap pre-filter before any parsing.
    if not re.search(r"\b(npm|pnpm|yarn|npx)\b", cmd):
        sys.exit(0)

    packages = extract_packages(cmd)
    if not packages:
        sys.exit(0)  # bare install / flags-only / nothing recognizable

    for pkg in sorted(packages)[:MAX_LOOKUPS]:
        result = package_age(pkg)
        if result is None:
            continue  # fail open on registry flakiness
        age, latest = result
        if age < MAX_AGE:
            hours = age.total_seconds() / 3600
            response = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"BLOCKED by npm publish-age guard: `{pkg}@{latest}` was published "
                        f"{hours:.1f}h ago (< 24h).\n"
                        "Per the Mini Shai-Hulud supply-chain rule (CLAUDE.md, npm/JS "
                        "supply-chain hygiene): never install a freshly-published or "
                        "freshly-bumped package without verifying it. Compromised versions "
                        "are usually yanked within 24h.\n"
                        f"Verify with: npm view {pkg} time --json\n"
                        "Options: wait 24h, pin a known-good older version, or if you have "
                        "verified the release is legitimate, bypass by adding ` # OK-FRESH` "
                        "to the end of the command."
                    ),
                }
            }
            print(json.dumps(response))
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
