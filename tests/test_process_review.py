import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest  # type: ignore[import]

# Add .github directory to path for proper package imports
GITHUB_DIR = str(Path(__file__).resolve().parent.parent.parent)
if GITHUB_DIR not in sys.path:
    sys.path.insert(0, GITHUB_DIR)


JINJA2_AVAILABLE = True
JSONSCHEMA_AVAILABLE = True
YAML_AVAILABLE = True


try:  # pragma: no cover - prefer real PyGithub when available
    import github  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - provide minimal stub package
    github_module = types.ModuleType("github")
    sys.modules["github"] = github_module

    class _StubGithub:
        def __init__(self, *_, **__):
            pass

    github_module.Github = _StubGithub

    github_exception_module = types.ModuleType("github.GithubException")

    class _StubGithubException(Exception):
        def __init__(self, status, *_, **__):
            super().__init__(status)
            self.status = status

    github_exception_module.GithubException = _StubGithubException
    sys.modules["github.GithubException"] = github_exception_module

    pull_request_module = types.ModuleType("github.PullRequest")

    class _StubPullRequest:  # pragma: no cover - structural stub
        pass

    pull_request_module.PullRequest = _StubPullRequest
    sys.modules["github.PullRequest"] = pull_request_module

    repository_module = types.ModuleType("github.Repository")

    class _StubRepository:  # pragma: no cover - structural stub
        pass

    repository_module.Repository = _StubRepository
    sys.modules["github.Repository"] = repository_module

else:  # pragma: no cover - real module available
    github_module = github


try:  # pragma: no cover - prefer real Jinja2 when available
    import jinja2  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - provide minimal stub package
    JINJA2_AVAILABLE = False
    jinja2_module = types.ModuleType("jinja2")
    sys.modules["jinja2"] = jinja2_module

    class _StubTemplate:
        def __init__(self, render):
            self._render = render

        def render(self, **context):
            return self._render(**context)

    class _StubEnvironment:
        def __init__(self, *_, **__):
            pass

        def get_template(self, *_args, **_kwargs):
            raise RuntimeError("Template rendering not available in stub environment")

    class _StubFileSystemLoader:
        def __init__(self, *_, **__):
            pass

    jinja2_module.Template = _StubTemplate
    jinja2_module.Environment = _StubEnvironment
    jinja2_module.FileSystemLoader = _StubFileSystemLoader


try:  # pragma: no cover - prefer real jsonschema when available
    import jsonschema  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - provide minimal stub package
    JSONSCHEMA_AVAILABLE = False
    jsonschema_module = types.ModuleType("jsonschema")
    sys.modules["jsonschema"] = jsonschema_module

    class _StubDraft7Validator:
        def __init__(self, schema):
            self.schema = schema

        def iter_errors(self, data):
            required = self.schema.get("required", [])
            for field in required:
                if field not in data:
                    yield SimpleNamespace(
                        path=[], message=f"'{field}' is a required property"
                    )

            properties = self.schema.get("properties", {})
            for key, constraints in properties.items():
                expected_type = constraints.get("type")
                if expected_type == "string" and key in data and not isinstance(
                    data[key], str
                ):
                    yield SimpleNamespace(
                        path=[key], message="'{}' is not of type 'string'".format(key)
                    )

    jsonschema_module.Draft7Validator = _StubDraft7Validator


try:  # pragma: no cover - prefer real PyYAML when available
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - provide minimal stub package
    YAML_AVAILABLE = False
    yaml_module = types.ModuleType("yaml")

    def _safe_load(_text):
        return {}

    yaml_module.safe_load = _safe_load
    sys.modules["yaml"] = yaml_module


# Import process_review as a proper package to handle relative imports correctly
from process_review import process_review
from github.GithubException import GithubException  # type: ignore  # noqa: E402


def test_truncate_returns_original_when_within_limit():
    assert process_review.truncate("hello", limit=10) == "hello"


def test_truncate_strips_and_truncates_long_text():
    text = "  " + ("x" * 100) + "  "
    result = process_review.truncate(text, limit=50)
    assert result == ("x" * 47) + "..."


