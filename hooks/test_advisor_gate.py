import json, os, subprocess, sys, tempfile
H = "/Users/branchuchristophe/Documents/GitHub/claude-code-tools/hooks/advisor-gate.py"


def human(text):
    return {"type": "user", "origin": {"kind": "human"}, "message": {"role": "user", "content": text}}

def advisor():
    return {"type": "assistant", "message": {"content": [{"type": "server_tool_use", "id": "s1", "name": "advisor", "input": {}}]}}

def edit(path="/repo/a.py"):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": path}}]}}

def bash():
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "x"}}]}}

def result(error=False, text="ok"):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "is_error": error, "content": text}]}}

def denial():
    return result(True, "[advisor-gate] First edit of this turn: call advisor()")

FAIL = [bash(), result(True, "Exit code 1")]

CASES = [
    # (should_block, label, event, extra, transcript)
    (True,  "first edit, no advisor",         "PreToolUse", {"tool_name": "Edit", "tool_input": {"file_path": "/repo/a.py"}}, [human("fix the bug")]),
    (False, "first edit after advisor",       "PreToolUse", {"tool_name": "Edit", "tool_input": {"file_path": "/repo/a.py"}}, [human("fix the bug"), advisor()]),
    (True,  "advisor was last turn only",     "PreToolUse", {"tool_name": "Write", "tool_input": {"file_path": "/repo/a.py"}}, [human("a"), advisor(), human("b")]),
    (False, "scratchpad edit exempt",         "PreToolUse", {"tool_name": "Write", "tool_input": {"file_path": "/private/tmp/claude-501/x/scratchpad/f.py"}}, [human("a")]),
    (False, "memory edit exempt",             "PreToolUse", {"tool_name": "Write", "tool_input": {"file_path": "/Users/u/.claude/projects/p/memory/m.md"}}, [human("a")]),
    (False, "read-only tool, calm turn",      "PreToolUse", {"tool_name": "Bash"}, [human("how much does X cost?")]),
    (True,  "3 failures since advisor",       "PreToolUse", {"tool_name": "Bash"}, [human("a"), advisor()] + FAIL * 3),
    (False, "2 failures is fine",             "PreToolUse", {"tool_name": "Bash"}, [human("a"), advisor()] + FAIL * 2),
    (False, "failures reset by advisor",      "PreToolUse", {"tool_name": "Bash"}, [human("a")] + FAIL * 3 + [advisor()]),
    (False, "failures don't cross turns",     "PreToolUse", {"tool_name": "Read"}, [human("a"), advisor()] + FAIL * 2 + [human("b"), advisor()] + FAIL * 1),
    (True,  "3 failures in one turn",         "PreToolUse", {"tool_name": "Read"}, [human("a"), advisor()] + FAIL * 2 + [human("b"), advisor()] + FAIL * 3),
    (False, "subagent transcript path",       "PreToolUse", {"tool_name": "Edit", "transcript_path_override": "/x/subagents/agent-1.jsonl", "tool_input": {"file_path": "/r/a"}}, [human("a")]),
    (True,  "stuck prompt blocks exempt edit","PreToolUse", {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.py"}}, [human("still broken")]),
    (True,  "user: still broken",             "PreToolUse", {"tool_name": "Bash"}, [human("nope, still broken")]),
    (True,  "user: marche pas (FR)",          "PreToolUse", {"tool_name": "Read"}, [human("ça marche pas")]),
    (True,  "user: same error",               "PreToolUse", {"tool_name": "Bash"}, [human("same error as before")]),
    (False, "stuck prompt after advisor",     "PreToolUse", {"tool_name": "Bash"}, [human("still broken"), advisor()]),
    (False, "neutral prompt mentioning work", "PreToolUse", {"tool_name": "Bash"}, [human("how does the work queue work?")]),
    (False, "gate denials are not failures",  "PreToolUse", {"tool_name": "Edit", "tool_input": {"file_path": "/r/a"}}, [human("a"), advisor(), denial(), denial(), denial()]),
    (False, "safety valve after 2 denials",   "PreToolUse", {"tool_name": "Edit", "tool_input": {"file_path": "/r/a"}}, [human("a"), denial(), denial()]),
    (True,  "stop: edited, no advisor",       "Stop", {}, [human("a"), edit(), result()]),
    (True,  "stop: edit after advisor",       "Stop", {}, [human("a"), advisor(), edit(), result()]),
    (False, "stop: advisor after last edit",  "Stop", {}, [human("a"), advisor(), edit(), result(), advisor()]),
    (False, "stop: no edits this turn",       "Stop", {}, [human("a"), edit(), result(), advisor(), human("question?"), bash(), result()]),
    (False, "stop: scratchpad-only edits",    "Stop", {}, [human("a"), edit("/tmp/x.py"), result()]),
    (False, "stop: stop_hook_active",         "Stop", {"stop_hook_active": True}, [human("a"), edit(), result()]),
    (False, "subagent exempt",                "PreToolUse", {"tool_name": "Edit", "agent_id": "a1", "tool_input": {"file_path": "/r/a"}}, [human("a")]),
]

fails = 0
env = {k: v for k, v in os.environ.items() if k not in ("ADVISOR_GATE", "ANTHROPIC_BASE_URL")}
for want_block, label, event, extra, transcript in CASES:
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        f.write("\n".join(json.dumps(e) for e in transcript))
    extra = dict(extra)
    tpath = extra.pop("transcript_path_override", f.name)
    payload = {"hook_event_name": event, "transcript_path": tpath, "session_id": f"test-{abs(hash(label))}", **extra}
    p = subprocess.run([sys.executable, H], input=json.dumps(payload), capture_output=True, text=True, env=env)
    os.unlink(f.name)
    blocked = '"deny"' in p.stdout or '"block"' in p.stdout
    ok = blocked == want_block and not p.stderr
    fails += not ok
    print(("PASS" if ok else "FAIL"), label, "" if ok else f"-> stdout={p.stdout!r} stderr={p.stderr[-300:]!r}")

deepseek = subprocess.run([sys.executable, H], capture_output=True, text=True,
                          input=json.dumps({"hook_event_name": "Stop", "transcript_path": "/nonexistent"}),
                          env={**env, "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic"})
print("PASS" if not deepseek.stdout else "FAIL", "non-Anthropic endpoint exempt")
fails += bool(deepseek.stdout)

# Safety valve via the state file: the hook's own denials may not be visible
# in the transcript, so two denials in one turn must let the third attempt through.
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
    f.write(json.dumps({**human("fix it"), "uuid": "u1"}))
sid = f"valve-{os.getpid()}"
outcomes = []
for _ in range(3):
    p = subprocess.run([sys.executable, H], capture_output=True, text=True, env=env, input=json.dumps(
        {"hook_event_name": "PreToolUse", "session_id": sid, "transcript_path": f.name,
         "tool_name": "Edit", "tool_input": {"file_path": "/r/a"}}))
    outcomes.append('"deny"' in p.stdout)
os.unlink(f.name)
ok = outcomes == [True, True, False]
print("PASS" if ok else "FAIL", "state-file valve opens on 3rd attempt", "" if ok else outcomes)
fails += not ok
print(f"\n{len(CASES) + 2 - fails}/{len(CASES) + 2} passed")
sys.exit(1 if fails else 0)
