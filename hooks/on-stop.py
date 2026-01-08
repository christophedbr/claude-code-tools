#!/usr/bin/env python3
"""
Stop hook - runs when Claude Code session ends.
Updates all tracked projects' CLAUDE.md files and cleans up session state.
"""
import json
import sys
import os
import subprocess

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from session_state import load_state, clear_state, get_all_tracked_projects

def notify(title, message):
    """Send macOS notification"""
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    try:
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=5)
    except Exception:
        pass

def update_project(project_root):
    """Update a single project's CLAUDE.md"""
    try:
        update_script = os.path.join(os.path.dirname(__file__), 'update-claude-md.py')
        if os.path.exists(update_script):
            result = subprocess.run(
                ['python3', update_script, '--project', str(project_root), '--trigger', 'session-end'],
                capture_output=True,
                timeout=15
            )
            return result.returncode == 0
    except Exception:
        pass
    return False

def main():
    try:
        # Read input (required for hooks)
        json.load(sys.stdin)

        # Get all tracked projects
        projects = get_all_tracked_projects()

        if not projects:
            sys.exit(0)

        # Update each project
        updated = []
        for project in projects:
            if update_project(project):
                # Extract just the project name for notification
                project_name = os.path.basename(project)
                updated.append(project_name)

        # Send single notification for all updates
        if updated:
            if len(updated) == 1:
                notify("CLAUDE.md Updated", f"Session saved: {updated[0]}")
            else:
                notify("CLAUDE.md Updated", f"Session saved: {len(updated)} projects")

        # Clear session state
        clear_state()

    except Exception:
        pass

    sys.exit(0)

if __name__ == '__main__':
    main()