def test_find_file_in_workspace_finds_pull_request_dir(monkeypatch, tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    pr_dir = tmp_path / "pull-request"
    pr_dir.mkdir()
    target = pr_dir / "review.json"
    target.write_text("{}")

    monkeypatch.chdir(work_dir)

    found = process_review.find_file_in_workspace("review.json")
    assert found.resolve() == target.resolve()


def test_load_review_data_success(tmp_path):
    data = {
        "approved": True,
        "overallRisk": "LOW",
        "summary": "ok",
        "findings": [],
    }
    path = tmp_path / "review.json"
    path.write_text(json.dumps(data))

    loaded = process_review.load_review_data(path)
    assert loaded == data


def test_load_review_data_missing_required_fields(tmp_path):
    path = tmp_path / "review.json"
    path.write_text(json.dumps({"approved": True}))

    with pytest.raises(ValueError):
        process_review.load_review_data(path)


def test_load_review_data_rejects_whitespace_only(tmp_path):
    path = tmp_path / "review.json"
    path.write_text("   ")

    with pytest.raises(ValueError):
        process_review.load_review_data(path)


def test_validate_review_reports_errors(tmp_path):
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))

    errors = process_review.validate_review({}, schema_path)
    assert errors == ["<root>: 'name' is a required property"]


def test_build_markdown_renders_sections_with_truncation_and_sorting(monkeypatch):
    data = {
        "approved": False,
        "overallRisk": "MEDIUM",
        "summary": "Headline\nAdditional detail",
        "findings": [
            {
                "type": "version",
                "title": "demo chart 1.0.0 -> 1.1.0",
                "subject": {
                    "name": "demo",
                    "kind": "chart",
                    "from": "1.0.0",
                    "to": "1.1.0",
                },
                "risk": "low",
                "summary": "A" * 400,
                "references": [
                    {
                        "url": "https://example.invalid",
                        "note": "B" * 300,
                    }
                ],
            },
            {
                "type": "version",
                "title": "alpha chart 0.9.0 -> 1.0.0",
                "subject": {
                    "name": "alpha",
                    "kind": "chart",
                    "from": "0.9.0",
                    "to": "1.0.0",
                },
                "risk": "HIGH",
                "summary": "Short summary",
            },
            {
                "type": "resource",
                "title": "Deployment/default/zeta",
                "location": {"resource": "Deployment/default/zeta"},
                "cosmetic": False,
                "tags": ["change:container"],
                "risk": "MEDIUM",
                "summary": "C" * 400,
                "evidence": {
                    "diff": "line1\nline2",
                    "yaml": "key: value\nother: x",
                },
            },
            {
                "type": "resource",
                "title": "Deployment/default/alpha",
                "location": {"resource": "Deployment/default/alpha"},
                "cosmetic": False,
                "tags": ["change:kubernetes"],
                "risk": "HIGH",
                "summary": "Minor",
                "evidence": {
                    "diff": "add\nremove",
                    "yaml": "foo: bar",
                },
            },
        ],
    }

    captured_context: dict[str, object] = {}

    class FakeTemplate:
        def render(self, **context):
            captured_context.update(context)
            return "rendered"

    monkeypatch.setattr(process_review, "get_template", lambda: FakeTemplate())

    markdown = process_review.build_markdown(data, ["schema error"])

    assert markdown.endswith("\n")
    assert captured_context["verdict"] == "Needs manual review"
    assert captured_context["headline"] == "Headline"

    finding_groups = captured_context["finding_groups"]  # type: ignore[assignment]
    version_group = next(group for group in finding_groups if group["type"] == "version")
    assert version_group["findings"][0]["subject"]["name"] == "alpha"
    version_by_name = {item["subject"]["name"]: item for item in version_group["findings"]}
    assert version_by_name["demo"]["summary"] == process_review.truncate(
        "A" * 400, limit=280
    )
    assert version_by_name["demo"]["risk"] == "LOW"

    resource_group = next(group for group in finding_groups if group["type"] == "resource")
    assert resource_group["findings"][0]["title"] == "Deployment/default/alpha"
    resource_by_name = {item["title"]: item for item in resource_group["findings"]}
    assert resource_by_name["Deployment/default/zeta"]["summary"] == process_review.truncate(
        "C" * 400, limit=280
    )
    assert resource_by_name["Deployment/default/zeta"]["diff"] == ["line1", "line2"]
    assert resource_by_name["Deployment/default/zeta"]["yaml"] == ["key: value", "other: x"]
    assert resource_by_name["Deployment/default/zeta"]["anchor"].startswith("finding-")
    assert captured_context["validation_errors"] == ["schema error"]


