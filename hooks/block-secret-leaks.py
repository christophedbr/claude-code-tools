#!/usr/bin/env python3
"""
PreToolUse hook for Bash.

Blocks Bash commands that would dump secret values into the conversation
transcript. The transcript persists to disk and is read by future sessions,
so any secret printed becomes a long-term leak.

Strategy: deny-list the most common leak vectors. Refuses the call and
returns a helpful "use this safer form instead" message so the model can
auto-correct.

Patterns blocked:
- `infisical secrets` (list) without a name-stripping pipeline
- `infisical secrets get` without redirecting / consuming directly
- `vercel env pull` to stdout (rare but possible)
- `aws ssm get-parameter --with-decryption` printed
- Direct `cat` of common secret files

Pass-through: any of those forms with a stripping pipeline (awk/jq/grep)
or with `--json | jq 'keys'` etc. are allowed.
"""
import json
import re
import sys

# Each rule: regex of a bad command + suggestion for safer form.
# A command is BLOCKED only if it matches `bad` AND does NOT match `safe`.
RULES = [
    {
        "name": "infisical-secrets-list",
        "bad": r"\binfisical\s+secrets(?!\s+(set|get|delete))\b",
        "safe": r"(\|\s*(awk|jq|grep|cut|sed|head|tail))|--json",
        "reason": (
            "`infisical secrets` (list) prints every secret value in plain text. "
            "That output lands in the session transcript. Use one of:\n"
            "  infisical secrets --json | jq 'keys'\n"
            "  infisical secrets 2>&1 | awk -F '│' 'NR>3 && $2~/[A-Z]/{print $2}'\n"
            "  infisical run --projectId=... --env=... -- <consumer-command>"
        ),
    },
    {
        "name": "infisical-secrets-get",
        "bad": r"\binfisical\s+secrets\s+get\b",
        # Allowed if value goes to /dev/null, into an env var via $(...) chained
        # to a consumer, or piped into another command.
        "safe": r"(>\s*/dev/null|2>/dev/null\s*\||\s*\|\s*(awk|grep|sed|cut)|--plain.*\|)",
        "reason": (
            "`infisical secrets get NAME` prints the value to stdout. "
            "Use one of:\n"
            "  infisical run -- bash -c 'consumer \"$NAME\"'\n"
            "  VAL=$(infisical secrets get NAME --plain) && consume \"$VAL\"\n"
            "  infisical secrets get NAME --plain | <pipe-consumer>"
        ),
    },
    {
        "name": "vercel-env-pull-stdout",
        "bad": r"\bvercel\s+env\s+pull\b(?!.*\.env)",
        "safe": r"\.env",  # writing to a file is fine
        "reason": (
            "`vercel env pull` without a target file dumps to stdout. "
            "Use `vercel env pull .env.local` and inspect the file."
        ),
    },
    {
        "name": "cat-secret-file",
        "bad": r"\bcat\s+(\S*\.env(\.\w+)?|.*credentials\.json|.*sa-key\.json|~/\.aws/credentials)\b",
        "safe": r"(\|\s*(awk|grep|cut|sed|head|wc)|>\s*/dev/null)",
        "reason": (
            "Reading a secret-bearing file with `cat` dumps every value into the "
            "transcript. Use `awk -F= '{print $1}'` to list keys only, or use "
            "`grep -c` to count lines, or `head -1` to inspect format."
        ),
    },
    {
        "name": "aws-ssm-with-decryption",
        "bad": r"\baws\s+ssm\s+get-parameter[s]?\b.*--with-decryption\b",
        "safe": r"(\|\s*(jq|awk|grep)|\.Value\b)",
        "reason": (
            "`aws ssm get-parameter --with-decryption` prints the plaintext "
            "secret. Use `--query Parameter.Value --output text | <consumer>` "
            "to pipe it directly into the consumer."
        ),
    },
]


def evaluate(cmd: str):
    for rule in RULES:
        if re.search(rule["bad"], cmd) and not re.search(rule["safe"], cmd):
            return rule
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    cmd = data.get("tool_input", {}).get("command", "")
    rule = evaluate(cmd)
    if rule is None:
        sys.exit(0)

    # Deny the tool call with a helpful reason.
    response = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"BLOCKED by secret-leak guard ({rule['name']}).\n"
                f"{rule['reason']}\n\n"
                "If you genuinely need the leaky form (e.g. for one-off "
                "debugging), bypass by adding ` # OK-LEAK` to the end of the "
                "command — the operator has acknowledged the risk."
            ),
        }
    }

    # OK-LEAK escape hatch: explicit operator acknowledgement
    if "# OK-LEAK" in cmd or "#OK-LEAK" in cmd:
        sys.exit(0)

    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
