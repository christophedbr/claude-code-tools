#!/usr/bin/env python3
"""
PreToolUse + Stop hook: make the main session actually call advisor().

The advisor is a server tool, so no hook fires for it; its calls show up in
the transcript as {"type": "server_tool_use", "name": "advisor"}. This hook
reads the transcript and gates on three rules:

1. First edit of a turn (Edit/Write/NotebookEdit, PreToolUse): denied unless
   advisor was called since the user's last message.
2. Finishing a turn that edited files (Stop): blocked unless advisor was
   called after the last edit.
3. Stuck (any PreToolUse): denied when 3+ tool calls have failed this turn
   since the last advisor call, or when the user's message says the last attempt did
   not work ("still broken", "same error", "marche pas", ...) and advisor has
   not been called since.

Exempt: subagents, scratchpad/tmp and memory files, non-Anthropic endpoints
(DeepSeek children have no advisor). Safety valve: after 2 denials in one turn
with no advisor call, the gate assumes advisor is unavailable and lets the
turn through (denials are counted in a per-session state file under the
system temp dir, since the denial text's place in the transcript is unverified). Kill switch: ADVISOR_GATE=off.
"""
import json
import os
import re
import sys
import tempfile

MARKER = "[advisor-gate]"
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
ERROR_THRESHOLD = 3
MAX_DENIALS_PER_TURN = 2
EXEMPT_PATH = re.compile(r"^(/private)?/tmp/|/\.claude/projects/[^/]+/memory/")
STUCK = re.compile(
    r"\bsame (error|issue|problem|bug|thing)\b"
    r"|\bstill (broken|failing|fails|not|there|happening|the same|wrong|erroring)\b"
    r"|\b(doesn'?t|does not|didn'?t|did not|isn'?t|is not|won'?t) (work|fix|help|change)"
    r"|\bnot (fixed|working)\b"
    r"|\b(marche|fonctionne) (toujours )?pas\b"
    r"|\btoujours (pas|le m[eê]me|la m[eê]me|cass[eé])\b",
    re.I,
)


def load(path):
    entries = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return entries


def blocks(entry):
    content = (entry.get("message") or {}).get("content")
    return content if isinstance(content, list) else []


def is_human(entry):
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    origin = entry.get("origin") or {}
    if origin:
        return origin.get("kind") == "human"
    content = (entry.get("message") or {}).get("content")
    return isinstance(content, str) or not any(b.get("type") == "tool_result" for b in blocks(entry))


def prompt_text(entry):
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in blocks(entry) if b.get("type") == "text")


def is_advisor(block):
    return block.get("type") == "server_tool_use" and block.get("name") == "advisor"


def is_edit(block):
    if block.get("type") != "tool_use" or block.get("name") not in EDIT_TOOLS:
        return False
    inp = block.get("input") or {}
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    return not EXEMPT_PATH.search(path)


def result_text(block):
    content = block.get("content")
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return str(content or "")


def is_failure(block):
    if block.get("type") != "tool_result" or not block.get("is_error"):
        return False
    text = result_text(block)
    return MARKER not in text and "doesn't want to proceed" not in text


def is_gate_denial(block):
    return block.get("type") == "tool_result" and MARKER in result_text(block)


def analyse(entries):
    """Flatten the transcript into what the rules need."""
    last_human = -1
    for i, e in enumerate(entries):
        if is_human(e):
            last_human = i
    turn = entries[last_human + 1:] if last_human >= 0 else entries
    last_prompt = prompt_text(entries[last_human]) if last_human >= 0 else ""

    advisor_this_turn = False
    edits_after_advisor = False
    denials_this_turn = 0
    for e in turn:
        for b in blocks(e):
            if is_advisor(b):
                advisor_this_turn = True
                edits_after_advisor = False
            elif is_edit(b):
                edits_after_advisor = True
            elif is_gate_denial(b):
                denials_this_turn += 1

    # Failures only count within this turn: a no-match grep hours ago is not
    # "stuck". Across turns, the STUCK prompt regex and the per-turn edit rule
    # cover the back-and-forth case.
    failures_since_advisor = 0
    for e in reversed(turn):
        bs = blocks(e)
        if any(is_advisor(b) for b in bs):
            break
        failures_since_advisor += sum(1 for b in bs if is_failure(b))

    return {
        "advisor_this_turn": advisor_this_turn,
        "edits_after_advisor": edits_after_advisor,
        "denials_this_turn": denials_this_turn,
        "failures_since_advisor": failures_since_advisor,
        "stuck_prompt": bool(STUCK.search(last_prompt)),
        "turn_key": str(entries[last_human].get("uuid") or last_human) if last_human >= 0 else "none",
    }


def pre_tool_reason(tool, s, exempt_edit=False):
    if s["advisor_this_turn"] and s["failures_since_advisor"] < ERROR_THRESHOLD:
        return None
    if s["failures_since_advisor"] >= ERROR_THRESHOLD:
        return (f"{s['failures_since_advisor']} tool calls have failed since the last advisor call. "
                "You look stuck: call advisor() now, before trying another fix.")
    if s["stuck_prompt"]:
        return ("The user says the previous attempt did not work. Call advisor() before your next "
                "action instead of trying another quick fix.")
    if tool in EDIT_TOOLS and not exempt_edit:
        return "First edit of this turn: call advisor() before writing, then retry this edit."
    return None


def state_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "unknown")
    return os.path.join(tempfile.gettempdir(), "advisor-gate", f"{safe}.json")


def state_denials(session_id, turn_key):
    try:
        with open(state_path(session_id)) as f:
            st = json.load(f)
        return st.get("denials", 0) if st.get("turn") == turn_key else 0
    except (OSError, ValueError):
        return 0


def record_denial(session_id, turn_key):
    path = state_path(session_id)
    count = state_denials(session_id, turn_key) + 1  # read before "w" truncates the file
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"turn": turn_key, "denials": count}, f)
    except OSError:
        pass


def main():
    if os.environ.get("ADVISOR_GATE", "").lower() == "off":
        return
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    if base_url and "anthropic.com" not in base_url:
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    if data.get("agent_id") or "/subagents/" in data.get("transcript_path", ""):
        return

    event = data.get("hook_event_name")
    session_id = data.get("session_id", "")
    s = analyse(load(data.get("transcript_path", "")))
    denials = max(s["denials_this_turn"], state_denials(session_id, s["turn_key"]))
    if denials >= MAX_DENIALS_PER_TURN and not s["advisor_this_turn"]:
        return

    if event == "PreToolUse":
        tool = data.get("tool_name", "")
        inp = data.get("tool_input") or {}
        exempt_edit = tool in EDIT_TOOLS and bool(
            EXEMPT_PATH.search(inp.get("file_path") or inp.get("notebook_path") or ""))
        reason = pre_tool_reason(tool, s, exempt_edit)
        if reason:
            record_denial(session_id, s["turn_key"])
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"{MARKER} {reason}",
            }}))
    elif event == "Stop":
        if data.get("stop_hook_active"):
            return
        if s["edits_after_advisor"]:
            print(json.dumps({
                "decision": "block",
                "reason": f"{MARKER} You edited files this turn and have not called advisor() since "
                          "the last edit. Call it now, act on what it says, then finish.",
            }))


if __name__ == "__main__":
    main()
