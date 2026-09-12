import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "release_eligibility.py"
SHA = "a" * 40
REPO = "WildestAI/DiffGraph-CLI"


def run(pr, **page_info):
    repository = {"pullRequests": {"nodes": [pr], "pageInfo": {"hasNextPage": False}}}
    repository["pullRequests"].update(page_info.pop("pull_requests", {}))
    pr["labels"].update(page_info.pop("pr_labels", {}))
    pr["closingIssuesReferences"].update(page_info.pop("closing_issues", {}))
    if pr["closingIssuesReferences"]["nodes"]:
        pr["closingIssuesReferences"]["nodes"][0]["labels"].update(page_info.pop("issue_labels", {}))
    assert not page_info
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--tested-sha", SHA, "--repository", REPO, "--pull-requests-json", json.dumps(repository)],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, json.loads(completed.stdout)


def pull_request(*, labels=(), issue_labels=(), include_issue=True):
    pr = {"number": 53, "mergeCommit": {"oid": SHA}, "labels": {"nodes": [{"name": name} for name in labels], "pageInfo": {"hasNextPage": False}}}
    pr["closingIssuesReferences"] = {"nodes": [] if not include_issue else [{
        "number": 53,
        "repository": {"nameWithOwner": REPO},
        "labels": {"nodes": [{"name": name} for name in issue_labels], "pageInfo": {"hasNextPage": False}},
    }], "pageInfo": {"hasNextPage": False}}
    return pr


def test_non_release_merge_is_green_and_explicitly_skipped():
    code, output = run(pull_request())
    assert code == 0
    assert output == {"eligible": False, "reason": "Skipped: PR #53 is not release-eligible (missing release:publish)."}


def test_valid_patch_minor_and_major_releases_are_eligible():
    issue_labels = ("release:ready", "direction:aligned", "roadmap")
    for bump in ("release:patch", "release:minor", "release:major"):
        code, output = run(pull_request(labels=("release:publish", bump), issue_labels=issue_labels))
        assert code == 0
        assert output["eligible"] is True
        assert bump in output["reason"]


def test_intended_release_requires_a_bump_and_linked_ready_issue():
    code, output = run(pull_request(labels=("release:publish",), issue_labels=()))
    assert code == 2
    assert output["eligible"] is False
    assert "semantic bump" in output["reason"]

    code, output = run(pull_request(labels=("release:publish", "release:patch"), include_issue=False))
    assert code == 2
    assert "same-repository roadmap issue" in output["reason"]


def test_intended_release_rejects_missing_or_invalid_issue_labels():
    code, output = run(pull_request(labels=("release:publish", "release:patch"), issue_labels=("roadmap",)))
    assert code == 2
    assert "missing direction:aligned, release:ready" in output["reason"]

    code, output = run(pull_request(labels=("release:publish", "release:patch"), issue_labels=("release:ready", "direction:aligned", "roadmap", "direction:revise")))
    assert code == 2
    assert "has direction:revise" in output["reason"]


def test_incomplete_bounded_release_policy_connections_fail_closed():
    labels = ("release:publish", "release:patch")
    issue_labels = ("release:ready", "direction:aligned", "roadmap")
    for connection in ("pull_requests", "pr_labels", "closing_issues", "issue_labels"):
        code, output = run(
            pull_request(labels=labels, issue_labels=issue_labels),
            **{connection: {"pageInfo": {"hasNextPage": True}}},
        )
        assert code == 2
        assert output["eligible"] is False
        assert "query is incomplete" in output["reason"]
