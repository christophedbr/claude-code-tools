#!/usr/bin/env python3
"""
PostToolUse hook for Edit/Write tools.
Tracks which projects are being worked on based on file paths.
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Debug logging
DEBUG_LOG = Path.home() / '.claude' / 'hooks-debug.log'

def log_debug(msg):
    with open(DEBUG_LOG, 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] on-file-edit: {msg}\n")

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from session_state import track_project

def main():
    try:
        input_data = json.load(sys.stdin)
        log_debug(f"Received input: {json.dumps(input_data)[:500]}")

        # Extract file_path from tool_input
        tool_input = input_data.get('tool_input', {})
        file_path = tool_input.get('file_path', '')
        log_debug(f"File path: {file_path}")

        if file_path and os.path.isabs(file_path):
            # Skip files in home .claude directory
            if '/.claude/' not in file_path:
                track_project(file_path, event_type="edit")

    except Exception:
        pass

    sys.exit(0)

if __name__ == '__main__':
    main()
