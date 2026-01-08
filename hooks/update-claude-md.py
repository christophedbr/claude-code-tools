#!/usr/bin/env python3
"""
Updates CLAUDE.md with session context.
Maintains a living document with:
- Current and archived tech stack
- Current and archived architecture decisions
- Task progress
- Session history (FIFO, max 5)
"""
import json
import sys
import os
import subprocess
import re
import argparse
from datetime import datetime
from pathlib import Path

# Configuration
MAX_SESSION_HISTORY = 5
MAX_ARCHIVED_ITEMS = 10
SIGNIFICANT_COMMIT_PATTERNS = ['feat:', 'breaking:', 'migrate', 'refactor:', 'BREAKING', 'fix:']

def notify(title, message):
    """Send macOS notification"""
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    try:
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=5)
    except Exception:
        pass

def run_git_command(project_root, args):
    """Run a git command and return output"""
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""

def detect_tech_stack(project_root):
    """Detect tech stack from project files"""
    stack = {}
    project_root = Path(project_root)

    # Check package.json for JS/TS projects
    pkg_paths = [
        project_root / 'package.json',
        project_root / 'app' / 'package.json',
        project_root / 'frontend' / 'package.json',
        project_root / 'backend' / 'package.json',
        project_root / 'web' / 'package.json',
        project_root / 'client' / 'package.json',
    ]

    for pkg_path in pkg_paths:
        if pkg_path.exists():
            try:
                pkg = json.loads(pkg_path.read_text())
                deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}

                # Frontend frameworks
                if 'next' in deps:
                    version = deps.get('next', '').lstrip('^~')
                    stack['Frontend'] = f"Next.js {version.split('.')[0]}" if version else "Next.js"
                elif 'react' in deps and 'Frontend' not in stack:
                    stack['Frontend'] = "React"
                elif 'vue' in deps:
                    stack['Frontend'] = "Vue.js"
                elif 'svelte' in deps:
                    stack['Frontend'] = "Svelte"

                # Styling
                if 'tailwindcss' in deps:
                    stack['Styling'] = "Tailwind CSS"
                elif 'styled-components' in deps:
                    stack['Styling'] = "Styled Components"

                # Database/Backend
                if '@supabase/supabase-js' in deps:
                    stack['Database'] = "Supabase (PostgreSQL)"
                if 'prisma' in deps or '@prisma/client' in deps:
                    stack['ORM'] = "Prisma"
                if 'firebase' in deps or 'firebase-admin' in deps:
                    stack['Backend'] = "Firebase"
                if 'mongoose' in deps:
                    stack['Database'] = "MongoDB"
                if 'express' in deps:
                    stack['API'] = "Express.js"

                # TypeScript
                if 'typescript' in deps:
                    stack['Language'] = "TypeScript"

                # Testing
                if 'jest' in deps:
                    stack['Testing'] = "Jest"
                elif 'vitest' in deps:
                    stack['Testing'] = "Vitest"

            except Exception:
                pass

    # Python projects
    if (project_root / 'requirements.txt').exists():
        stack.setdefault('Language', 'Python')
    if (project_root / 'pyproject.toml').exists():
        stack.setdefault('Language', 'Python')

    # Deployment
    if (project_root / 'vercel.json').exists():
        stack['Deployment'] = "Vercel"
    elif (project_root / 'netlify.toml').exists():
        stack['Deployment'] = "Netlify"
    elif (project_root / 'fly.toml').exists():
        stack['Deployment'] = "Fly.io"
    elif (project_root / 'Dockerfile').exists():
        stack['Deployment'] = "Docker"

    return stack

def get_recent_commits(project_root):
    """Get recent commits from today"""
    output = run_git_command(project_root, [
        'log', '--oneline', '--since=midnight', '-n', '10', '--format=%h|%s'
    ])
    if not output:
        return []

    commits = []
    for line in output.split('\n'):
        if '|' in line:
            hash_id, message = line.split('|', 1)
            commits.append({'hash': hash_id, 'message': message})
    return commits

def get_significant_commits(project_root):
    """Get significant commits for architecture decisions"""
    output = run_git_command(project_root, [
        'log', '--oneline', '-n', '30', '--format=%h|%s|%as', '--since=30 days ago'
    ])
    if not output:
        return []

    significant = []
    for line in output.split('\n'):
        parts = line.split('|')
        if len(parts) >= 3:
            hash_id, message, date = parts[0], parts[1], parts[2]
            if any(pattern.lower() in message.lower() for pattern in SIGNIFICANT_COMMIT_PATTERNS):
                significant.append({
                    'hash': hash_id,
                    'message': message,
                    'date': date
                })
    return significant[:10]

