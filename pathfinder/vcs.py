"""Thin GitHub layer: read a PR's changed SQL and post the comment.

Only the handful of REST calls Pathfinder needs. Isolated here so the rest of
the agent stays testable without hitting GitHub.
"""

from __future__ import annotations

import base64
import re
from typing import Optional

import requests

from .models import PullRequestRef

_PR_URL_RE = re.compile(r"github\.com/(?P<repo>[^/]+/[^/]+)/pull/(?P<num>\d+)")
_API = "https://api.github.com"


def parse_pr_url(url: str) -> tuple[str, int]:
    m = _PR_URL_RE.search(url)
    if not m:
        raise ValueError(f"not a GitHub PR url: {url}")
    return m.group("repo"), int(m.group("num"))


class GitHub:
    def __init__(self, token: Optional[str], timeout: int = 30):
        self.timeout = timeout
        self._s = requests.Session()
        self._s.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        if token:
            self._s.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, **params):
        r = self._s.get(f"{_API}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_pr(self, repo: str, number: int) -> dict:
        return self._get(f"/repos/{repo}/pulls/{number}")

    def pr_ref(self, repo: str, number: int, pr: dict) -> PullRequestRef:
        return PullRequestRef(
            repo=repo, number=number,
            title=pr.get("title", ""),
            author=(pr.get("user") or {}).get("login", ""),
            url=pr.get("html_url", f"https://github.com/{repo}/pull/{number}"),
        )

    def changed_files(self, repo: str, number: int) -> list[dict]:
        files: list[dict] = []
        page = 1
        while True:
            batch = self._get(f"/repos/{repo}/pulls/{number}/files", per_page=100, page=page)
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    def file_at(self, repo: str, path: str, ref: str) -> str:
        """Return file text at a git ref, or '' if it does not exist there."""
        r = self._s.get(f"{_API}/repos/{repo}/contents/{path}", params={"ref": ref}, timeout=self.timeout)
        if r.status_code == 404:
            return ""
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return ""

    def upsert_comment(self, repo: str, number: int, body: str, marker: str) -> str:
        """Create the Pathfinder comment, or edit the existing one in place."""
        comments = self._get(f"/repos/{repo}/issues/{number}/comments", per_page=100)
        existing = next((c for c in comments if marker in (c.get("body") or "")), None)
        if existing:
            r = self._s.patch(
                f"{_API}/repos/{repo}/issues/comments/{existing['id']}",
                json={"body": body}, timeout=self.timeout,
            )
        else:
            r = self._s.post(
                f"{_API}/repos/{repo}/issues/{number}/comments",
                json={"body": body}, timeout=self.timeout,
            )
        r.raise_for_status()
        return r.json().get("html_url", "")
