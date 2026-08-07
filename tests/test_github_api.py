"""Tests for github_api pagination and error handling, using a mocked requests."""

from unittest.mock import patch

import pytest
import requests

import github_api


class FakeResponse:
    def __init__(self, json_data, links=None, status_ok=True):
        self._json = json_data
        self.links = links or {}
        self._status_ok = status_ok

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.exceptions.HTTPError("404")


def test_make_github_api_call_follows_pagination():
    # Two pages of commits; the helper must concatenate both (regression: it
    # previously returned only the first page, breaking commits[-1]).
    page1 = FakeResponse(
        [{"sha": "a"}, {"sha": "b"}],
        links={"next": {"url": "https://api.github.com/pr/commits?page=2"}},
    )
    page2 = FakeResponse([{"sha": "c"}])

    with patch("github_api.requests.get", side_effect=[page1, page2]) as mock_get:
        commits = github_api.make_github_api_call("https://api.github.com/pr/commits", "tok")

    assert [c["sha"] for c in commits] == ["a", "b", "c"]
    assert commits[-1]["sha"] == "c"
    # timeout must be passed on every request.
    for call in mock_get.call_args_list:
        assert call.kwargs["timeout"] == github_api.REQUEST_TIMEOUT


def test_make_github_api_call_raises_on_http_error():
    bad = FakeResponse(None, status_ok=False)
    with patch("github_api.requests.get", return_value=bad), pytest.raises(ValueError):
        github_api.make_github_api_call("https://api.github.com/pr/commits", "tok")


def test_get_workflow_runs_extends_across_pages():
    page1 = FakeResponse(
        {"workflow_runs": [{"id": 1}]},
        links={"next": {"url": "https://api.github.com/runs?page=2"}},
    )
    page2 = FakeResponse({"workflow_runs": [{"id": 2}]})
    with patch("github_api.requests.get", side_effect=[page1, page2]):
        runs = github_api.get_workflow_runs("o", "r", "tok", {"per_page": 100})
    assert [r["id"] for r in runs] == [1, 2]
