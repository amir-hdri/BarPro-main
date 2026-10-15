#!/usr/bin/env python3
"""Multi-Agent Sync Framework — Standalone Zero-Dependency Coordination Tool.

Synchronizes state, provides atomic workspace locking, manages session logs,
and enforces atomic commits across Antigravity, OpenCode, Hermes, and Claude Code.
"""

import argparse
import os
import re
import sys
from datetime import datetime

SCHEMA_VERSION_STR = "2.0.0"

REQUIRED_STATE_SECTIONS = [
    "# 🎯 هدف جاری",
    "## ✅ کارهای انجام‌شده",
    "## 📁 فایل‌های تغییریافته",
    "## 🎯 تسک دقیق بعدی",
    "## 🧠 تصمیمات فنی و چرایی",
    "## ⚠️ نکات حساس و موانع",
]

AGENTS_MD_CONTENT = """# Multi-Agent Sync Protocol v2.0

این مخزن از پروتکل هماهنگی چند-ایجنت استفاده می‌کند. تمامی ابزارهای هوش مصنوعی (Antigravity، OpenCode، Hermes، Claude Code) ملزم به رعایت این پروتکل هستند.

## 🔴 پروتکل شروع به کار (قبل از هرگونه تغییر در کد)
1. بررسی فایل `.context/LOCK` — اگر فایل وجود دارد، نشان‌دهنده فعالیت ایجنت دیگری است. کار را متوقف کرده و به کاربر هشدار دهید.
2. خواندن فایل `.context/STATE.md` — تصویر زنده از وضعیت پروژه، آخرین تصمیمات و تسک جاری.
3. در صورت وجود Cairn در پروژه، مستند `.cairn/plans/PROJECT.md` را مرور کنید.
4. ثبت قفل در فایل `.context/LOCK` از طریق دستور: `python3 scripts/agent_sync.py start <نام_ایجنت>`.

## 🔴 پروتکل اتمام نشست (قبل از ثبت کامیت)
1. به‌روزرسانی تمام بخش‌های ۵‌گانه در `.context/STATE.md`.
2. ثبت رکورد گزارش در انتهای `.context/SESSION_LOG.md`.
3. ثبت کامیت اتمیک که هم کدهای تغییریافته و هم فایل‌های وضعیت (`.context/`) را شامل شود.
4. فایل قفل `.context/LOCK` به صورت خودکار توسط post-commit hook آزاد می‌شود (یا از طریق `python3 scripts/agent_sync.py end <نام_ایجنت>`).

## 🟡 قوانین رفتاری و جلوگیری از تعارض
- **اصل حفظ پیوستگی (Preserve & Justify):** بازنویسی سلیقه‌ای کدهای ایجنت قبلی اکیداً ممنوع است.
- در صورت وجود باگ یا نقص منطقی، موظفید دلیل دقیق اصلاح را در بخش "تصمیمات فنی" ثبت کنید.
- مستقیماً فایل‌های ساختاری `.cairn/` را ویرایش نکنید؛ این فایل‌ها توسط ابزارهای Cairn MCP مدیریت می‌شوند.

## 🟢 دستورات کمکی سریع
- بررسی وضعیت سلامت: `python3 scripts/agent_sync.py status`
- خلاصه وضعیت هنداف: `python3 scripts/agent_sync.py handoff`
- فشرده‌سازی لاگ‌های قدیمی: `python3 scripts/agent_sync.py compact-log`
"""

CLAUDE_MD_CONTENT = """@AGENTS.md

<!-- Claude Code Native Adapter -->
<!-- All general multi-agent rules are loaded from AGENTS.md via the import directive above. -->
"""

GEMINI_RULE_MD_CONTENT = """# Agent Sync Protocol — Antigravity Rules

## Session Start (BEFORE any work)
1. Check `.context/LOCK` — if active, STOP and notify user.
2. If Cairn is active, run `cairn brief` and `cairn waypoint resume`.
3. Read `.context/STATE.md` to load active decisions and next task.
4. Run `python3 scripts/agent_sync.py start antigravity`.

## Session End (BEFORE committing)
1. If Cairn is active, run `cairn waypoint` to checkpoint.
2. Update `.context/STATE.md` (all 5 required sections).
3. Append record to `.context/SESSION_LOG.md`.
4. Atomic commit of source files together with `.context/STATE.md`.
"""