def test_derive_labels_builds_expected_mapping(monkeypatch):
    config = {
        "default_color": "aaaaaa",
        "descriptions": {},
        "change_type_colors": {"container": "0e8a16", "other": "bbbbbb"},
        "update_colors": {"chart": "1d76db", "other": "cccccc"},
        "risk_colors": {"LOW": "00ff00"},
    }
    monkeypatch.setattr(process_review, "get_label_config", lambda: config)

    data = {
        "findings": [
            {"type": "resource", "tags": ["change:container"]},
            {"type": "resource", "changeType": None},
            {"type": "version", "subject": {"kind": "chart"}},
        ],
        "overallRisk": "low",
    }

    labels = process_review.derive_labels(data)

    assert labels["change:container"] == "0e8a16"
    assert labels["change:other"] == "bbbbbb"
    assert labels["update:chart"] == "1d76db"
    assert labels["risk:low"] == "00ff00"


def test_apply_labels_creates_missing_and_handles_conflicts(monkeypatch):
    created = []

    class DummyLabel:
        def __init__(self, name: str):
            self.name = name

    class DummyRepo:
        def __init__(self):
            self.full_name = "acme/repo"
            self._labels = [DummyLabel("risk:medium")]

        def get_labels(self):
            return list(self._labels)

        def create_label(self, name, color, description):
            created.append((name, color, description))
            if name == "change:container":
                self._labels.append(DummyLabel(name))
            else:
                raise GithubException(422, {"message": "exists"}, None)

    class DummyPR:
        def __init__(self, repo):
            self.base = SimpleNamespace(repo=repo)
            self.added = []

        def add_to_labels(self, *names):
            self.added.extend(names)

    monkeypatch.setattr(
        process_review,
        "get_label_config",
        lambda: {
            "descriptions": {
                "change": "change label",
                "update": "update label",
            }
        },
    )

    repo = DummyRepo()
    pr = DummyPR(repo)

    labels = {"change:container": "0e8a16", "update:chart": "1d76db"}
    process_review.apply_labels(pr, labels)

    assert ("change:container", "0e8a16", "change label") in created
    assert ("update:chart", "1d76db", "update label") in created
    assert pr.added == ["change:container", "update:chart"]


def test_publish_comment_invokes_issue_comment_and_truncates():
    class DummyPR:
        def __init__(self):
            self.comments = []

        def create_issue_comment(self, markdown):
            self.comments.append(markdown)
            return SimpleNamespace(id=1)

    pr = DummyPR()
    process_review.publish_comment(pr, "hello")
    assert pr.comments == ["hello"]

    pr_empty = DummyPR()
    process_review.publish_comment(pr_empty, "")
    assert pr_empty.comments == []

    pr_whitespace = DummyPR()
    process_review.publish_comment(pr_whitespace, "   ")
    assert pr_whitespace.comments == []

    long_text = "x" * 70000
    pr_long = DummyPR()
    process_review.publish_comment(pr_long, long_text)
    assert pr_long.comments[0][:65536] == ("x" * 65536)
    assert pr_long.comments[0].endswith("... (truncated due to length)")


