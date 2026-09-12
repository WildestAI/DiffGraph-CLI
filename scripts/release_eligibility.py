#!/usr/bin/env python3
"""Classify whether a tested main commit is eligible for an immutable release.

A merge without ``release:publish`` is an ordinary product merge, not a failed
release.  A merge which opts into publication must satisfy every release
prerequisite, otherwise this command exits non-zero with a corrective error.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


REQUIRED_ISSUE_LABELS = {"release:ready", "direction:aligned", "roadmap"}
DISALLOWED_ISSUE_LABELS = {"direction:revise", "direction:discuss-close"}
BUMP_LABELS = {"release:patch", "release:minor", "release:major"}


def labels(node: dict[str, Any]) -> set[str]:
    return {item["name"] for item in node.get("labels", {}).get("nodes", [])}


def result(eligible: bool, reason: str, *, bump: str | None = None, error: bool = False) -> int:
    payload: dict[str, Any] = {"eligible": eligible, "reason": reason}
    if bump is not None:
        payload["bump"] = bump
    print(json.dumps(payload))
    return 2 if error else 0


def has_truncated_connection(repository: dict[str, Any]) -> bool:
    """Return whether any bounded release-policy GraphQL connection is incomplete."""
    pull_requests = repository.get("pullRequests", {})
    if pull_requests.get("pageInfo", {}).get("hasNextPage"):
        return True
    for pr in pull_requests.get("nodes", []):
        if pr.get("labels", {}).get("pageInfo", {}).get("hasNextPage"):
            return True
        issues = pr.get("closingIssuesReferences", {})
        if issues.get("pageInfo", {}).get("hasNextPage"):
            return True
        for issue in issues.get("nodes", []):
            if issue.get("labels", {}).get("pageInfo", {}).get("hasNextPage"):
                return True
    return False


def classify(repository_data: dict[str, Any], tested_sha: str, repository: str) -> int:
    if has_truncated_connection(repository_data):
        return result(False, "Release-policy query is incomplete; refusing to classify bounded results.", error=True)

    pull_requests = repository_data.get("pullRequests", {}).get("nodes", [])
    matching = [pr for pr in pull_requests if pr.get("mergeCommit", {}).get("oid") == tested_sha]
    if len(matching) != 1:
        return result(False, f"Skipped: expected one merged PR for tested SHA {tested_sha}; found {len(matching)}.")

    pr = matching[0]
    pr_labels = labels(pr)
    if "release:publish" not in pr_labels:
        return result(False, f"Skipped: PR #{pr['number']} is not release-eligible (missing release:publish).")

    bump_labels = pr_labels & BUMP_LABELS
    if len(bump_labels) != 1:
        return result(False, f"PR #{pr['number']} opted into release:publish but needs exactly one semantic bump label.", error=True)

    issues = [
        issue
        for issue in pr.get("closingIssuesReferences", {}).get("nodes", [])
        if issue.get("repository", {}).get("nameWithOwner") == repository
    ]
    if len(issues) != 1:
        return result(False, f"PR #{pr['number']} opted into release:publish but must close exactly one same-repository roadmap issue; found {len(issues)}.", error=True)

    issue = issues[0]
    issue_labels = labels(issue)
    missing = REQUIRED_ISSUE_LABELS - issue_labels
    blocked = DISALLOWED_ISSUE_LABELS & issue_labels
    if missing or blocked:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if blocked:
            details.append("has " + ", ".join(sorted(blocked)))
        return result(False, f"PR #{pr['number']} opted into release:publish but issue #{issue['number']} is ineligible ({'; '.join(details)}).", error=True)

    bump = next(iter(bump_labels)).removeprefix("release:")
    return result(True, f"Eligible: PR #{pr['number']} closes release-ready issue #{issue['number']} with release:{bump}.", bump=bump)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tested-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-requests-json", required=True)
    args = parser.parse_args()
    data = json.loads(args.pull_requests_json)
    return classify(data, args.tested_sha, args.repository)


if __name__ == "__main__":
    sys.exit(main())