STATE_MD_TEMPLATE = f"""<!--schema:{SCHEMA_VERSION_STR}-->
<!--agent:INITIAL-->
<!--timestamp:2026-10-15T00:00:00+03:30-->

# 🎯 هدف جاری
راه‌اندازی اولیه و آماده‌سازی ساختار پروژه

## ✅ کارهای انجام‌شده
- استقرار فریمورک هماهنگی چند-ایجنت
- نصب Git Hooks محافظتی

## 📁 فایل‌های تغییریافته
- `AGENTS.md`
- `CLAUDE.md`
- `scripts/agent_sync.py`

## 🎯 تسک دقیق بعدی
تعریف اولین فاز یا تسک پروژه بر اساس نیازمندی‌ها
پیشنیاز: مشخص شدن نیازمندی اولیه توسط کاربر

## 🧠 تصمیمات فنی و چرایی
- استفاده از ساختار استاندارد بدون وابستگی خارجی جهت پرتابل بودن روی همه سیستم‌ها

## ⚠️ نکات حساس و موانع
- هیچ مانعی وجود ندارد. پروژه آماده ورود اولین ایجنت است.
"""

SESSION_LOG_MD_HEADER = """# Multi-Agent Session History
تاریخچه ترتیبی نشست‌های ایجنت‌ها در این مخزن. رکوردهای جدید در انتهای فایل اضافه می‌شوند.

---
"""

PRE_COMMIT_HOOK_CONTENT = """#!/bin/bash
set -euo pipefail

# Check if non-context files are staged
CODE_CHANGED=$(git diff --cached --name-only | grep -v '^\\.context/' | grep -v '^$' | wc -l || true)
STATE_CHANGED=$(git diff --cached --name-only | grep -c '^\\.context/STATE\\.md$' || true)

if [ "$CODE_CHANGED" -gt 0 ] && [ "$STATE_CHANGED" -eq 0 ]; then
    echo ""
    echo "❌ [AgentSync Guard] کامیت مسدود شد!"
    echo "   فایل‌های سورس تغییر کرده‌اند اما .context/STATE.md به‌روزرسانی نشده است."
    echo ""
    echo "   راهنما: ابتدا فایل وضعیت را با گزارش کارهای انجام‌شده آپدیت کنید:"
    echo "   1) ویرایش .context/STATE.md یا اجرای: python3 scripts/agent_sync.py end <نام_ایجنت>"
    echo "   2) git add .context/STATE.md"
    echo ""
    exit 1
fi

# Schema validation if STATE.md exists
if [ -f ".context/STATE.md" ] && [ -f ".context/schema.version" ]; then
    REQUIRED_SCHEMA=$(cat ".context/schema.version" | tr -d '[:space:]')
    CURRENT_SCHEMA=$(grep -o '<!--schema:[^>]*-->' .context/STATE.md | head -1 | sed 's/<!--schema://' | sed 's/-->//' | tr -d '[:space:]')
    if [ -n "$CURRENT_SCHEMA" ] && [ "$CURRENT_SCHEMA" != "$REQUIRED_SCHEMA" ]; then
        echo "⚠️  [AgentSync Guard] هشدار: نسخه اسکما ($CURRENT_SCHEMA) با نسخه مورد انتظار ($REQUIRED_SCHEMA) همخوانی ندارد."
    fi
fi

exit 0
"""

POST_COMMIT_HOOK_CONTENT = """#!/bin/bash
if [ -f ".context/LOCK" ]; then
    LOCK_INFO=$(cat ".context/LOCK" 2>/dev/null || echo "unknown")
    rm -f ".context/LOCK"
    echo "✅ [AgentSync] قفل کار با موفقیت آزاد شد ($LOCK_INFO)."
fi
"""

TEMPLATES = {
    "AGENTS.md": AGENTS_MD_CONTENT,
    "CLAUDE.md": CLAUDE_MD_CONTENT,
    ".gemini/rules/agent-sync-protocol.md": GEMINI_RULE_MD_CONTENT,
    ".context/schema.version": SCHEMA_VERSION_STR + "\n",
    ".context/STATE.md": STATE_MD_TEMPLATE,
    ".context/SESSION_LOG.md": SESSION_LOG_MD_HEADER,
    ".git/hooks/pre-commit": PRE_COMMIT_HOOK_CONTENT,
    ".git/hooks/post-commit": POST_COMMIT_HOOK_CONTENT,
}

