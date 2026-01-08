#!/usr/bin/env python3
"""
PostToolUse hook for Bash commands.
Detects git commits and triggers immediate CLAUDE.md update.
"""
import json
import sys
import os
import subprocess
import re

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from session_state import track_project, get_all_tracked_projects

def get_last_commit_info(project_root):
    """Get info about the last commit"""
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%h|%s'],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split('|', 1)
            return {
                'hash': parts[0],
                'message': parts[1] if len(parts) > 1 else ''
            }
    except Exception:
        pass
    return None

def detect_git_project_from_command(command):
    """Try to extract project path from git command"""
    # Check for -C flag (git -C /path/to/repo commit ...)
    match = re.search(r'git\s+-C\s+([^\s]+)', command)
    if match:
        return match.group(1)

    # Check for commands run with cd prefix
    match = re.search(r'cd\s+([^\s&;]+)\s*&&\s*git', command)
    if match:
        return match.group(1)

    return None

def trigger_claude_md_update(project_root):
    """Trigger CLAUDE.md update for a specific project"""
    try:
        update_script = os.path.join(os.path.dirname(__file__), 'update-claude-md.py')
        if os.path.exists(update_script):
            subprocess.run(
                ['python3', update_script, '--project', str(project_root), '--trigger', 'commit'],
                capture_output=True,
                timeout=10
            )
    except Exception:
        pass

def main():
    try:
        input_data = json.load(sys.stdin)

        tool_input = input_data.get('tool_input', {})
        command = tool_input.get('command', '')

        # Check if this is a git commit command
        if 'git commit' in command or 'git push' in command:
            # Try to find which project this commit was in
            project_path = detect_git_project_from_command(command)

            if project_path:
                commit_info = get_last_commit_info(project_path)
                if commit_info:
                    track_project(project_path, event_type="commit", commit_info=commit_info)
                    trigger_claude_md_update(project_path)
            else:
                # Check all tracked projects for new commits
                for project in get_all_tracked_projects():
                    commit_info = get_last_commit_info(project)
                    if commit_info:
                        track_project(project, event_type="commit", commit_info=commit_info)
                        trigger_claude_md_update(project)

    except Exception:
        pass

    sys.exit(0)

if __name__ == '__main__':
    main()
