"""Run the WebLens verification agent team defined in .freebuff/agents/team.json.

The team is sequential-with-handoff: each role owns one gate, runs its commands
from the repository root, writes its own log and a structured result, and stops
the run on failure. The runner never upgrades a role result: exit 0 -> PASS,
exit 2 -> BLOCKED, anything else -> FAIL.

Usage
-----
    python scripts/agent_team.py                # whole team, stop on failure
    python scripts/agent_team.py --list         # show the plan
    python scripts/agent_team.py --only models  # single role
    python scripts/agent_team.py --keep-going   # run all roles regardless
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TEAM_FILE = REPO_ROOT / ".freebuff" / "agents" / "team.json"


def load_team() -> dict[str, Any]:
    return json.loads(TEAM_FILE.read_text(encoding="utf-8"))


def classify(exit_codes: list[int]) -> str:
    if not exit_codes:
        return "BLOCKED"
    if all(code == 0 for code in exit_codes):
        return "PASS"
    if all(code in (0, 2) for code in exit_codes) and any(code == 2 for code in exit_codes):
        return "BLOCKED"
    return "FAIL"


def run_role(role: dict[str, Any], out_dir: Path, default_timeout: int) -> dict[str, Any]:
    name = role["name"]
    timeout = int(role.get("timeout_s", default_timeout))
    log_path = out_dir / f"{name}.log"
    started = time.perf_counter()
    exit_codes: list[int] = []
    commands: list[dict[str, Any]] = []
    tail = ""

    with log_path.open("w", encoding="utf-8") as log:
        for command in role.get("commands", []):
            log.write(f"$ {command}\n")
            log.flush()
            t0 = time.perf_counter()
            try:
                proc = subprocess.run(
                    command,
                    shell=True,
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                code = proc.returncode
                output = (proc.stdout or "") + (proc.stderr or "")
            except subprocess.TimeoutExpired as e:
                code = 124
                output = f"TIMEOUT after {timeout}s\n{e}"
            log.write(output)
            log.write(f"\n[exit {code}] {round(time.perf_counter() - t0, 2)}s\n\n")
            log.flush()
            exit_codes.append(code)
            commands.append(
                {
                    "command": command,
                    "exit_code": code,
                    "duration_s": round(time.perf_counter() - t0, 2),
                }
            )
            tail = output.strip().splitlines()[-1] if output.strip() else ""

    return {
        "role": name,
        "objective": role.get("objective", ""),
        "owner": role.get("owner", ""),
        "status": classify(exit_codes),
        "gate": role.get("gate", ""),
        "exit_codes": exit_codes,
        "duration_s": round(time.perf_counter() - started, 2),
        "commands": commands,
        "log": str(log_path.relative_to(REPO_ROOT)),
        "last_line": tail[:300],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# WebLens verification agent team",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Team: `{summary['team']}`",
        f"- Mode: {summary['mode']}",
        f"- Verdict: **{summary['verdict']}**",
        f"- Duration: {summary['duration_s']}s",
        "",
        "| # | Role | Owner | Status | Duration | Exit codes | Log |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, role in enumerate(summary["roles"], 1):
        lines.append(
            f"| {i} | {role['role']} | {role['owner']} | **{role['status']}** | "
            f"{role['duration_s']}s | {role['exit_codes']} | `{role['log']}` |"
        )
    lines += ["", "## Role gates", ""]
    for role in summary["roles"]:
        lines.append(f"### {role['role']} — {role['status']}")
        lines.append("")
        lines.append(f"- Objective: {role['objective']}")
        lines.append(f"- Gate: {role['gate']}")
        lines.append(f"- Last output line: `{role['last_line']}`")
        lines.append(f"- Evidence: `{role['log']}`")
        lines.append("")
    lines.append(
        "Status semantics: PASS = every command exited 0, BLOCKED = nothing failed but a role "
        "could not run (exit 2), FAIL = at least one command failed. The runner cannot mark a "
        "role PASS on partial evidence."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the role plan and exit")
    parser.add_argument("--only", help="run a single role by name")
    parser.add_argument("--keep-going", action="store_true", help="continue after a failing role")
    parser.add_argument("--out", help="artifact directory (default reports/team/<stamp>)")
    args = parser.parse_args()

    team = load_team()
    roles = team["roles"]
    if args.only:
        roles = [r for r in roles if r["name"] == args.only]
        if not roles:
            print(f"no such role: {args.only}", file=sys.stderr)
            return 1

    if args.list:
        print(f"team: {team['team']} ({team['execution']['mode']})")
        for role in roles:
            print(f"  {role['name']:<12} {role['owner']:<12} {role['objective']}")
        return 0

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.out) if args.out else REPO_ROOT / team["execution"]["artifact_root"] / stamp
    out_dir = out_dir if out_dir.is_absolute() else (REPO_ROOT / out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    for role in roles:
        print(f"[team] {role['name']} ...", flush=True)
        result = run_role(role, out_dir, int(team["execution"].get("timeout_default_s", 900)))
        results.append(result)
        print(f"[team] {role['name']}: {result['status']} ({result['duration_s']}s)", flush=True)
        if result["status"] == "FAIL" and not args.keep_going:
            print("[team] stopping: a gate failed and --keep-going was not set", flush=True)
            break

    statuses = [r["status"] for r in results]
    verdict = "FAIL" if "FAIL" in statuses else ("BLOCKED" if "BLOCKED" in statuses else "PASS")

    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "team": team["team"],
        "mode": team["execution"]["mode"],
        "verdict": verdict,
        "duration_s": round(time.perf_counter() - started, 2),
        "roles": results,
        "skipped_roles": [r["name"] for r in team["roles"] if r["name"] not in {x["role"] for x in results}],
    }

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")

    print()
    for r in results:
        print(f"{r['role']:<14} {r['status']:<8} {r['duration_s']:>7}s  {r['log']}")
    print(f"\nTEAM VERDICT {verdict} | {out_dir}")

    return 0 if verdict == "PASS" else (2 if verdict == "BLOCKED" else 1)


if __name__ == "__main__":
    sys.exit(main())
