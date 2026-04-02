"""Minimal GitHub Contents API client for updating files in a repo."""

from __future__ import annotations

import base64
from typing import Any

import requests

API = "https://api.github.com"


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_file_text(token: str, owner: str, repo: str, path: str, branch: str) -> tuple[str, str]:
    """Return (decoded_utf8_text, sha) for a file."""
    url = f"{API}/repos/{owner}/{repo}/contents/{path}"
    r = requests.get(
        url,
        headers=_headers(token),
        params={"ref": branch},
        timeout=60,
    )
    if r.status_code != 200:
        raise GitHubError(
            f"Failed to load {path}: {r.text}",
            status=r.status_code,
            detail=r.json() if r.text else None,
        )
    data = r.json()
    if data.get("encoding") != "base64" or "content" not in data:
        raise GitHubError(f"Unexpected response for {path}")
    raw = base64.b64decode(data["content"].replace("\n", ""))
    return raw.decode("utf-8"), data["sha"]


def put_file_bytes(
    token: str,
    owner: str,
    repo: str,
    path: str,
    branch: str,
    content: bytes,
    message: str,
    sha: str | None,
) -> None:
    b64 = base64.b64encode(content).decode("ascii")
    body: dict[str, Any] = {
        "message": message,
        "content": b64,
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    url = f"{API}/repos/{owner}/{repo}/contents/{path}"
    r = requests.put(url, headers=_headers(token), json=body, timeout=120)
    if r.status_code not in (200, 201):
        raise GitHubError(
            f"Failed to update {path}: {r.text}",
            status=r.status_code,
            detail=r.json() if r.text else None,
        )


def put_file_text(
    token: str,
    owner: str,
    repo: str,
    path: str,
    branch: str,
    text: str,
    message: str,
    sha: str | None,
) -> None:
    put_file_bytes(
        token,
        owner,
        repo,
        path,
        branch,
        text.encode("utf-8"),
        message,
        sha,
    )