def parse_existing_claude_md(claude_md_path):
    """Parse existing CLAUDE.md to extract all sections"""
    sections = {
        'quick_context': '',
        'current_tech_stack': {},
        'archived_tech': [],
        'current_architecture': [],
        'archived_architecture': [],
        'task_progress': [],
        'session_history': [],
        'notes': ''
    }

    if not claude_md_path.exists():
        return sections

    content = claude_md_path.read_text()

    # Extract Quick Context
    ctx_match = re.search(r'## Quick Context\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
    if ctx_match:
        sections['quick_context'] = ctx_match.group(1).strip()

    # Extract Current Tech Stack table
    tech_match = re.search(r'## Current Tech Stack\n\|[^\n]+\n\|[-\s|]+\n((?:\|[^\n]+\n)*)', content)
    if tech_match:
        for line in tech_match.group(1).strip().split('\n'):
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 3 and parts[0] != '-':
                sections['current_tech_stack'][parts[0]] = {
                    'tech': parts[1],
                    'since': parts[2],
                    'notes': parts[3] if len(parts) > 3 else ''
                }

    # Extract Archived Tech table
    arch_tech_match = re.search(r'## Archived Tech\n\|[^\n]+\n\|[-\s|]+\n((?:\|[^\n]+\n)*)', content)
    if arch_tech_match:
        for line in arch_tech_match.group(1).strip().split('\n'):
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 4 and parts[0] != '-':
                sections['archived_tech'].append({
                    'tech': parts[0],
                    'used': parts[1],
                    'retired': parts[2],
                    'reason': parts[3]
                })

    # Extract Architecture Decisions (Active)
    arch_match = re.search(r'## Architecture Decisions \(Active\)\n\|[^\n]+\n\|[-\s|]+\n((?:\|[^\n]+\n)*)', content)
    if arch_match:
        for line in arch_match.group(1).strip().split('\n'):
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 4 and parts[0] != '-':
                sections['current_architecture'].append({
                    'date': parts[0],
                    'decision': parts[1],
                    'rationale': parts[2],
                    'status': parts[3]
                })

    # Extract Architecture Decisions (Archived)
    arch_archived_match = re.search(r'## Architecture Decisions \(Archived\)\n\|[^\n]+\n\|[-\s|]+\n((?:\|[^\n]+\n)*)', content)
    if arch_archived_match:
        for line in arch_archived_match.group(1).strip().split('\n'):
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 3 and parts[0] != '-':
                sections['archived_architecture'].append({
                    'date': parts[0],
                    'decision': parts[1],
                    'outcome': parts[2]
                })

    # Extract Task Progress
    task_match = re.search(r'## Task Progress\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
    if task_match:
        task_content = task_match.group(1).strip()
        for line in task_content.split('\n'):
            line = line.strip()
            if line.startswith('- ['):
                sections['task_progress'].append(line)

    # Extract Session History
    hist_match = re.search(r'## Recent Sessions.*?\n\|[^\n]+\n\|[-\s|]+\n((?:\|[^\n]+\n)*)', content)
    if hist_match:
        for line in hist_match.group(1).strip().split('\n'):
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 3 and parts[0] != '-':
                sections['session_history'].append({
                    'date': parts[0],
                    'branch': parts[1],
                    'summary': parts[2]
                })

    # Extract Notes (stop at next section header or footer)
    notes_match = re.search(r'## Notes\n(.*?)(?=\n## |\n---|\n\*Auto-maintained|\Z)', content, re.DOTALL)
    if notes_match:
        notes_content = notes_match.group(1).strip()
        # Filter out any remnant section headers
        if not notes_content.startswith('|') and '## ' not in notes_content:
            sections['notes'] = notes_content

    return sections

def generate_session_summary(commits, files_edited=None):
    """Generate a brief summary of the session"""
    parts = []

    if commits:
        commit_types = set()
        for commit in commits:
            msg = commit.get('message', '')
            if msg.startswith('feat'):
                commit_types.add('feat')
            elif msg.startswith('fix'):
                commit_types.add('fix')
            elif msg.startswith('refactor'):
                commit_types.add('refactor')
            elif msg.startswith('docs'):
                commit_types.add('docs')
        if commit_types:
            parts.append(', '.join(sorted(commit_types)))

    if files_edited:
        parts.append(f"{len(files_edited)} files")

    return '; '.join(parts) if parts else 'Session work'

def update_claude_md(project_root, trigger_type="manual"):
    """Update or create CLAUDE.md with session info"""
    project_root = Path(project_root)
    claude_md = project_root / 'CLAUDE.md'
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")
    date_short = now.strftime("%Y-%m-%d")

    # Parse existing content
    existing = parse_existing_claude_md(claude_md)

    # Detect current tech stack
    detected_stack = detect_tech_stack(project_root)

    # Merge tech stack (preserve existing, add new)
    for layer, tech in detected_stack.items():
        if layer not in existing['current_tech_stack']:
            existing['current_tech_stack'][layer] = {
                'tech': tech,
                'since': date_short,
                'notes': ''
            }

    # Get significant commits and add to architecture decisions
    significant = get_significant_commits(project_root)
    existing_decisions = {d['decision'] for d in existing['current_architecture']}

    for commit in significant:
        msg = commit['message']
        decision = msg.split(':', 1)[-1].strip() if ':' in msg else msg
        decision = decision[:50] + '...' if len(decision) > 50 else decision

        if decision not in existing_decisions:
            rationale = "Feature" if 'feat' in msg.lower() else \
                       "Bug fix" if 'fix' in msg.lower() else \
                       "Refactor" if 'refactor' in msg.lower() else \
                       "Update"

            existing['current_architecture'].insert(0, {
                'date': commit['date'],
                'decision': decision,
                'rationale': rationale,
                'status': 'Active'
            })
            existing_decisions.add(decision)

    # Limit active architecture decisions
    existing['current_architecture'] = existing['current_architecture'][:10]

    # Get session context
    branch = run_git_command(project_root, ['branch', '--show-current']) or 'unknown'
    commits = get_recent_commits(project_root)
    summary = generate_session_summary(commits)

    # Add to session history (FIFO)
    # Check if we already have an entry for this session (same date prefix)
    date_prefix = now.strftime("%Y-%m-%d")
    existing['session_history'] = [
        s for s in existing['session_history']
        if not s['date'].startswith(date_prefix)
    ]

    existing['session_history'].insert(0, {
        'date': date_str,
        'branch': branch,
        'summary': summary
    })

    # Keep only last N sessions
    existing['session_history'] = existing['session_history'][:MAX_SESSION_HISTORY]

    # Build the document
    content = f"""# Project: {project_root.name}

> Auto-maintained by Claude Code hooks

## Quick Context

{existing['quick_context'] if existing['quick_context'] else '<!-- Brief project description for Claude to quickly understand context -->'}

## Current Tech Stack

| Layer | Technology | Since | Notes |
|-------|------------|-------|-------|
"""

    if existing['current_tech_stack']:
        for layer, info in sorted(existing['current_tech_stack'].items()):
            content += f"| {layer} | {info['tech']} | {info['since']} | {info.get('notes', '')} |\n"
    else:
        content += "| - | No tech detected | - | - |\n"

    content += """
## Archived Tech

| Technology | Used | Retired | Reason |
|------------|------|---------|--------|
"""

    if existing['archived_tech']:
        for item in existing['archived_tech'][:MAX_ARCHIVED_ITEMS]:
            content += f"| {item['tech']} | {item['used']} | {item['retired']} | {item['reason']} |\n"
    else:
        content += "| - | - | - | No archived tech yet |\n"

    content += """
## Architecture Decisions (Active)

| Date | Decision | Rationale | Status |
|------|----------|-----------|--------|
"""

    if existing['current_architecture']:
        for decision in existing['current_architecture']:
            content += f"| {decision['date']} | {decision['decision']} | {decision['rationale']} | {decision['status']} |\n"
    else:
        content += "| - | No decisions recorded | - | - |\n"

    content += """
## Architecture Decisions (Archived)

| Date | Decision | Outcome |
|------|----------|---------|
"""

    if existing['archived_architecture']:
        for decision in existing['archived_architecture'][:MAX_ARCHIVED_ITEMS]:
            content += f"| {decision['date']} | {decision['decision']} | {decision['outcome']} |\n"
    else:
        content += "| - | No archived decisions | - |\n"

    content += """
## Task Progress

"""

    if existing['task_progress']:
        for task in existing['task_progress']:
            content += f"{task}\n"
    else:
        content += "<!-- Track ongoing tasks here -->\n- [ ] Example task\n"

    content += f"""
## Recent Sessions (Last {MAX_SESSION_HISTORY})

| Date | Branch | Summary |
|------|--------|---------|
"""

    for session in existing['session_history']:
        content += f"| {session['date']} | {session['branch']} | {session['summary']} |\n"

    content += """
## Notes

"""
    content += existing['notes'] if existing['notes'] else "<!-- Manual notes preserved across updates -->"

    content += """

---

*Auto-maintained by Claude Code hooks*
"""

    claude_md.write_text(content)
    return str(claude_md)

def main():
    parser = argparse.ArgumentParser(description='Update CLAUDE.md')
    parser.add_argument('--project', required=True, help='Project root path')
    parser.add_argument('--trigger', default='manual', help='What triggered this update')
    parser.add_argument('--notify', action='store_true', help='Send notification')

    args = parser.parse_args()

    project_root = Path(args.project)
    if not project_root.exists():
        sys.exit(1)

    # Skip home directory
    if project_root == Path.home():
        sys.exit(0)

    # Skip non-git directories
    if not (project_root / '.git').exists():
        sys.exit(0)

    file_path = update_claude_md(project_root, args.trigger)

    if args.notify:
        notify("CLAUDE.md Updated", f"{project_root.name} ({args.trigger})")

    sys.exit(0)

if __name__ == '__main__':
    main()
