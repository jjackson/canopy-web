"""
Seed the database with realistic demo data for walkthrough runs.

Usage:
    python manage.py seed_demo          # Create demo data
    python manage.py seed_demo --reset  # Wipe and re-create
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.collections.models import Collection, Source
from apps.workspace.models import WorkspaceSession
from apps.skills.models import Skill
from apps.evals.models import EvalSuite, EvalCase, EvalRun


# ── Demo source material ────────────────────────────────────────────

ONBOARDING_TRANSCRIPT = """\
Agent: Welcome! I see you're setting up CommCare for your CHW program. Let's \
walk through the key steps.

User: We have 200 community health workers across 3 districts. They need to do \
household registration, child growth monitoring, and referral tracking.

Agent: Great. Let's start with the application structure. I'll create three \
modules: Household Registration, Child Health Visit, and Referral Follow-up. \
Each one maps to a distinct workflow your CHWs perform in the field.

User: Should we use case management or form-based?

Agent: Case management. Each household is a case, children are sub-cases. This \
lets CHWs see their full caseload, filter by due visits, and track referral \
status over time. Form-based would lose that continuity.

User: What about the registration form?

Agent: The registration form captures: head of household name, GPS coordinates, \
number of children under 5, and a photo. GPS auto-captures on save. The photo \
helps CHWs identify the right household on return visits.

User: We also need to calculate Z-scores for growth monitoring.

Agent: I'll add a hidden value that computes weight-for-age Z-score using WHO \
standards. The form will show a color-coded indicator: green (normal), yellow \
(moderate), red (severe). If red, it auto-creates a referral case.

User: And the referral tracking?

Agent: Referral follow-up form: date of referral, facility referred to, \
outcome (treated/not seen/referred further), and a follow-up date. If outcome \
is "not seen", it flags for supervisor review and schedules a re-visit in 48 hours.
"""

CODE_REVIEW_CONVERSATION = """\
User: Can you review this pull request? It adds a new caching layer for our API.

Agent: Looking at the changes...

1. Cache key generation uses f"api:{endpoint}:{user_id}" which correctly \
differentiates per-user and per-endpoint.

2. Cache invalidation via @invalidate_cache on write endpoints clears all keys \
matching the endpoint prefix. Aggressive but safe.

3. Race condition: There's a TOCTOU issue in get_or_set(). Between checking if \
the key exists and setting it, another request could write a different value. \
Use Redis SETNX for critical paths.

4. Error handling: If Redis is down, the decorator falls through to the database. \
Good. But add a metric counter for cache misses due to connection errors.