class AgentSyncManager:
    """Manages project initialization, locks, verification, and session history."""

    def init_project(self, target_dir: str, force: bool = False) -> dict:
        created_files = []
        skipped_files = []

        for rel_path, content in TEMPLATES.items():
            if rel_path.startswith(".git/") and not os.path.exists(os.path.join(target_dir, ".git")):
                continue

            full_path = os.path.join(target_dir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            if os.path.exists(full_path) and not force:
                skipped_files.append(rel_path)
            else:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                if rel_path.startswith(".git/hooks/"):
                    try:
                        os.chmod(full_path, 0o755)
                    except OSError:
                        pass
                created_files.append(rel_path)

        return {
            "success": True,
            "created": created_files,
            "skipped": skipped_files,
            "has_cairn": os.path.exists(os.path.join(target_dir, ".cairn")),
        }

    def acquire_lock(self, target_dir: str, agent_name: str, max_age_hours: float = 2.0) -> tuple[bool, str]:
        lock_file = os.path.join(target_dir, ".context", "LOCK")
        now = datetime.now()

        if os.path.exists(lock_file):
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    data = f.read().strip()
                parts = data.split("|")
                locked_by = parts[0] if parts else "Unknown"
                lock_time = datetime.fromisoformat(parts[1]) if len(parts) > 1 else now

                age_hours = (now - lock_time).total_seconds() / 3600.0
                if age_hours > max_age_hours:
                    msg = f"Stale lock by '{locked_by}' ({age_hours:.1f}h old) overridden by '{agent_name}'"
                else:
                    return False, f"Workspace currently LOCKED by '{locked_by}' (acquired {age_hours * 60:.1f} minutes ago)."
            except Exception:
                pass

        os.makedirs(os.path.dirname(lock_file), exist_ok=True)
        with open(lock_file, "w", encoding="utf-8") as f:
            f.write(f"{agent_name}|{now.isoformat()}")

        return True, f"Lock successfully acquired by '{agent_name}'."

    def release_lock(self, target_dir: str, agent_name: str = "") -> bool:
        lock_file = os.path.join(target_dir, ".context", "LOCK")
        if not os.path.exists(lock_file):
            return True

        if agent_name:
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    data = f.read().strip()
                locked_by = data.split("|")[0]
                if locked_by != agent_name and locked_by != "FORCE":
                    pass
            except Exception:
                pass

        try:
            os.remove(lock_file)
            return True
        except OSError:
            return False

    def validate_state(self, target_dir: str) -> tuple[bool, list[str]]:
        state_file = os.path.join(target_dir, ".context", "STATE.md")
        errors = []

        if not os.path.exists(state_file):
            return False, ["File .context/STATE.md does not exist."]

        with open(state_file, "r", encoding="utf-8") as f:
            content = f.read()

        schema_match = re.search(r"<!--schema:([^>]+)-->", content)
        if not schema_match:
            errors.append("Missing schema header (<!--schema:X.Y.Z-->).")
        elif schema_match.group(1).strip() != SCHEMA_VERSION_STR:
            errors.append(f"Schema mismatch: found {schema_match.group(1)}, expected {SCHEMA_VERSION_STR}.")

        for section in REQUIRED_STATE_SECTIONS:
            if section not in content:
                errors.append(f"Missing required section: '{section}'")

        return (len(errors) == 0, errors)

    def record_session(
        self,
        target_dir: str,
        agent_name: str,
        summary: str,
        next_task: str,
        modified_files: list[str],
    ) -> bool:
        log_file = os.path.join(target_dir, ".context", "SESSION_LOG.md")
        now_str = datetime.now().isoformat()
        files_str = ", ".join(f"`{f}`" for f in modified_files) if modified_files else "none"

        entry = (
            f"\n## [{now_str}] Agent: {agent_name}\n"
            f"- **خلاصه کار:** {summary}\n"
            f"- **فایل‌های تغییریافته:** {files_str}\n"
            f"- **تسک پیشنهادی بعدی:** {next_task}\n"
            f"---\n"
        )

        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        return True

    def get_status(self, target_dir: str) -> dict:
        lock_file = os.path.join(target_dir, ".context", "LOCK")
        state_file = os.path.join(target_dir, ".context", "STATE.md")
        log_file = os.path.join(target_dir, ".context", "SESSION_LOG.md")

        lock_info = None
        if os.path.exists(lock_file):
            with open(lock_file, "r", encoding="utf-8") as f:
                parts = f.read().strip().split("|")
                lock_info = {
                    "agent": parts[0] if parts else "Unknown",
                    "timestamp": parts[1] if len(parts) > 1 else "",
                }

        session_count = 0
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
                session_count = len(re.findall(r"^## \[", content, re.MULTILINE))

        valid_state, state_errors = self.validate_state(target_dir)

        return {
            "is_locked": lock_info is not None,
            "lock_info": lock_info,
            "session_count": session_count,
            "is_state_valid": valid_state,
            "state_errors": state_errors,
            "has_cairn": os.path.exists(os.path.join(target_dir, ".cairn")),
        }

    def compact_session_log(self, target_dir: str, keep_latest: int = 20) -> int:
        log_file = os.path.join(target_dir, ".context", "SESSION_LOG.md")
        if not os.path.exists(log_file):
            return 0

        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        entries = re.split(r"(?m)^(?=## \[)", content)
        header = entries[0]
        sessions = entries[1:]

        if len(sessions) <= keep_latest:
            return 0

        archive_sessions = sessions[:-keep_latest]
        keep_sessions = sessions[-keep_latest:]

        archive_dir = os.path.join(target_dir, ".context", "archive")
        os.makedirs(archive_dir, exist_ok=True)
        archive_name = f"sessions-{datetime.now().strftime('%Y-%m')}.md"
        archive_path = os.path.join(archive_dir, archive_name)

        with open(archive_path, "a", encoding="utf-8") as f:
            f.write("".join(archive_sessions))

        with open(log_file, "w", encoding="utf-8") as f:
            f.write(header + "".join(keep_sessions))

        return len(archive_sessions)

def main():
    parser = argparse.ArgumentParser(
        description="Multi-Agent Sync CLI for harmonious cross-agent handoffs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="Initialize multi-agent sync framework in this repository.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing template files.")

    # start
    start_parser = subparsers.add_parser("start", help="Record session start and acquire atomic lock.")
    start_parser.add_argument("agent", help="Agent name (e.g. antigravity, opencode, hermes, claude-code)")

    # end
    end_parser = subparsers.add_parser("end", help="Record session end, update history, and prepare commit.")
    end_parser.add_argument("agent", help="Agent name")
    end_parser.add_argument("--summary", default="", help="Summary of work completed")
    end_parser.add_argument("--next", default="", help="Immediate next task")
    end_parser.add_argument("--files", nargs="*", default=[], help="List of modified files")

    # status
    subparsers.add_parser("status", help="Check workspace lock and sync health.")

    # handoff
    subparsers.add_parser("handoff", help="Display current handoff information from STATE.md.")

    # compact-log
    compact_parser = subparsers.add_parser("compact-log", help="Archive older session log entries.")
    compact_parser.add_argument("--keep", type=int, default=20, help="Number of latest entries to keep.")

    # validate-state
    subparsers.add_parser("validate-state", help="Validate STATE.md against current schema.")

    args = parser.parse_args()
    mgr = AgentSyncManager()
    cwd = os.getcwd()

    if args.command == "init":
        res = mgr.init_project(cwd, force=args.force)
        print(f"✅ Initialized Multi-Agent Sync Framework in: {cwd}")
        if res["created"]:
            print("   Created: " + ", ".join(res["created"]))
        if res["skipped"]:
            print("   Skipped (already exist): " + ", ".join(res["skipped"]))
        if res["has_cairn"]:
            print("   ℹ️ Cairn project detected. Integrated with .cairn workflows.")

    elif args.command == "start":
        ok, msg = mgr.acquire_lock(cwd, args.agent)
        if not ok:
            print(f"❌ {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"✅ Lock acquired by '{args.agent}'.")
        state_file = os.path.join(cwd, ".context", "STATE.md")
        if os.path.exists(state_file):
            print("\n📋 [Current Handoff Summary]:")
            with open(state_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("# 🎯") or line.startswith("## 🎯"):
                        print(f"   {line.strip()}")

    elif args.command == "end":
        summary = args.summary
        next_task = args.next
        if not summary:
            summary = "Session completed successfully."
        if not next_task:
            next_task = "Check .context/STATE.md for next planned task."

        mgr.record_session(cwd, args.agent, summary, next_task, args.files)
        mgr.release_lock(cwd, args.agent)
        print(f"✅ Session recorded for '{args.agent}' and lock released.")
        print("\nNext step: Run atomic commit:")
        print("  git add .context/STATE.md .context/SESSION_LOG.md <code_files>")
        print(f'  git commit -m "feat: handoff [{args.agent}] {summary}"')

    elif args.command == "status":
        st = mgr.get_status(cwd)
        print("📊 [Multi-Agent Sync Status]")
        print(f"  Lock State:      {'🔒 Locked by ' + st['lock_info']['agent'] if st['is_locked'] else '🟢 Unlocked'}")
        print(f"  Total Sessions:  {st['session_count']}")
        print(f"  State Valid:     {'✅ Yes' if st['is_state_valid'] else '❌ No (' + ', '.join(st['state_errors']) + ')'}")
        print(f"  Cairn Present:   {'✅ Yes' if st['has_cairn'] else '⚪ No'}")

    elif args.command == "handoff":
        state_file = os.path.join(cwd, ".context", "STATE.md")
        if not os.path.exists(state_file):
            print("❌ .context/STATE.md not found. Run 'init' first.", file=sys.stderr)
            sys.exit(1)
        with open(state_file, "r", encoding="utf-8") as f:
            print(f.read())

    elif args.command == "compact-log":
        archived = mgr.compact_session_log(cwd, keep_latest=args.keep)
        print(f"✅ Archived {archived} old session log entries.")

    elif args.command == "validate-state":
        ok, errors = mgr.validate_state(cwd)
        if ok:
            print("✅ .context/STATE.md matches schema 2.0.0 perfectly.")
        else:
            print("❌ Validation errors:", file=sys.stderr)
            for err in errors:
                print(f"   - {err}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
