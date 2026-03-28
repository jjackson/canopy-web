"""
Eval runner: executes skill eval suites and checks expectations.

Runs each eval case against the skill definition using the Anthropic API,
checks outputs against expected criteria, and stores results.
"""
import time

from .models import EvalRun


def run_skill_step(skill_definition, input_data):
    """Execute a skill against input data using the configured AI backend."""
    from apps.common.anthropic_client import call_ai

    steps_desc = "\n".join(
        f"- {s['name']}: {s['description']}" for s in skill_definition.get("steps", [])
    )
    system = "You are executing a skill. Follow the steps and produce the output."
    prompt = f"Execute this skill:\n{steps_desc}\n\nInput: {input_data}\n\nProduce the complete output."

    return call_ai(system, prompt, max_tokens=2048)


def check_expected(output: str, expected: dict) -> tuple[bool, list[str]]:
    """Check if output meets expected criteria."""
    reasons = []
    passed = True

    for term in expected.get("contains", []):
        if term.lower() not in output.lower():
            passed = False
            reasons.append(f"Missing expected term: '{term}'")

    return passed, reasons


class EvalRunner:
    def __init__(self, skill):
        self.skill = skill

    def execute(self, suite) -> EvalRun:
        """Run each case, check expectations, store results, compute overall score."""
        start = time.monotonic()
        cases = suite.cases.all()
        case_results = []
        passed_count = 0

        for case in cases:
            output = run_skill_step(self.skill.definition, case.input_data)
            passed, reasons = check_expected(output, case.expected_output)
            if passed:
                passed_count += 1
            case_results.append({
                "case_id": case.id,
                "case_name": case.name,
                "passed": passed,
                "reasons": reasons,
                "output_preview": output[:500],
            })

        total = len(case_results)
        overall_score = (passed_count / total) if total > 0 else 0.0
        elapsed = round(time.monotonic() - start, 2)

        run = EvalRun.objects.create(
            suite=suite,
            status="completed",
            results={"cases": case_results},
            overall_score=overall_score,
            runtime=f"{elapsed}s",
        )

        # Increment skill usage count
        self.skill.usage_count += 1
        self.skill.save(update_fields=["usage_count"])

        return run
