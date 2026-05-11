"""Validate Skill Files — verifica che MCP tools, script e tabelle referenziati esistano.

Uso: python scripts/validate_skills.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MCP_TOOLS = {
    "get_weekly_context",
    "get_race_context",
    "get_session_review_context",
    "get_upcoming_plan",
    "get_recent_metrics",
    "get_planned_session",
    "get_activity_history",
    "query_subjective_log",
    "propose_plan_change",
    "commit_plan_change",
    "get_physiology_zones",
    "force_garmin_sync",
}

SUPABASE_TABLES = {
    "activities",
    "daily_wellness",
    "daily_metrics",
    "subjective_log",
    "planned_sessions",
    "mesocycles",
    "races",
    "physiology_zones",
    "health",
    "bot_messages",
    "pending_confirmations",
    "api_usage",
    "session_analyses",
    "plan_modulations",
}

TOOL_RE = re.compile(r"`(get_\w+|query_\w+|propose_\w+|commit_\w+|force_\w+)`")
TABLE_RE = re.compile(r"`(activities|daily_\w+|subjective_log|planned_sessions|mesocycles|races|physiology_zones|health|bot_messages|pending_confirmations|api_usage|session_analyses|plan_modulations)`")
SCRIPT_RE = re.compile(r"python\s+(?:-m\s+)?([\w.]+)")
FILE_RE = re.compile(r"`((?:docs|coach|workers|scripts)/[\w/._-]+)`")


def validate() -> list[str]:
    skills_dir = ROOT / "skills"
    if not skills_dir.exists():
        return ["skills/ directory not found"]

    errors: list[str] = []

    for skill_file in sorted(skills_dir.glob("*.md")):
        content = skill_file.read_text(encoding="utf-8")
        name = skill_file.name

        for m in TOOL_RE.finditer(content):
            tool = m.group(1)
            if tool not in MCP_TOOLS and not tool.startswith("gcal:"):
                errors.append(f"{name}: unknown MCP tool `{tool}`")

        for m in TABLE_RE.finditer(content):
            table = m.group(1)
            if table not in SUPABASE_TABLES:
                errors.append(f"{name}: unknown table `{table}`")

        for m in SCRIPT_RE.finditer(content):
            module = m.group(1)
            mod_path = ROOT / module.replace(".", os.sep)
            if not mod_path.exists() and not mod_path.with_suffix(".py").exists():
                pkg_init = mod_path / "__init__.py"
                main = mod_path / "__main__.py"
                if not pkg_init.exists() and not main.exists():
                    errors.append(f"{name}: script `{module}` not found")

        for m in FILE_RE.finditer(content):
            fpath = m.group(1)
            if not (ROOT / fpath).exists():
                errors.append(f"{name}: referenced file `{fpath}` not found")

    return errors


def main() -> None:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    errors = validate()
    if errors:
        print(f"FAIL: {len(errors)} validation errors:\n")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("OK: All skill references valid")


if __name__ == "__main__":
    main()
