"""In-memory stand-in for the parts of the GitHub REST API that the GitHub publisher uses.

Test double only: it mimics GitHub's responses (status codes, error bodies, fast-forward checks,
empty repositories) closely enough to exercise every branch of ``backend.services.github_publisher``.
"""

import base64
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, parse_qs

import httpx


def _sha(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


class FakeGitHub:
    def __init__(self, tokens: Optional[Dict[str, str]] = None):
        self.tokens = dict(tokens or {"good-token": "forge-tester"})
        self.repos: Dict[str, Dict[str, Any]] = {}
        self.blobs: Dict[str, bytes] = {}
        self.trees: Dict[str, Dict[str, str]] = {}  # tree sha -> {path: blob sha}
        self.commits: Dict[str, Dict[str, Any]] = {}
        self.requests: List[Tuple[str, str]] = []
        self.seen_auth: List[str] = []
        self._counter = 0

    # ------------------------------------------------------------------ helpers for tests
    def add_repo(self, full_name: str, *, empty: bool = False, files: Optional[Dict[str, str]] = None,
                 private: bool = True, collaborators: Tuple[str, ...] = ()) -> Dict[str, Any]:
        owner, name = full_name.split("/")
        repo = {"full_name": full_name, "owner": owner, "name": name, "private": private, "default_branch": "main",
                "refs": {}, "collaborators": set(collaborators)}
        self.repos[full_name.lower()] = repo
        if not empty:
            tree = self._tree({p: self._blob(c.encode()) for p, c in (files or {"README.md": f"# {name}\n"}).items()})
            repo["refs"]["main"] = self._commit(tree, [], "Initial commit")
        return repo

    def files(self, full_name: str, branch: str = "main") -> Dict[str, bytes]:
        repo = self.repos[full_name.lower()]
        tree = self.commits[repo["refs"][branch]]["tree"]
        return {path: self.blobs[sha] for path, sha in self.trees[tree].items()}

    def commit_of(self, full_name: str, branch: str = "main") -> Dict[str, Any]:
        return self.commits[self.repos[full_name.lower()]["refs"][branch]]

    def commit_file(self, full_name: str, path: str, content: str, branch: str = "main") -> str:
        """Simulate someone committing directly on GitHub."""
        repo = self.repos[full_name.lower()]
        head = repo["refs"][branch]
        files = dict(self.trees[self.commits[head]["tree"]])
        files[path] = self._blob(content.encode())
        repo["refs"][branch] = self._commit(self._tree(files), [head], f"Edit {path} on GitHub")
        return repo["refs"][branch]

    # ------------------------------------------------------------------ storage
    def _blob(self, data: bytes) -> str:
        sha = hashlib.sha1(b"blob" + data).hexdigest()
        self.blobs[sha] = data
        return sha

    def _tree(self, files: Dict[str, str]) -> str:
        sha = _sha("tree", sorted(files.items()))
        self.trees[sha] = dict(files)
        return sha

    def _commit(self, tree: str, parents: List[str], message: str) -> str:
        self._counter += 1
        sha = _sha("commit", tree, parents, message, self._counter)
        self.commits[sha] = {"sha": sha, "tree": tree, "parents": list(parents), "message": message}
        return sha

    # ------------------------------------------------------------------ HTTP
    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content) if request.content else None
            status, payload, headers = self.handle(request.method, request.url.raw_path.decode(),
                                                   request.headers.get("authorization", ""), body)
            return httpx.Response(status, json=payload, headers=headers)

        return httpx.MockTransport(handler)

    def handle(self, method: str, raw_path: str, authorization: str, body: Any) -> Tuple[int, Any, Dict[str, str]]:
        parts = urlsplit(raw_path)
        path = parts.path.rstrip("/") or "/"
        query = parse_qs(parts.query)
        self.requests.append((method, path))
        self.seen_auth.append(authorization)
        token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        login = self.tokens.get(token)
        if not login:
            return 401, {"message": "Bad credentials", "documentation_url": "https://docs.github.com/rest"}, {}

        if method == "GET" and path == "/user":
            return 200, {"login": login, "id": 1}, {}
        if method == "POST" and path == "/user/repos":
            full_name = f"{login}/{body['name']}"
            if full_name.lower() in self.repos:
                return 422, {"message": "Repository creation failed.", "errors": [
                    {"resource": "Repository", "code": "custom", "field": "name",
                     "message": "name already exists on this account"}]}, {}
            repo = self.add_repo(full_name, empty=not body.get("auto_init"), private=bool(body.get("private")))
            repo["description"] = body.get("description")
            return 201, self._repo_json(repo, login), {}

        match = re.match(r"^/repos/([^/]+)/([^/]+)(/.*)?$", path)
        if not match:
            return 404, {"message": "Not Found"}, {}
        repo = self.repos.get(f"{match.group(1)}/{match.group(2)}".lower())
        if repo is None or (repo["private"] and login != repo["owner"] and login not in repo["collaborators"]):
            return 404, {"message": "Not Found"}, {}
        rest = match.group(3) or ""
        can_push = login == repo["owner"] or login in repo["collaborators"]
        if method != "GET" and not can_push:
            return 403, {"message": "Resource not accessible by personal access token"}, {}

        if method == "GET" and rest == "":
            return 200, self._repo_json(repo, login), {}
        ref = re.match(r"^/git/refs?/heads/(.+)$", rest)
        if method == "GET" and ref and rest.startswith("/git/ref/"):
            if not repo["refs"]:
                return 409, {"message": "Git Repository is empty."}, {}
            sha = repo["refs"].get(ref.group(1))
            if not sha:
                return 404, {"message": "Not Found"}, {}
            return 200, {"ref": f"refs/heads/{ref.group(1)}", "object": {"sha": sha, "type": "commit"}}, {}
        if not repo["refs"] and rest.startswith("/git/"):
            return 409, {"message": "Git Repository is empty."}, {}
        commit = re.match(r"^/git/commits/([0-9a-f]+)$", rest)
        if method == "GET" and commit:
            data = self.commits.get(commit.group(1))
            if not data:
                return 404, {"message": "Not Found"}, {}
            return 200, {"sha": data["sha"], "tree": {"sha": data["tree"]}, "message": data["message"],
                         "parents": [{"sha": p} for p in data["parents"]]}, {}
        tree = re.match(r"^/git/trees/([0-9a-f]+)$", rest)
        if method == "GET" and tree:
            files = self.trees.get(tree.group(1))
            if files is None:
                return 404, {"message": "Not Found"}, {}
            items = [{"path": p, "type": "blob", "sha": s, "mode": "100644"} for p, s in sorted(files.items())]
            if query.get("recursive"):
                dirs = sorted({"/".join(p.split("/")[:i]) for p in files for i in range(1, len(p.split("/")))})
                items += [{"path": d, "type": "tree", "mode": "040000"} for d in dirs]
            return 200, {"sha": tree.group(1), "tree": items, "truncated": False}, {}
        if method == "POST" and rest == "/git/blobs":
            data = base64.b64decode(body["content"]) if body.get("encoding") == "base64" else body["content"].encode()
            return 201, {"sha": self._blob(data)}, {}
        if method == "POST" and rest == "/git/trees":
            files = dict(self.trees.get(body.get("base_tree") or "", {}))
            for entry in body["tree"]:
                if "content" in entry:
                    files[entry["path"]] = self._blob(entry["content"].encode("utf-8"))
                elif entry.get("sha") is None:
                    if entry["path"] not in files:
                        return 422, {"message": "GitRPC::BadObjectState"}, {}
                    del files[entry["path"]]
                else:
                    if entry["sha"] not in self.blobs:
                        return 422, {"message": "tree.sha is not a valid blob"}, {}
                    files[entry["path"]] = entry["sha"]
            return 201, {"sha": self._tree(files)}, {}
        if method == "POST" and rest == "/git/commits":
            if body["tree"] not in self.trees or any(p not in self.commits for p in body.get("parents", [])):
                return 422, {"message": "Invalid tree or parent"}, {}
            sha = self._commit(body["tree"], body.get("parents", []), body["message"])
            return 201, {"sha": sha, "html_url": f"https://github.com/{repo['full_name']}/commit/{sha}"}, {}
        if method == "POST" and rest == "/git/refs":
            name = body["ref"].removeprefix("refs/heads/")
            if name in repo["refs"]:
                return 422, {"message": "Reference already exists"}, {}
            repo["refs"][name] = body["sha"]
            return 201, {"ref": body["ref"], "object": {"sha": body["sha"]}}, {}
        if method == "PATCH" and ref and rest.startswith("/git/refs/"):
            name = ref.group(1)
            if name not in repo["refs"]:
                return 422, {"message": "Reference does not exist"}, {}
            new = body["sha"]
            if not body.get("force") and repo["refs"][name] not in self.commits[new]["parents"]:
                return 422, {"message": "Update is not a fast forward"}, {}
            repo["refs"][name] = new
            return 200, {"ref": f"refs/heads/{name}", "object": {"sha": new}}, {}
        contents = re.match(r"^/contents/(.+)$", rest)
        if method == "PUT" and contents:
            branch = body.get("branch") or repo["default_branch"]
            head = repo["refs"].get(branch)
            files = dict(self.trees[self.commits[head]["tree"]]) if head else {}
            files[contents.group(1)] = self._blob(base64.b64decode(body["content"]))
            repo["refs"][branch] = self._commit(self._tree(files), [head] if head else [], body["message"])
            return 201, {"commit": {"sha": repo["refs"][branch]}}, {}
        return 404, {"message": "Not Found"}, {}

    def _repo_json(self, repo: Dict[str, Any], login: str) -> Dict[str, Any]:
        can_push = login == repo["owner"] or login in repo["collaborators"]
        return {"full_name": repo["full_name"], "name": repo["name"], "private": repo["private"],
                "default_branch": repo["default_branch"], "html_url": f"https://github.com/{repo['full_name']}",
                "owner": {"login": repo["owner"]}, "permissions": {"push": can_push, "pull": True}}
