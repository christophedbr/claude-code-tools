#!/usr/bin/env python3
"""
PreCompact + SessionEnd hook.

Captures session checkpoints into the life-os vault so context survives
compaction and session boundaries:

1. Appends a checkpoint stub (timestamp, event, session_id, cwd) under a
   "## Session checkpoints" section in agents/lifeos/state/current.md.
2. On SessionEnd only, appends a DRAFT lesson stub to
   agents/lifeos/learnings/lessons.md for later human/agent review —
   but only when the transcript is >50KB (skips trivial sessions).

Fast (<2s), non-blocking, fail-silent: never raises, always exits 0.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

VAULT = Path.home() / 'Documents' / 'GitHub' / 'life-os'
CURRENT_MD = VAULT / 'agents' / 'lifeos' / 'state' / 'current.md'
LESSONS_MD = VAULT / 'agents' / 'lifeos' / 'learnings' / 'lessons.md'
CHECKPOINT_HEADER = '## Session checkpoints'
TRANSCRIPT_MIN_BYTES = 50_000


def append_checkpoint(event, session_id, cwd):
    if not CURRENT_MD.exists():
        return
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"- {timestamp} | {event} | session `{session_id}` | cwd `{cwd}`\n"
    content = CURRENT_MD.read_text()
    with open(CURRENT_MD, 'a') as f:
        if CHECKPOINT_HEADER not in content:
            prefix = '' if content.endswith('\n') else '\n'
            f.write(f"{prefix}\n{CHECKPOINT_HEADER}\n\n")
        f.write(line)


def append_draft_lesson(session_id, cwd, transcript_path):
    if not LESSONS_MD.exists():
        return
    # Skip trivial sessions: only capture when the transcript is substantial.
    try:
        if os.path.getsize(transcript_path) <= TRANSCRIPT_MIN_BYTES:
            return
    except OSError:
        return
    date = datetime.now().strftime('%Y-%m-%d')
    id_prefix = str(session_id)[:8]
    stub = (
        f"\n### {date}: [DRAFT - session {id_prefix}] needs review\n\n"
        f"- TODO: review transcript and extract lessons "
        f"(session `{session_id}`, cwd `{cwd}`, transcript `{transcript_path}`)\n"
    )
    with open(LESSONS_MD, 'a') as f:
        f.write(stub)


def main():
    try:
        data = json.load(sys.stdin)
        event = data.get('hook_event_name', '')
        if event not in ('PreCompact', 'SessionEnd'):
            sys.exit(0)
        session_id = data.get('session_id', 'unknown')
        cwd = data.get('cwd', os.getcwd())
        transcript_path = data.get('transcript_path', '')

        append_checkpoint(event, session_id, cwd)
        if event == 'SessionEnd' and transcript_path:
            append_draft_lesson(session_id, cwd, transcript_path)
    except Exception:
        pass

    sys.exit(0)


if __name__ == '__main__':
    main()