def test_approve_and_merge_reviews_and_deletes_branch():
    deleted_refs = []

    class DummyGitRef:
        def __init__(self, name):
            self.name = name

        def delete(self):
            deleted_refs.append(self.name)

    class DummyRepo:
        def __init__(self):
            self.full_name = "acme/repo"

        def get_git_ref(self, ref):
            return DummyGitRef(ref)

    class DummyPR:
        def __init__(self):
            repo = DummyRepo()
            self.base = SimpleNamespace(repo=repo)
            self.head = SimpleNamespace(repo=repo, ref="feature")
            self._merged = False
            self.review_calls = []
            self.merge_called = False

        def is_merged(self):
            return self._merged

        def create_review(self, body, event):
            self.review_calls.append((body, event))

        def merge(self, merge_method):
            self.merge_called = True
            self._merged = True
            return SimpleNamespace(sha="abc123")

    pr = DummyPR()
    process_review.approve_and_merge(pr)

    assert pr.review_calls == [
        ("Automated approval based on structured review.", "APPROVE")
    ]
    assert pr.merge_called is True
    assert deleted_refs == ["heads/feature"]


def test_approve_and_merge_skips_when_already_merged():
    class DummyPR:
        def is_merged(self):
            return True

        def create_review(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("should not create review")

    process_review.approve_and_merge(DummyPR())


def test_load_pull_request_reads_environment(monkeypatch, tmp_path):
    pr = object()

    class DummyRepo:
        def __init__(self):
            self.requests = []

        def get_pull(self, number):
            self.requests.append(number)
            return pr

    repo = DummyRepo()

    class DummyGithub:
        def __init__(self, token, timeout=None):
            assert token == "token"
            assert timeout == 30

        def get_repo(self, name):
            assert name == "acme/repo"
            return repo

    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"number": 42}))

    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setattr(process_review, "Github", DummyGithub)

    result = process_review.load_pull_request("token")
    assert result is pr
    assert repo.requests == [42]


def test_load_pull_request_uses_override(monkeypatch, tmp_path):
    pr = object()

    class DummyRepo:
        def __init__(self):
            self.requests = []

        def get_pull(self, number):
            self.requests.append(number)
            return pr

    repo = DummyRepo()

    class DummyGithub:
        def __init__(self, token, timeout=None):
            assert token == "token"
            assert timeout == 30

        def get_repo(self, name):
            assert name == "acme/repo"
            return repo

    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"number": 12}))

    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("REVIEW_PR_NUMBER", "99")
    monkeypatch.setattr(process_review, "Github", DummyGithub)

    result = process_review.load_pull_request("token")
    assert result is pr
    assert repo.requests == [99]


def test_load_pull_request_requires_environment(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    with pytest.raises(EnvironmentError):
        process_review.load_pull_request("token")


def test_load_pull_request_rejects_invalid_pr_number(monkeypatch, tmp_path):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"number": 0}))

    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    with pytest.raises(ValueError):
        process_review.load_pull_request("token")


def test_should_auto_merge_disabled_returns_false():
    pr = SimpleNamespace(
        head=SimpleNamespace(ref="renovate/test"),
        user=SimpleNamespace(login="renovate[bot]"),
    )
    allowed, reason = process_review.should_auto_merge(pr, {"enabled": False})
    assert allowed is False
    assert "disabled" in reason


def test_should_auto_merge_allows_when_no_rules():
    pr = SimpleNamespace(
        head=SimpleNamespace(ref="feature/test"),
        user=SimpleNamespace(login="someone"),
    )
    allowed, _ = process_review.should_auto_merge(
        pr,
        {
            "enabled": True,
            "branch_prefixes": [],
            "branch_regexes": [],
            "author_logins": [],
        },
    )
    assert allowed is True


def test_should_auto_merge_matches_branch_prefix():
    pr = SimpleNamespace(
        head=SimpleNamespace(ref="renovate/test"),
        user=SimpleNamespace(login="renovate[bot]"),
    )
    allowed, _ = process_review.should_auto_merge(
        pr,
        {
            "enabled": True,
            "branch_prefixes": ["renovate/"],
            "branch_regexes": [],
            "author_logins": [],
        },
    )
    assert allowed is True


def test_should_auto_merge_blocks_when_no_match():
    pr = SimpleNamespace(
        head=SimpleNamespace(ref="feature/test"),
        user=SimpleNamespace(login="dev"),
    )
    allowed, reason = process_review.should_auto_merge(
        pr,
        {
            "enabled": True,
            "branch_prefixes": ["renovate/"],
            "branch_regexes": [],
            "author_logins": [],
        },
    )
    assert allowed is False
    assert "no rules matched" in reason