5. Memory: No eviction policy configured. Add maxmemory-policy allkeys-lru.
"""


# ── Skill definitions with eval history ─────────────────────────────

SKILLS = [
    {
        "name": "CommCare App Configuration",
        "description": "Guide users through configuring CommCare mobile apps with case management, calculated fields, and staged deployment.",
        "definition": {
            "name": "CommCare App Configuration",
            "description": "Walk through the full setup of a CommCare application: define modules and forms, configure case management, add calculated properties, and plan a staged rollout.",
            "steps": [
                {"name": "Gather requirements", "description": "Understand program scope: users, geography, workflows.", "tools": [], "inputs": ["program_description"], "outputs": ["requirements_summary"]},
                {"name": "Design app structure", "description": "Create modules and forms. Choose case management for longitudinal tracking.", "tools": ["commcare_app_builder"], "inputs": ["requirements_summary"], "outputs": ["module_list", "case_hierarchy"]},
                {"name": "Configure calculations", "description": "Add hidden values for computed indicators (Z-scores, risk flags) with color coding.", "tools": ["commcare_app_builder"], "inputs": ["module_list"], "outputs": ["calculated_fields"]},
                {"name": "Plan deployment", "description": "Set up user groups, staged rollout, and data integration.", "tools": ["commcare_admin"], "inputs": ["case_hierarchy"], "outputs": ["deployment_plan"]},
            ],
        },
        "eval_cases": [
            {"name": "CHW program with growth monitoring", "input_data": {"prompt": "Set up a CHW program for 200 workers doing household registration and child health visits."}, "expected_output": {"contains": ["case management", "household", "z-score", "referral"]}},
            {"name": "Staged rollout recommendation", "input_data": {"prompt": "We have 5 districts. How should we deploy?"}, "expected_output": {"contains": ["staged", "rollout", "pilot"]}},
            {"name": "GPS and photo capture", "input_data": {"prompt": "How do we verify CHWs are visiting the right households?"}, "expected_output": {"contains": ["GPS", "photo"]}},
        ],
        "eval_runs": [
            {"score": 0.33, "days_ago": 12, "failures": {"CHW program with growth monitoring": "Expected 'z-score' in output but not found. Output focused on registration workflow only.", "GPS and photo capture": "Expected 'photo' in output but not found. Response mentioned GPS but not photo verification."}},
            {"score": 0.67, "days_ago": 9, "failures": {"GPS and photo capture": "Expected 'photo' in output but not found. Response covered GPS tracking but omitted photo capture."}},
            {"score": 0.67, "days_ago": 6, "failures": {"CHW program with growth monitoring": "Expected 'z-score' in output but not found. Output mentioned 'growth monitoring' but not WHO Z-score calculation."}},
            {"score": 1.0, "days_ago": 3},
            {"score": 1.0, "days_ago": 1},
        ],
    },
    {
        "name": "Code Review Analysis",
        "description": "Structured code review: identify bugs, race conditions, security issues, and operational risks with severity ratings.",
        "definition": {
            "name": "Code Review Analysis",
            "description": "Systematically review code changes for correctness, security, performance, and operational readiness.",
            "steps": [
                {"name": "Read the diff", "description": "Parse code changes and understand the intent.", "tools": ["git_diff"], "inputs": ["pull_request_url"], "outputs": ["change_summary"]},
                {"name": "Check correctness", "description": "Look for logic errors, race conditions, edge cases.", "tools": [], "inputs": ["change_summary"], "outputs": ["correctness_issues"]},
                {"name": "Check security", "description": "Review for injection risks, auth bypasses, missing rate limits.", "tools": [], "inputs": ["change_summary"], "outputs": ["security_issues"]},
                {"name": "Synthesize review", "description": "Prioritize by severity, recommend fixes, give verdict.", "tools": [], "inputs": ["correctness_issues", "security_issues"], "outputs": ["review_summary", "verdict"]},
            ],
        },
        "eval_cases": [
            {"name": "Caching layer review", "input_data": {"prompt": "Review a Redis caching implementation for a REST API."}, "expected_output": {"contains": ["cache", "invalidation", "TTL"]}},
            {"name": "Race condition detection", "input_data": {"prompt": "This code reads a value, checks it, then writes. Any issues?"}, "expected_output": {"contains": ["race condition", "TOCTOU"]}},
        ],
        "eval_runs": [
            {"score": 0.5, "days_ago": 14, "failures": {"Race condition detection": "Expected 'TOCTOU' in output but not found. Response identified the race condition but used 'check-then-act' terminology."}},
            {"score": 1.0, "days_ago": 10},
            {"score": 1.0, "days_ago": 7},
            {"score": 1.0, "days_ago": 4},
            {"score": 0.5, "days_ago": 2, "failures": {"Race condition detection": "Expected 'TOCTOU' in output but not found. Response focused on mutex locks instead of naming the vulnerability class."}},
            {"score": 1.0, "days_ago": 0},
        ],
    },
    {
        "name": "Incident Response Runbook",
        "description": "Triage production incidents: classify severity, identify blast radius, coordinate response, and write post-mortems.",
        "definition": {
            "name": "Incident Response Runbook",
            "description": "Structured approach to production incidents from alert to post-mortem.",
            "steps": [
                {"name": "Classify severity", "description": "Determine SEV level from symptoms and affected users.", "tools": ["monitoring_dashboard"], "inputs": ["alert_description"], "outputs": ["severity_level", "blast_radius"]},
                {"name": "Identify root cause", "description": "Trace from symptom to cause using logs, metrics, and recent deploys.", "tools": ["log_search", "deploy_history"], "inputs": ["severity_level"], "outputs": ["root_cause"]},
                {"name": "Mitigate", "description": "Apply immediate fix: rollback, feature flag, or hotfix.", "tools": ["deploy_tool"], "inputs": ["root_cause"], "outputs": ["mitigation_status"]},
                {"name": "Write post-mortem", "description": "Document timeline, root cause, impact, and action items.", "tools": [], "inputs": ["root_cause", "mitigation_status"], "outputs": ["post_mortem"]},
            ],
        },
        "eval_cases": [
            {"name": "Database connection exhaustion", "input_data": {"prompt": "All API endpoints returning 500s. Connection pool at 100%."}, "expected_output": {"contains": ["connection pool", "SEV", "rollback"]}},
            {"name": "Memory leak detection", "input_data": {"prompt": "Service memory usage growing 2% per hour. No recent deploys."}, "expected_output": {"contains": ["memory leak", "heap", "profil"]}},
        ],
        "eval_runs": [
            {"score": 0.5, "days_ago": 8, "failures": {"Memory leak detection": "Expected 'heap' in output but not found. Response discussed memory monitoring but not heap analysis."}},
            {"score": 0.5, "days_ago": 5, "failures": {"Database connection exhaustion": "Expected 'rollback' in output but not found. Response suggested scaling the pool instead of rolling back."}},
            {"score": 1.0, "days_ago": 2},
        ],
    },
    {
        "name": "Data Migration Planner",
        "description": "Plan and execute database migrations: assess risk, write rollback strategies, and validate data integrity.",
        "definition": {
            "name": "Data Migration Planner",
            "description": "Plan safe database migrations with rollback strategies and integrity checks.",
            "steps": [
                {"name": "Assess migration scope", "description": "Identify tables, row counts, and downstream dependencies.", "tools": ["database_client"], "inputs": ["migration_description"], "outputs": ["scope_assessment"]},
                {"name": "Design rollback", "description": "Create a reversible migration plan with point-in-time recovery.", "tools": [], "inputs": ["scope_assessment"], "outputs": ["rollback_plan"]},
                {"name": "Validate integrity", "description": "Write checksums and row count assertions for pre/post migration.", "tools": ["database_client"], "inputs": ["scope_assessment"], "outputs": ["validation_queries"]},
            ],
        },
        "eval_cases": [
            {"name": "Column rename migration", "input_data": {"prompt": "Rename user.email_address to user.email across 2M rows."}, "expected_output": {"contains": ["rollback", "downtime", "index"]}},
            {"name": "Table split migration", "input_data": {"prompt": "Split the orders table into orders and order_items. 10M rows."}, "expected_output": {"contains": ["foreign key", "backfill", "validate"]}},
        ],
        "eval_runs": [
            {"score": 0.5, "days_ago": 10, "failures": {"Table split migration": "Expected 'backfill' in output but not found. Response covered schema changes but not data migration strategy."}},
            {"score": 1.0, "days_ago": 6},
            {"score": 1.0, "days_ago": 3},
            {"score": 1.0, "days_ago": 1},
        ],
    },
    {
        "name": "API Design Review",
        "description": "Review API designs for RESTful conventions, versioning, error handling, and pagination patterns.",
        "definition": {
            "name": "API Design Review",
            "description": "Evaluate API designs against best practices for consistency, usability, and evolvability.",
            "steps": [
                {"name": "Check resource naming", "description": "Verify RESTful URL patterns, plural nouns, no verbs in paths.", "tools": [], "inputs": ["api_spec"], "outputs": ["naming_issues"]},
                {"name": "Check error handling", "description": "Verify consistent error envelope, HTTP status codes, error codes.", "tools": [], "inputs": ["api_spec"], "outputs": ["error_issues"]},
                {"name": "Check pagination", "description": "Verify cursor or offset pagination on list endpoints.", "tools": [], "inputs": ["api_spec"], "outputs": ["pagination_issues"]},
            ],
        },
        "eval_cases": [
            {"name": "REST convention violations", "input_data": {"prompt": "Review: POST /api/getUsers, PUT /api/user/delete/123"}, "expected_output": {"contains": ["GET", "DELETE", "plural"]}},
            {"name": "Missing pagination", "input_data": {"prompt": "GET /api/orders returns all 50K orders in one response."}, "expected_output": {"contains": ["pagination", "cursor", "limit"]}},
        ],
        "eval_runs": [
            {"score": 1.0, "days_ago": 7},
            {"score": 1.0, "days_ago": 4},
            {"score": 1.0, "days_ago": 1},
        ],
    },
]


class Command(BaseCommand):
    help = "Seed database with demo data for walkthrough runs"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Wipe and re-create")

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Resetting demo data...")
            EvalRun.objects.all().delete()
            EvalCase.objects.all().delete()
            EvalSuite.objects.all().delete()
            Skill.objects.all().delete()
            WorkspaceSession.objects.all().delete()
            Source.objects.all().delete()
            Collection.objects.all().delete()

        self._create_published_skills()
        self._create_collection_for_walkthrough()
        self.stdout.write(self.style.SUCCESS("Demo data seeded."))

    def _create_published_skills(self):
        now = timezone.now()

        for spec in SKILLS:
            skill, created = Skill.objects.get_or_create(
                name=spec["name"],
                defaults={
                    "description": spec["description"],
                    "definition": spec["definition"],
                    "version": 1,
                    "usage_count": len(spec["eval_runs"]),
                },
            )
            if not created:
                self.stdout.write(f"  '{skill.name}' exists, skipping.")
                continue

            suite = EvalSuite.objects.create(skill=skill)

            for case_spec in spec["eval_cases"]:
                EvalCase.objects.create(
                    suite=suite,
                    name=case_spec["name"],
                    input_data=case_spec["input_data"],
                    expected_output=case_spec["expected_output"],
                )

            cases = list(suite.cases.all())
            for run_spec in spec["eval_runs"]:
                score = run_spec["score"]
                failures = run_spec.get("failures", {})
                case_results = []
                for c in cases:
                    if c.name in failures:
                        case_results.append({
                            "case_id": c.id, "case_name": c.name,
                            "passed": False,
                            "reasons": [failures[c.name]],
                            "output_preview": "The AI response addressed the topic but missed specific expected terms.",
                        })
                    else:
                        case_results.append({
                            "case_id": c.id, "case_name": c.name,
                            "passed": True, "reasons": [],
                            "output_preview": "AI produced a comprehensive response covering all expected terms.",
                        })

                run = EvalRun.objects.create(
                    suite=suite, status="completed",
                    results={"cases": case_results},
                    overall_score=score,
                    runtime=f"{1.2 + len(cases) * 0.4:.1f}s",
                )
                # Backdate the timestamp
                EvalRun.objects.filter(pk=run.pk).update(
                    created_at=now - timedelta(days=run_spec["days_ago"])
                )

            self.stdout.write(
                f"  Created '{skill.name}' — {len(cases)} cases, {len(spec['eval_runs'])} runs"
            )

    def _create_collection_for_walkthrough(self):
        collection, created = Collection.objects.get_or_create(
            name="Customer Onboarding Workflow",
            defaults={"description": "Extract a reusable onboarding skill from a support conversation"},
        )
        if not created:
            self.stdout.write("  Collection exists, skipping.")
            return
        Source.objects.create(collection=collection, source_type="transcript", title="CommCare Setup Session", content=ONBOARDING_TRANSCRIPT)
        Source.objects.create(collection=collection, source_type="transcript", title="Code Review Session", content=CODE_REVIEW_CONVERSATION)
        self.stdout.write(f"  Created collection with 2 sources")
