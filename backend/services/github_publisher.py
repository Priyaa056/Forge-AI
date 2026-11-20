"""Push a generated application to a GitHub repository.

The platform talks to the GitHub REST API (Git Data endpoints) with the token the user supplies for
that one push. The token is never stored, logged or returned: it lives only in the request header of
this client and is scrubbed from any error text.

Each push is one commit on the chosen branch:

* new repository - created in the token owner's account (private by default) and filled with the app;
* existing repository - the app's files are added or updated on top of what is already there. Files
  the user added on GitHub are kept; files FORGE AI pushed earlier but no longer generates are removed.

Files that must never leave the machine (``.env``, databases, keys, build and dependency folders) are
not pushed. Set ``FORGE_GITHUB_API_URL`` to use GitHub Enterprise Server (``https://<host>/api/v3``).
"""

import base64
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from backend.codegen.project_files import file_tree
from backend.monitoring import sanitize_secret

DEFAULT_API_URL = "https://api.github.com"
OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
SECRET_NAMES = {".env", ".envrc", ".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
SECRET_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-journal", ".pyc", ".pem", ".key", ".p12", ".pfx")
MAX_FILES = 3000
MAX_TOTAL_BYTES = 50 * 1024 * 1024
TOKEN_HELP = ("A classic token needs the 'repo' scope; a fine-grained token needs 'Contents: read and write' "
              "(and 'Administration: read and write' to create repositories).")

# Tests (and local end-to-end checks) can route the client to a fake GitHub.
_transport_override: Optional[httpx.BaseTransport] = None
_active_pushes: set = set()
_active_lock = threading.Lock()


def set_transport_for_tests(transport: Optional[httpx.BaseTransport]) -> None:
    global _transport_override
    _transport_override = transport


class GitHubPublishError(Exception):
    """A push that could not be completed; ``status_code`` is the platform API status to return."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class PushOptions:
    token: str
    mode: str  # "new" or "existing"
    name: Optional[str] = None  # new repository name
    repository: Optional[str] = None  # "owner/name" of an existing repository
    private: bool = True
    description: Optional[str] = None
    branch: Optional[str] = None
    message: str = "Update from FORGE AI"
    previous: Optional[Dict[str, Any]] = None  # project's earlier GitHub link (for stale-file cleanup)


@dataclass
class PushResult:
    full_name: str
    html_url: str
    branch: str
    commit_sha: str
    commit_url: str
    created_repository: bool
    changed: bool
    files: int
    removed: List[str] = field(default_factory=list)
    pushed_paths: List[str] = field(default_factory=list)

    def link(self, version: Optional[int]) -> Dict[str, Any]:
        """What the project remembers about its GitHub repository (never the token)."""
        return {"full_name": self.full_name, "html_url": self.html_url, "branch": self.branch,
                "last_commit": self.commit_sha, "commit_url": self.commit_url, "pushed_version": version,
                "pushed_at": datetime.now(timezone.utc).isoformat(), "pushed_paths": self.pushed_paths}


def api_url() -> str:
    return (os.getenv("FORGE_GITHUB_API_URL") or DEFAULT_API_URL).rstrip("/")


def is_publishable(rel_path: str) -> bool:
    """False for files that must never be pushed (secrets, local databases, compiled files)."""
    name = PurePosixPath(rel_path).name.lower()
    if name in SECRET_NAMES or (name.startswith(".env.") and name != ".env.example"):
        return False
    return not name.endswith(SECRET_SUFFIXES)


def collect_files(root: Path) -> List[Tuple[str, bytes]]:
    """The generated app's files to push, read into memory (build/dependency folders and secrets excluded)."""
    entries = [f for f in file_tree(root) if is_publishable(f["path"])]
    if not entries:
        raise GitHubPublishError("This version has no generated files to push.", 409)
    if len(entries) > MAX_FILES or sum(f["bytes"] for f in entries) > MAX_TOTAL_BYTES:
        raise GitHubPublishError("The generated app is too large to push in one commit.", 413)
    return [(f["path"], (Path(root) / f["path"]).read_bytes()) for f in entries]


def validate_options(options: PushOptions) -> None:
    if options.mode not in ("new", "existing"):
        raise GitHubPublishError("Choose a new or an existing repository.")
    if not options.token or not options.token.strip() or any(c.isspace() for c in options.token.strip()):
        raise GitHubPublishError("Enter a GitHub access token.")
    if options.mode == "new":
        name = (options.name or "").strip()
        if not REPO_RE.match(name) or name in (".", ".."):
            raise GitHubPublishError("Repository names may use letters, numbers, '-', '_' and '.' (up to 100).")
    else:
        owner, _, repo = (options.repository or "").strip().partition("/")
        if not OWNER_RE.match(owner) or not REPO_RE.match(repo) or repo in (".", ".."):
            raise GitHubPublishError("Enter the existing repository as owner/name, e.g. octo-org/farm-app.")
    if options.branch:
        branch = options.branch.strip()
        if (not BRANCH_RE.match(branch) or ".." in branch or branch.startswith(("/", "-", "."))
                or branch.endswith(("/", ".lock", "."))):
            raise GitHubPublishError(f"'{branch}' is not a valid branch name.")


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


class GitHubPublisher:
    def __init__(self, token: str, base_url: Optional[str] = None, transport: Optional[httpx.BaseTransport] = None,
                 timeout: float = 60.0):
        self._token = token.strip()
        self.client = httpx.Client(
            base_url=base_url or api_url(), timeout=timeout, transport=transport or _transport_override,
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "FORGE-AI-platform"},
        )

    def close(self) -> None:
        self.client.close()

    # ------------------------------------------------------------------ HTTP
    def _scrub(self, text: str) -> str:
        return sanitize_secret(str(text).replace(self._token, "[REDACTED]")) if self._token else str(text)

    def _call(self, method: str, path: str, *, ok: Sequence[int] = (200, 201), not_found: Optional[str] = None,
              allow: Sequence[int] = (), **kwargs) -> httpx.Response:
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise GitHubPublishError(f"Could not reach GitHub: {self._scrub(exc.__class__.__name__)}. "
                                     "Check the internet connection and try again.", 502) from None
        if response.status_code in ok or response.status_code in allow:
            return response
        try:
            body = response.json()
        except ValueError:
            body = {}
        detail = self._scrub(body.get("message") or "") if isinstance(body, dict) else ""
        errors = body.get("errors") if isinstance(body, dict) else None
        if isinstance(errors, list):
            extra = "; ".join(self._scrub(e.get("message") or e.get("code") or "") for e in errors if isinstance(e, dict))
            detail = f"{detail} ({extra})" if extra.strip() else detail
        status = response.status_code
        if status == 401:
            raise GitHubPublishError("GitHub rejected the access token. Check that it is correct and has not expired.")
        if status == 429 or (status == 403 and response.headers.get("x-ratelimit-remaining") == "0"):
            raise GitHubPublishError("GitHub's rate limit was reached. Wait a few minutes and try again.", 429)
        if status == 403:
            raise GitHubPublishError(f"The access token is not allowed to do this ({detail or 'forbidden'}). {TOKEN_HELP}")
        if status == 404 and not_found:
            raise GitHubPublishError(not_found)
        raise GitHubPublishError(f"GitHub returned an error ({status}){': ' + detail if detail else ''}.", 502)

    # ------------------------------------------------------------------ steps
    def login(self) -> str:
        return self._call("GET", "/user").json()["login"]

    def create_repository(self, name: str, private: bool, description: Optional[str]) -> Dict[str, Any]:
        response = self._call("POST", "/user/repos", allow=(422,), json={
            "name": name, "private": private, "description": (description or "")[:350], "auto_init": True})
        if response.status_code == 422:
            text = self._scrub(response.text).lower()
            if "already exists" in text:
                raise GitHubPublishError(f"You already have a repository named '{name}' on GitHub. Choose another "
                                         "name, or push to it as an existing repository.", 409)
            raise GitHubPublishError(f"GitHub could not create the repository '{name}'.")
        return response.json()

    def repository(self, full_name: str) -> Dict[str, Any]:
        repo = self._call("GET", f"/repos/{full_name}", not_found=(
            f"Repository {full_name} was not found, or the access token cannot see it.")).json()
        if (repo.get("permissions") or {}).get("push") is False:
            raise GitHubPublishError(f"The access token cannot push to {full_name}. {TOKEN_HELP}")
        return repo

    def head(self, full_name: str, branch: str) -> Optional[str]:
        """Commit sha the branch points to; None if the branch does not exist; "" if the repository is empty."""
        response = self._call("GET", f"/repos/{full_name}/git/ref/heads/{branch}", allow=(404, 409))
        if response.status_code == 409:
            return ""
        if response.status_code == 404:
            return None
        data = response.json()
        if isinstance(data, list):  # a prefix match, not the exact branch
            return None
        return data["object"]["sha"]

    def initialise_empty(self, full_name: str, branch: str) -> str:
        """The Git Data API cannot write to an empty repository; give it a first commit."""
        self._call("PUT", f"/repos/{full_name}/contents/.forge-ai", json={
            "message": "Initialise repository", "branch": branch,
            "content": base64.b64encode(b"Pushed by FORGE AI\n").decode()})
        sha = self.head(full_name, branch)
        if not sha:
            raise GitHubPublishError("GitHub did not initialise the empty repository; try again.", 502)
        return sha

    def tree_of(self, full_name: str, commit_sha: str) -> Tuple[str, Optional[set]]:
        tree_sha = self._call("GET", f"/repos/{full_name}/git/commits/{commit_sha}").json()["tree"]["sha"]
        listing = self._call("GET", f"/repos/{full_name}/git/trees/{tree_sha}", params={"recursive": "1"}).json()
        if listing.get("truncated"):
            return tree_sha, None  # too large to list; skip stale-file cleanup
        return tree_sha, {item["path"] for item in listing.get("tree", []) if item.get("type") == "blob"}

    # ------------------------------------------------------------------ push
    def push(self, files: List[Tuple[str, bytes]], options: PushOptions) -> PushResult:
        validate_options(options)
        self.login()  # checks the token before anything is written
        created = options.mode == "new"
        if created:
            repo = self.create_repository(options.name.strip(), options.private, options.description)
        else:
            repo = self.repository(options.repository.strip())
        full_name = repo["full_name"]
        default_branch = repo.get("default_branch") or "main"
        branch = (options.branch or "").strip() or default_branch

        parent = self.head(full_name, branch)
        new_branch = parent is None
        if parent == "":
            parent = self.initialise_empty(full_name, branch)
            new_branch = False
        elif parent is None:
            parent = self.head(full_name, default_branch)
            if parent == "":
                parent = self.initialise_empty(full_name, default_branch)
            elif parent is None:
                raise GitHubPublishError(f"The default branch of {full_name} could not be read.", 502)
        base_tree, existing = self.tree_of(full_name, parent)

        paths = [p for p, _ in files]
        entries: List[Dict[str, Any]] = []
        for path, data in files:
            if _is_text(data):
                entries.append({"path": path, "mode": "100644", "type": "blob", "content": data.decode("utf-8")})
            else:
                blob = self._call("POST", f"/repos/{full_name}/git/blobs",
                                  json={"content": base64.b64encode(data).decode(), "encoding": "base64"}).json()
                entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        removed: List[str] = []
        previous = options.previous or {}
        if existing is not None and previous.get("full_name", "").lower() == full_name.lower() \
                and previous.get("branch") == branch:
            current = set(paths)
            removed = sorted(p for p in previous.get("pushed_paths") or [] if p not in current and p in existing)
            entries.extend({"path": p, "mode": "100644", "type": "blob", "sha": None} for p in removed)

        tree = self._call("POST", f"/repos/{full_name}/git/trees", json={"base_tree": base_tree, "tree": entries}).json()
        html_url = repo.get("html_url") or f"https://github.com/{full_name}"
        if tree["sha"] == base_tree and not new_branch:
            return PushResult(full_name, html_url, branch, parent, f"{html_url}/commit/{parent}", created, False,
                              len(files), [], paths)
        commit = self._call("POST", f"/repos/{full_name}/git/commits",
                            json={"message": options.message, "tree": tree["sha"], "parents": [parent]}).json()
        if new_branch:
            self._call("POST", f"/repos/{full_name}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
        else:
            moved = self._call("PATCH", f"/repos/{full_name}/git/refs/heads/{branch}", allow=(409, 422),
                               json={"sha": commit["sha"], "force": False})
            if moved.status_code in (409, 422):
                raise GitHubPublishError(f"Branch '{branch}' changed on GitHub while pushing. Try again.", 409)
        commit_url = commit.get("html_url") or f"{html_url}/commit/{commit['sha']}"
        return PushResult(full_name, html_url, branch, commit["sha"], commit_url, created, True, len(files),
                          removed, paths)


def publish(project_id: str, files: List[Tuple[str, bytes]], options: PushOptions) -> PushResult:
    """Push ``files`` for ``project_id``; one push per project at a time."""
    validate_options(options)
    with _active_lock:
        if project_id in _active_pushes:
            raise GitHubPublishError("A push to GitHub is already in progress for this project.", 409)
        _active_pushes.add(project_id)
    publisher = GitHubPublisher(options.token)
    try:
        return publisher.push(files, options)
    finally:
        publisher.close()
        with _active_lock:
            _active_pushes.discard(project_id)
