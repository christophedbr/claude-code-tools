#!/usr/bin/env python3
"""
UserPromptSubmit hook.
Counts prompts and triggers periodic CLAUDE.md saves as safety net.
"""
import json
import sys
import os
import subprocess

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from session_state import increment_prompt_count, get_all_tracked_projects

def trigger_claude_md_update(project_root, trigger_type="periodic"):
    """Trigger CLAUDE.md update for a specific project"""
    try:
        update_script = os.path.join(os.path.dirname(__file__), 'update-claude-md.py')
        if os.path.exists(update_script):
            subprocess.run(
                ['python3', update_script, '--project', str(project_root), '--trigger', trigger_type],
                capture_output=True,
                timeout=10
            )
    except Exception:
        pass

def main():
    try:
        # Read input but we don't need to use it
        json.load(sys.stdin)

        # Increment counter and check if we should save
        should_save, state = increment_prompt_count()

        if should_save:
            # Update all tracked projects
            for project in get_all_tracked_projects():
                trigger_claude_md_update(project, trigger_type="periodic")

    except Exception:
        pass

    sys.exit(0)

if __name__ == '__main__':
    main()
