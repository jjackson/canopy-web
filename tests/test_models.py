import pytest

from apps.collections.models import Collection, Source
from apps.workspace.models import WorkspaceSession
from apps.skills.models import Skill
from apps.evals.models import EvalSuite, EvalCase, EvalRun


class TestCollection:
    def test_create_collection(self, collection):
        assert collection.pk is not None
        assert collection.name == "Test Collection"
        assert collection.description == "A test collection of sources"
        assert collection.created_at is not None
        assert collection.updated_at is not None
        assert str(collection) == "Test Collection"

    def test_collection_defaults(self, db):
        col = Collection.objects.create(name="Minimal")
        assert col.description == ""


class TestSource:
    def test_create_source(self, source, collection):
        assert source.pk is not None
        assert source.collection == collection
        assert source.source_type == "slack"
        assert source.title == "Test Slack Thread"
        assert source.content == "This is a test slack thread content."
        assert source.metadata == {"channel": "#general", "thread_ts": "1234567890.123456"}
        assert source.created_at is not None

    @pytest.mark.parametrize(
        "source_type,title,content",
        [
            ("slack", "Slack Thread", "Thread content from #general"),
            ("transcript", "AI Session", "User: Hello\nAssistant: Hi there"),
            ("document", "Design Doc", "# Architecture\n\nThis document describes..."),
            ("text", "Raw Notes", "Some raw text notes here"),
        ],
    )
    def test_all_source_types(self, db, collection, source_type, title, content):
        source = Source.objects.create(
            collection=collection,
            source_type=source_type,
            title=title,
            content=content,
        )
        assert source.pk is not None
        assert source.source_type == source_type
        assert source.collection == collection

    def test_source_related_name(self, source, collection):
        assert collection.sources.count() == 1
        assert collection.sources.first() == source


class TestWorkspaceSession:
    def test_create_workspace_session(self, db, collection):
        session = WorkspaceSession.objects.create(collection=collection)
        assert session.pk is not None
        assert session.status == "created"
        assert session.collection == collection
        assert session.proposed_approach == {}
        assert session.proposed_eval_cases == []
        assert session.skill_draft == {}
        assert session.edit_history == []
        assert session.created_at is not None
        assert session.updated_at is not None

    def test_workspace_session_status_update(self, db, collection):
        session = WorkspaceSession.objects.create(collection=collection, status="analyzing")
        assert session.status == "analyzing"

    def test_workspace_session_related_name(self, db, collection):
        WorkspaceSession.objects.create(collection=collection)
        assert collection.workspace_sessions.count() == 1


class TestSkill:
    def test_create_skill_version_default(self, db):
        skill = Skill.objects.create(
            name="tone-matcher",
            description="Matches the tone of the source material",
            definition={"system_prompt": "You are a tone matcher.", "parameters": {}},
        )
        assert skill.pk is not None
        assert skill.name == "tone-matcher"
        assert skill.version == 1
        assert skill.usage_count == 0
        assert skill.workspace_session is None
        assert skill.created_at is not None
        assert skill.updated_at is not None

    def test_skill_with_workspace_session(self, db, collection):
        session = WorkspaceSession.objects.create(collection=collection)
        skill = Skill.objects.create(
            name="linked-skill",
            definition={"system_prompt": "test"},
            workspace_session=session,
        )
        assert skill.workspace_session == session

    def test_skill_name_unique(self, db):
        Skill.objects.create(name="unique-skill", definition={})
        with pytest.raises(Exception):
            Skill.objects.create(name="unique-skill", definition={})


class TestEvalSuite:
    def test_create_eval_suite_with_cases(self, db):
        skill = Skill.objects.create(name="eval-test-skill", definition={"prompt": "test"})
        suite = EvalSuite.objects.create(skill=skill)

        assert suite.pk is not None
        assert suite.skill == skill
        assert suite.created_at is not None

        case1 = EvalCase.objects.create(
            suite=suite,
            name="Happy path",
            input_data={"text": "Hello world"},
            expected_output={"tone": "friendly"},
            source_excerpt="From the slack thread: Hello world",
        )
        case2 = EvalCase.objects.create(
            suite=suite,
            name="Edge case - empty input",
            input_data={"text": ""},
            expected_output={"tone": "neutral"},
        )

        assert suite.cases.count() == 2
        assert case1.name == "Happy path"
        assert case1.source_excerpt == "From the slack thread: Hello world"
        assert case2.source_excerpt == ""

    def test_eval_suite_one_to_one(self, db):
        skill = Skill.objects.create(name="one-to-one-skill", definition={})
        EvalSuite.objects.create(skill=skill)
        with pytest.raises(Exception):
            EvalSuite.objects.create(skill=skill)

    def test_eval_suite_related_name(self, db):
        skill = Skill.objects.create(name="related-skill", definition={})
        suite = EvalSuite.objects.create(skill=skill)
        assert skill.eval_suite == suite


class TestEvalRun:
    def test_create_eval_run_with_results_and_score(self, db):
        skill = Skill.objects.create(name="run-test-skill", definition={"prompt": "test"})
        suite = EvalSuite.objects.create(skill=skill)

        EvalCase.objects.create(
            suite=suite,
            name="Test case",
            input_data={"text": "input"},
            expected_output={"result": "expected"},
        )

        run = EvalRun.objects.create(
            suite=suite,
            status="completed",
            results={
                "cases": [
                    {"case_id": 1, "passed": True, "score": 0.95, "output": {"result": "expected"}},
                ]
            },
            overall_score=0.95,
            runtime="web",
        )

        assert run.pk is not None
        assert run.status == "completed"
        assert run.overall_score == 0.95
        assert run.results["cases"][0]["passed"] is True
        assert run.runtime == "web"
        assert run.created_at is not None

    def test_eval_run_defaults(self, db):
        skill = Skill.objects.create(name="defaults-skill", definition={})
        suite = EvalSuite.objects.create(skill=skill)
        run = EvalRun.objects.create(suite=suite)

        assert run.status == "pending"
        assert run.results == {}
        assert run.overall_score is None
        assert run.runtime == "web"

    def test_multiple_runs_per_suite(self, db):
        skill = Skill.objects.create(name="multi-run-skill", definition={})
        suite = EvalSuite.objects.create(skill=skill)
        EvalRun.objects.create(suite=suite, status="completed", overall_score=0.8)
        EvalRun.objects.create(suite=suite, status="completed", overall_score=0.9)

        assert suite.runs.count() == 2
