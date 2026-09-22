from pathlib import Path


QUERY = Path(__file__).parents[1] / "scripts" / "release_eligibility.graphql"
WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "release-on-resolved-issue.yml"


def _balanced_graphql_delimiters(source: str) -> bool:
    """Check the structural delimiters that GitHub's GraphQL parser requires.

    This query contains no GraphQL string literals or comments, so a small
    delimiter check catches malformed edits without adding a runtime-only
    GraphQL parser dependency to the CLI test environment.
    """
    pairs = {"}": "{", ")": "("}
    stack: list[str] = []
    for character in source:
        if character in "{(":
            stack.append(character)
        elif character in pairs:
            if not stack or stack.pop() != pairs[character]:
                return False
    return not stack


def test_release_eligibility_query_is_structurally_valid_and_wired_to_workflow():
    query = QUERY.read_text()

    assert _balanced_graphql_delimiters(query)
    assert "query($owner: String!, $repo: String!, $sha: String!)" in query
    assert "... on Commit" in query
    assert "associatedPullRequests(first: 100)" in query
    assert "closingIssuesReferences(first: 20)" in query
    assert "query=\"$(< scripts/release_eligibility.graphql)\"" in WORKFLOW.read_text()


def test_release_eligibility_query_requests_every_fail_closed_page_boundary():
    query = QUERY.read_text()

    # The classifier rejects a truncated pull-request, label, or closing-issue
    # connection. Keep every corresponding pageInfo request in the query.
    assert query.count("pageInfo {") == 4
    assert query.count("hasNextPage") == 4