def test_main_happy_path(monkeypatch, tmp_path):
    if not JINJA2_AVAILABLE:  # pragma: no cover - skip when stubbed
        pytest.skip("jinja2 dependency not available")

    monkeypatch.chdir(tmp_path)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    review_file = output_dir / "review.json"
    review_file.write_text(
        json.dumps(
            {
                "approved": True,
                "overallRisk": "LOW",
                "summary": "ok",
                "findings": [],
            }
        )
    )

    schema_file = tmp_path / "schema.json"
    schema_file.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["approved", "overallRisk", "summary", "findings"],
                "properties": {
                    "approved": {"type": "boolean"},
                    "overallRisk": {"type": "string"},
                    "summary": {"type": "string"},
                    "findings": {"type": "array"},
                },
            }
        )
    )

    calls = []

    monkeypatch.setattr(process_review, "load_pull_request", lambda token: SimpleNamespace())
    monkeypatch.setattr(
        process_review, "should_auto_merge", lambda pr, cfg: (True, "enabled")
    )
    monkeypatch.setattr(
        process_review,
        "apply_labels",
        lambda pr, labels: calls.append(("apply_labels", labels)),
    )
    monkeypatch.setattr(
        process_review,
        "publish_comment",
        lambda pr, markdown: calls.append(("publish_comment", markdown)),
    )
    monkeypatch.setattr(
        process_review,
        "approve_and_merge",
        lambda pr: calls.append(("approve_and_merge", None)),
    )

    monkeypatch.setenv("GITHUB_TOKEN", "token")

    process_review.main(
        ["--output-dir", str(output_dir), "--schema-file", str(schema_file)]
    )

    markdown_path = output_dir / "review.md"
    assert markdown_path.exists()
    assert ("approve_and_merge", None) in calls


def test_main_exits_when_validation_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    review_file = output_dir / "review.json"
    review_file.write_text(
        json.dumps(
            {
                "approved": True,
                "overallRisk": "LOW",
                "summary": "ok",
                "findings": [],
            }
        )
    )

    schema_file = tmp_path / "schema.json"
    schema_file.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["approved", "overallRisk", "summary", "findings"],
                "properties": {"summary": {"type": "string"}},
            }
        )
    )

    approve_called = []

    monkeypatch.setattr(process_review, "load_pull_request", lambda token: SimpleNamespace())
    monkeypatch.setattr(process_review, "validate_review", lambda data, path: ["error"])
    monkeypatch.setattr(
        process_review,
        "build_markdown",
        lambda data, errors, note=None: "markdown contents\n",
    )
    monkeypatch.setattr(process_review, "apply_labels", lambda pr, labels: None)
    monkeypatch.setattr(process_review, "publish_comment", lambda pr, markdown: None)
    monkeypatch.setattr(
        process_review, "approve_and_merge", lambda pr: approve_called.append(True)
    )

    monkeypatch.setenv("GITHUB_TOKEN", "token")

    with pytest.raises(SystemExit) as exc:
        process_review.main(
            ["--output-dir", str(output_dir), "--schema-file", str(schema_file)]
        )

    assert exc.value.code == 1
    assert (output_dir / "review.md").exists()
    assert approve_called == []


def test_sample_review_generates_markdown_artifact():
    if not JINJA2_AVAILABLE:  # pragma: no cover - skip when stubbed
        pytest.skip("jinja2 dependency not available")

    sample_path = Path(__file__).parent / "sample_review.json"
    assert sample_path.exists(), "sample_review.json fixture missing"

    data = json.loads(sample_path.read_text())

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "workflows"
        / "temu-claude-review.schema.json"
    )
    if schema_path.exists():
        validation_errors = process_review.validate_review(data, schema_path)
    else:  # pragma: no cover - schema absent in unusual environments
        validation_errors = []

    markdown = process_review.build_markdown(data, validation_errors)

    artifacts_dir = Path(__file__).parent / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / "sample_review.md"
    output_path.write_text(markdown)

    assert output_path.stat().st_size > 0
