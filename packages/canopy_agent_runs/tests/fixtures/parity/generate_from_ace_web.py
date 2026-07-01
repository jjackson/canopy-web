"""Generate GOLDEN read-model JSON + a declarative trees.json from ace-web's
REAL apps/opps run-reading code (sync.load_opp), driving ace-web's OWN
FakeDriveClient with representative ACE run folders.

Run from the ace-web project root:
    uv run python /path/to/gen_parity_golden.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.conf import settings  # noqa: E402

import yaml  # noqa: E402

from apps.opps import skills as skills_mod  # noqa: E402
from apps.opps import serializers as serializers_mod  # noqa: E402
from apps.opps.sync import load_opp  # noqa: E402
from apps.opps.tests.fixtures.fake_drive import FakeDriveClient  # noqa: E402

STUB = (Path("apps/opps/tests/fixtures/stub_plugin")).resolve()
settings.ACE_PLUGIN_PATH = str(STUB)
skills_mod.reset_cache()
serializers_mod.reset_system_overview_cache()

OUT_DIR = Path(
    "/Users/jjackson/emdash/worktrees/canopy-web/emdash/canopy-web-mhux4/"
    "apps/agent_runs/tests/fixtures/parity"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# run_state.yaml builder — shape A (explicit phase status + steps map), plus
# top-level phase/step/mode/gates the plugin writes.
# ---------------------------------------------------------------------------
def run_state_yaml(
    *, phase, step, mode, started_at, phases, gates=None, extra=None
):
    doc = {
        "current_phase": phase,
        "current_step": step,
        "mode": mode,
        "started_at": started_at,
        "initiated_by": "ace@dimagi-ai.com",
        "last_actor": "ace@dimagi-ai.com",
        "last_actor_at": "2026-06-01T12:00:00Z",
        "phases": phases,
    }
    if gates:
        doc["gates"] = gates
    if extra:
        doc.update(extra)
    return yaml.safe_dump(doc, sort_keys=False)


def phase_block(status, steps):
    return {"status": status, "steps": dict(steps)}


# Canonical phase -> ordered skills (from the live registry).
PHASE_SKILLS = {
    "design-review": ["idea-to-pdd", "pdd-to-test-prompts"],
    "commcare-setup": [
        "pdd-to-learn-app", "pdd-to-deliver-app", "app-deploy",
        "app-test", "training-materials",
    ],
    "connect-setup": ["connect-program-setup", "connect-opp-setup"],
    "ocs-setup": ["ocs-agent-setup", "ocs-chatbot-qa", "ocs-chatbot-eval"],
    "llo-management": [
        "llo-invite", "llo-onboarding", "llo-uat", "llo-launch",
        "timeline-monitor", "flw-data-review",
    ],
    "closeout": ["opp-closeout", "llo-feedback", "learnings-summary", "cycle-grade"],
}


def all_done_phases():
    out = {}
    for ph, sk in PHASE_SKILLS.items():
        out[ph] = phase_block("complete", {s: {"status": "done"} for s in sk})
    return out


def judge_yaml(skill, score, verdict, at):
    return (
        f"skill: {skill}\n"
        f"verdict: {verdict}\n"
        f"overall_score: {score}\n"
        f"evaluated_at: {at}\n"
    )


def qa_result_yaml(qa_skill, verdict, *, run, passed, failed, at):
    return yaml.safe_dump(
        {
            "skill": qa_skill,
            "verdict": verdict,
            "ran_at": at,
            "stats": {"checks_run": run, "checks_passed": passed, "checks_failed": failed},
            "failures": [
                {
                    "check": "form-count-matches-pdd",
                    "type": "static",
                    "detail": "PDD specifies 5 deliver forms; built app has 3.",
                    "auto_fix_hint": "Regenerate deliver app with the 2 missing forms.",
                }
            ] if verdict == "fail" else [],
            "auto_fix": {"attempted": True, "attempts": 2, "succeeded": False}
            if verdict == "fail" else None,
        },
        sort_keys=False,
    )


def decisions_yaml(rows):
    return yaml.safe_dump({"decisions": rows}, sort_keys=False)


# ===========================================================================
# The four representative run folders. Each is one opp with one run under
# runs/<run-id>/ (the current multi-run ACE-plugin layout).
# ===========================================================================
def build_runs():
    runs = {}

    # --- (a) simple complete run -------------------------------------------
    runs["simple_complete"] = {
        "slug": "malaria-rdt-simple",
        "run_id": "20260601-0900",
        "run_state": run_state_yaml(
            phase="closeout", step="cycle-grade", mode="autopilot",
            started_at="2026-06-01T09:00:00Z",
            phases=all_done_phases(),
        ),
        "files": {
            "idea.md": "FLW-administered malaria RDT screening pilot.",
            "pdd.md": "# Malaria RDT PDD\n\nVerify-and-Pay archetype.",
            "app-summaries/learn-app-summary.md": "nova_app_id: app-100\n8 modules",
            "app-summaries/deliver-app-summary.md": "nova_app_id: app-101\n4 forms",
            "closeout/cycle-grade.md": "# Cycle Grade\n\nOverall: A-",
        },
        "verdicts": {},
        "qa": {},
        "decisions": None,
    }

    # --- (b) mid-flight run ------------------------------------------------
    mid_phases = {
        "design-review": phase_block(
            "complete", {"idea-to-pdd": {"status": "done"},
                         "pdd-to-test-prompts": {"status": "done"}}),
        "commcare-setup": phase_block(
            "complete", {s: {"status": "done"} for s in PHASE_SKILLS["commcare-setup"]}),
        "connect-setup": phase_block(
            "running", {"connect-program-setup": {"status": "running"},
                        "connect-opp-setup": {"status": "pending"}}),
        "ocs-setup": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["ocs-setup"]}),
        "llo-management": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["llo-management"]}),
        "closeout": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["closeout"]}),
    }
    runs["mid_flight"] = {
        "slug": "nutrition-midflight",
        "run_id": "20260602-1030",
        "run_state": run_state_yaml(
            phase="connect-setup", step="connect-program-setup", mode="review",
            started_at="2026-06-02T10:30:00Z",
            phases=mid_phases,
        ),
        "files": {
            "idea.md": "Infant nutrition monitoring.",
            "pdd.md": "# Nutrition PDD\n\nMonitor-and-Refer archetype.",
            "app-summaries/learn-app-summary.md": "nova_app_id: app-200\n6 modules",
            "app-summaries/deliver-app-summary.md": "nova_app_id: app-201\n3 forms",
            "connect-setup/program.md": "Connect program created.",
        },
        "verdicts": {},
        "qa": {},
        "decisions": None,
    }

    # --- (c) judge verdicts AND a qa-failed step ---------------------------
    judge_phases = {
        "design-review": phase_block(
            "complete", {"idea-to-pdd": {"status": "done"},
                         "pdd-to-test-prompts": {"status": "done"}}),
        "commcare-setup": phase_block(
            "running", {"pdd-to-learn-app": {"status": "done"},
                        "pdd-to-deliver-app": {"status": "running"},
                        "app-deploy": {"status": "pending"},
                        "app-test": {"status": "pending"},
                        "training-materials": {"status": "pending"}}),
        "connect-setup": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["connect-setup"]}),
        "ocs-setup": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["ocs-setup"]}),
        "llo-management": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["llo-management"]}),
        "closeout": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["closeout"]}),
    }
    runs["judge_and_qa_failed"] = {
        "slug": "cholera-qa-gate",
        "run_id": "20260603-1400",
        "run_state": run_state_yaml(
            phase="commcare-setup", step="pdd-to-deliver-app", mode="review",
            started_at="2026-06-03T14:00:00Z",
            phases=judge_phases,
        ),
        "files": {
            "idea.md": "Cholera outbreak response.",
            "pdd.md": "# Cholera PDD\n\nVerify-and-Pay archetype.",
            "app-summaries/learn-app-summary.md": "nova_app_id: app-300\n7 modules",
        },
        "verdicts": {
            # OLD verdict layout (verdicts/<skill>[-variant].yaml) — the shape
            # the artifact-manifest declares and the existing fixtures use.
            "idea-to-pdd-deep.yaml": judge_yaml(
                "idea-to-pdd", 88, "pass", "2026-06-03T13:10:00Z"),
            "pdd-to-learn-app-deep.yaml": judge_yaml(
                "pdd-to-learn-app", 81, "pass", "2026-06-03T13:40:00Z"),
        },
        "qa": {
            # NEW QA-result layout: <N-phase>/<producer>-qa_result.yaml
            "2-commcare/pdd-to-deliver-app-qa_result.yaml": qa_result_yaml(
                "pdd-to-deliver-app-qa", "fail",
                run=6, passed=4, failed=2, at="2026-06-03T13:55:00Z"),
        },
        "decisions": None,
    }

    # --- (d) decisions.yaml (ai-default + overridden) + open gate ----------
    dec_phases = {
        "design-review": phase_block(
            "complete", {"idea-to-pdd": {"status": "done"},
                         "pdd-to-test-prompts": {"status": "done"}}),
        "commcare-setup": phase_block(
            "running", {"pdd-to-learn-app": {"status": "done"},
                        "pdd-to-deliver-app": {"status": "done"},
                        "app-deploy": {"status": "running"},
                        "app-test": {"status": "pending"},
                        "training-materials": {"status": "pending"}}),
        "connect-setup": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["connect-setup"]}),
        "ocs-setup": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["ocs-setup"]}),
        "llo-management": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["llo-management"]}),
        "closeout": phase_block(
            "pending", {s: {"status": "pending"} for s in PHASE_SKILLS["closeout"]}),
    }
    dec_rows = [
        {
            "id": "d1",
            "phase": "1-design",
            "skill": "idea-to-pdd",
            "question": "Which program archetype best fits this idea?",
            "ai-default": "Verify-and-Pay",
            "options": ["Verify-and-Pay", "Monitor-and-Refer", "Train-and-Certify"],
            "reasoning": "Source describes piecework payment on verified delivery.",
            "status": "ai-default",
            "source": "idea.md",
            "evidence_basis": "stated",
        },
        {
            "id": "d2",
            "phase": "2-commcare",
            "skill": "pdd-to-learn-app",
            "question": "How many training modules should the Learn app have?",
            "ai-default": "5 modules",
            "options": ["3 modules", "5 modules", "7 modules"],
            "reasoning": "Default cadence for a 6-week onboarding.",
            "status": "overridden",
            "override": "7 modules",
            "override_reasoning": "Partner requires two extra compliance modules.",
            "source": "pdd.md",
            "evidence_basis": "inferred",
        },
    ]
    runs["decisions_open_gate"] = {
        "slug": "tb-decisions-gate",
        "run_id": "20260604-1115",
        "run_state": run_state_yaml(
            phase="commcare-setup", step="app-deploy", mode="review",
            started_at="2026-06-04T11:15:00Z",
            phases=dec_phases,
            gates={
                "idea-to-pdd": {
                    "decision": "approved",
                    "decided_by": "neal@dimagi.com",
                    "decided_at": "2026-06-04T11:20:00Z",
                    "note": "PDD passes EM stress test.",
                },
                "app-deploy": {
                    "decision": "pending",
                    "decided_by": "",
                    "decided_at": "2026-06-04T11:40:00Z",
                    "note": "",
                },
            },
        ),
        "files": {
            "idea.md": "TB contact-tracing pilot.",
            "pdd.md": "# TB PDD\n\nVerify-and-Pay archetype.",
            "app-summaries/learn-app-summary.md": "nova_app_id: app-400\n7 modules",
            "app-summaries/deliver-app-summary.md": "nova_app_id: app-401\n5 forms",
            "gate-briefs/idea-to-pdd.md": "# Gate brief idea-to-pdd\n\n- [x] EM specified",
            "gate-briefs/app-deploy.md": "# Gate brief app-deploy\n\n- [ ] Both apps released",
        },
        "verdicts": {
            "idea-to-pdd-deep.yaml": judge_yaml(
                "idea-to-pdd", 90, "pass", "2026-06-04T11:18:00Z"),
        },
        "qa": {},
        "decisions": decisions_yaml(dec_rows),
    }

    return runs


# ---------------------------------------------------------------------------
# Assemble a nested FakeDriveClient tree for one run folder.
# ---------------------------------------------------------------------------
def nest(d, path, body):
    parts = path.split("/")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = body


def build_run_folder(run):
    folder = {"run_state.yaml": run["run_state"]}
    for path, body in run["files"].items():
        nest(folder, path, body)
    if run["verdicts"]:
        folder.setdefault("verdicts", {})
        for name, body in run["verdicts"].items():
            folder["verdicts"][name] = body
    for path, body in run["qa"].items():
        nest(folder, path, body)
    if run["decisions"]:
        folder["decisions.yaml"] = run["decisions"]
    return folder


def build_tree(run):
    return {
        "ACE": {
            run["slug"]: {
                "opp.yaml": yaml.safe_dump(
                    {
                        "display_name": run["slug"],
                        "slug": run["slug"],
                        "created_at": "2026-06-01T00:00:00Z",
                        "created_by": "ace@dimagi-ai.com",
                    },
                    sort_keys=False,
                ),
                "runs": {run["run_id"]: build_run_folder(run)},
            }
        }
    }


# ---------------------------------------------------------------------------
# Canonical read-model extraction from the OppSnapshot + run_state.
# ---------------------------------------------------------------------------
def canonical(run, snap, run_state):
    rd = snap.current_run
    derived_status = (
        snap.runs_summary[0].lifecycle_status if snap.runs_summary else None
    )

    steps = sorted(
        (
            {
                "skill": s.step.skill_name,
                "phase": s.step.phase,
                "ordinal": s.step.ordinal,
                "status": s.step.status,
            }
            for s in rd.steps
        ),
        key=lambda r: (r["ordinal"], r["skill"]),
    )

    artifacts = sorted(
        (
            {"skill": s.step.skill_name, "name": a.name}
            for s in rd.steps
            for a in s.artifacts
        ),
        key=lambda r: (r["skill"], r["name"]),
    )

    verdicts = []
    for s in rd.steps:
        if s.judge is not None:
            verdicts.append({
                "skill": s.step.skill_name,
                "kind": "judge",
                "score": s.judge.score,
                "passed": s.judge.passed,
            })
        if s.qa_result is not None:
            verdicts.append({
                "skill": s.step.skill_name,
                "kind": "qa",
                "score": None,
                "passed": s.qa_result.verdict == "pass",
            })
    verdicts.sort(key=lambda r: (r["skill"], r["kind"]))

    decisions = sorted(
        (
            {
                "step": d.skill,
                "question": d.question,
                "ai_default": d.ai_default,
                "override": d.override,
                "status": d.status,
            }
            for d in rd.decisions
        ),
        key=lambda r: (r["step"], r["question"]),
    )

    gates_map = (run_state.get("gates") or {})
    gates = sorted(
        (
            {"step": skill, "decision": (g or {}).get("decision")}
            for skill, g in gates_map.items()
        ),
        key=lambda r: r["step"],
    )

    return {
        "name": run["slug"],
        "run_id": rd.run_id,
        "run": {
            "mode": rd.mode,
            "status": derived_status,
            "current_phase": rd.current_phase,
            "current_step": rd.current_step,
        },
        "steps": steps,
        "artifacts": artifacts,
        "verdicts": verdicts,
        "decisions": decisions,
        "gates": gates,
    }


# ---------------------------------------------------------------------------
# Declarative tree description for trees.json (paths + bodies).
# ---------------------------------------------------------------------------
def flat_paths(node, prefix=""):
    out = {}
    for name, val in node.items():
        p = f"{prefix}/{name}" if prefix else name
        if isinstance(val, dict):
            out.update(flat_paths(val, p))
        else:
            out[p] = val
    return out


def main():
    runs = build_runs()
    written = []
    trees_doc = {
        "_README": (
            "Declarative description of each ACE run folder. Rebuild the "
            "IDENTICAL tree in a sibling FakeDriveClient by creating each "
            "file at `files[path]` with the given string body. Layout is the "
            "current ACE multi-run shape: ACE/<slug>/opp.yaml + "
            "ACE/<slug>/runs/<run_id>/...  Folders are implied by path "
            "separators; any path not ending a known file is a folder."
        ),
        "ace_root": "ACE",
        "runs": {},
    }

    for key, run in runs.items():
        tree = build_tree(run)
        client = FakeDriveClient.from_tree(tree)
        ace_id = client.folder_id("ACE")
        snap = load_opp(client, ace_folder_id=ace_id, slug=run["slug"])
        run_state = yaml.safe_load(run["run_state"])

        doc = canonical(run, snap, run_state)
        path = OUT_DIR / f"{key}.golden.json"
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        written.append(str(path))

        # Declarative tree: the run-folder contents only (under the run_id),
        # plus opp-level opp.yaml.
        opp_node = tree["ACE"][run["slug"]]
        trees_doc["runs"][key] = {
            "slug": run["slug"],
            "run_id": run["run_id"],
            "opp_files": {
                p: b for p, b in flat_paths(opp_node).items()
                if not p.startswith("runs/")
            },
            "run_files": flat_paths(opp_node["runs"][run["run_id"]]),
        }

    trees_path = OUT_DIR / "trees.json"
    trees_path.write_text(json.dumps(trees_doc, indent=2, sort_keys=True) + "\n")
    written.append(str(trees_path))

    print(json.dumps({"written": written}, indent=2))


if __name__ == "__main__":
    main()
