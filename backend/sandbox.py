"""
Sandboxed Verification and Preview
Runs a repository's own tests on a proposed change inside an isolated Modal
Sandbox: clone, install, test the original (baseline), apply the change,
test again, and report regressions. For web projects it can also serve the
changed app and return a temporary public preview URL.
"""

import base64
import re
import shlex

import modal

SANDBOX_APP = "devcopilot-sandboxes"
REPO_DIR = "/repo"
PREVIEW_PORT = 4173
TEST_TIMEOUT = 300
INSTALL_TIMEOUT = 480
PREVIEW_LIFETIME = 20 * 60   # seconds a preview stays reachable

SANDBOX_IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "curl", "ca-certificates", "build-essential")
    .run_commands(
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
        "apt-get install -y nodejs",
    )
    .pip_install("pytest")
)

PYTHON_INSTALL = r"""
pip install -q --upgrade pip >/dev/null 2>&1
if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]; then
  pip install -q -e ".[test]" 2>/dev/null || pip install -q -e ".[tests]" 2>/dev/null \
    || pip install -q -e ".[dev]" 2>/dev/null || pip install -q -e .
fi
for f in requirements.txt requirements-dev.txt requirements_dev.txt requirements-test.txt \
         test-requirements.txt requirements/tests.txt requirements/test.txt requirements/dev.txt; do
  [ -f "$f" ] && pip install -q -r "$f"
done
# PEP 735 dependency groups (pyproject [dependency-groups]), used by newer projects
for g in tests test dev; do pip install -q --group "$g" 2>/dev/null && break; done
pip install -q pytest
"""
PYTHON_TESTS = 'timeout {t} python -m pytest -q -p no:cacheprovider --tb=short -o addopts="" 2>&1 | tail -n 80; exit ${{PIPESTATUS[0]}}'
NODE_INSTALL = "npm ci --no-audit --no-fund || npm install --no-audit --no-fund"
NODE_TESTS = "CI=true timeout {t} npm test 2>&1 | tail -n 80; exit ${{PIPESTATUS[0]}}"

COUNT = re.compile(r"(\d+) (passed|passing|failed|failing|errors?|skipped|pending)")


def parse_counts(output: str) -> dict:
    """Pass/fail counts from pytest, jest/vitest or mocha output.

    Each count keeps its last reported value: pytest and jest print one final
    summary line, while mocha prints "N passing" and "N failing" separately.
    """
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for line in output.splitlines():
        if line.strip().startswith("Test Suites:"):
            continue  # jest's per-file summary; the "Tests:" line has the real counts
        for n, word in COUNT.findall(line):
            key = {"passing": "passed", "failing": "failed", "error": "errors", "pending": "skipped"}.get(word, word)
            counts[key] = int(n)
    return counts


class Verifier:
    def __init__(self, repo_url: str, token: str | None, preview: bool):
        self.repo_url = repo_url.rstrip("/").removesuffix(".git")
        self.token = token
        self.preview = preview
        self.sb = None
        self.keep_alive = False  # a running preview keeps the sandbox until its timeout

    # ── helpers ────────────────────────────────────────────
    def run(self, cmd: str, timeout: int = 120, workdir: str = REPO_DIR) -> tuple[int, str]:
        try:
            p = self.sb.exec("bash", "-lc", cmd, timeout=timeout, workdir=workdir)
            out = p.stdout.read() + p.stderr.read()
            code = p.wait()
        except Exception as e:  # exec timeouts and sandbox errors
            return 124, str(e)
        if self.token:
            out = out.replace(self.token, "***")
        return code, out

    def detect(self) -> dict:
        _, listing = self.run("ls -a; [ -f package.json ] && cat package.json", timeout=30)
        names = set(listing.split())
        pkg = listing[listing.find("{"):] if "package.json" in names else ""
        kind = "python" if names & {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"} else \
            "node" if "package.json" in names else "static" if "index.html" in names else "unknown"
        has_tests = kind == "node" and '"test"' in pkg and "no test specified" not in pkg
        return {"kind": kind, "pkg": pkg, "node_tests": has_tests}

    def tests(self, project: dict) -> dict:
        if project["kind"] == "python":
            code, out = self.run(PYTHON_TESTS.format(t=TEST_TIMEOUT), timeout=TEST_TIMEOUT + 30)
            ran = code != 5  # pytest: 5 = no tests collected
        elif project["kind"] == "node" and project["node_tests"]:
            code, out = self.run(NODE_TESTS.format(t=TEST_TIMEOUT), timeout=TEST_TIMEOUT + 30)
            ran = True
        else:
            return {"ran": False}
        counts = parse_counts(out)
        if code == 124:
            out += "\n(tests timed out)"
        return {"ran": ran and (sum(counts.values()) > 0 or code != 0), "exit_code": code,
                **counts, "output": out[-6000:]}

    def write_files(self, files: list[dict]):
        for f in files:
            path = shlex.quote(f"{REPO_DIR}/{f['path'].lstrip('/')}")
            # Stream the content through stdin (base64 keeps any bytes intact)
            p = self.sb.exec("bash", "-c", f"mkdir -p $(dirname {path}) && base64 -d > {path}", workdir=REPO_DIR)
            p.stdin.write(base64.b64encode(f["content"].encode("utf-8")).decode("ascii"))
            p.stdin.write_eof()
            p.stdin.drain()
            if p.wait() != 0:
                raise RuntimeError(f"Couldn't write {f['path']}: {p.stderr.read()[-300:]}")

    def syntax_check(self, files: list[dict]) -> list[str]:
        problems = []
        for f in files:
            path = shlex.quote(f["path"])
            if f["path"].endswith(".py"):
                code, out = self.run(f"python -m py_compile {path}", timeout=30)
            elif f["path"].endswith((".js", ".mjs", ".cjs")):
                code, out = self.run(f"node --check {path}", timeout=30)
            else:
                continue
            if code != 0:
                problems.append(f"{f['path']}: {out.strip()[-500:]}")
        return problems

    def start_preview(self, project: dict) -> str | None:
        pkg = project["pkg"]
        if project["kind"] == "static":
            serve = f"python -m http.server {PREVIEW_PORT} --directory {REPO_DIR}"
        elif project["kind"] == "node" and '"next"' in pkg:
            code, _ = self.run("npx next build", timeout=INSTALL_TIMEOUT)
            if code != 0:
                return None
            serve = f"npx next start -H 0.0.0.0 -p {PREVIEW_PORT}"
        elif project["kind"] == "node" and '"build"' in pkg:
            # Serve the production build: dev servers reject the tunnel's hostname
            code, _ = self.run("npm run build", timeout=INSTALL_TIMEOUT)
            if code != 0:
                return None
            _, out_dir = self.run("for d in dist build out public; do [ -f $d/index.html ] && echo $d && break; done")
            if not out_dir.strip():
                return None
            serve = f"python -m http.server {PREVIEW_PORT} --directory {REPO_DIR}/{out_dir.strip()}"
        else:
            return None

        self.sb.exec("bash", "-lc", f"{serve} > /tmp/preview.log 2>&1", workdir=REPO_DIR)
        code, _ = self.run(
            f"for i in $(seq 1 60); do curl -s -o /dev/null http://localhost:{PREVIEW_PORT} && exit 0; sleep 1; done; exit 1",
            timeout=80,
        )
        return self.sb.tunnels()[PREVIEW_PORT].url if code == 0 else None

    # ── pipeline ───────────────────────────────────────────
    def verify(self, files: list[dict]):
        """Yield progress events; the last has type "done"."""
        def stage(name, status, detail=None):
            return {"type": "stage", "stage": name, "status": status, "detail": detail}

        try:
            yield stage("sandbox", "running")
            app = modal.App.lookup(SANDBOX_APP, create_if_missing=True)
            self.sb = modal.Sandbox.create(
                app=app, image=SANDBOX_IMAGE, cpu=2, memory=4096,
                timeout=PREVIEW_LIFETIME if self.preview else 900,
                encrypted_ports=[PREVIEW_PORT] if self.preview else [],
            )
            yield stage("sandbox", "done")

            yield stage("clone", "running")
            url = self.repo_url
            if self.token:
                url = url.replace("https://", f"https://x-access-token:{self.token}@")
            code, out = self.run(f"git clone --depth 1 {shlex.quote(url + '.git')} {REPO_DIR}",
                                 timeout=180, workdir="/")
            if code != 0:
                yield stage("clone", "failed", out[-500:])
                yield {"type": "done", "verdict": "error", "summary": "Couldn't clone the repository."}
                return
            project = self.detect()
            yield stage("clone", "done", f"{project['kind']} project")

            yield stage("install", "running")
            install = PYTHON_INSTALL if project["kind"] == "python" else NODE_INSTALL if project["kind"] == "node" else "true"
            code, out = self.run(install, timeout=INSTALL_TIMEOUT)
            yield stage("install", "done" if code == 0 else "warning",
                        None if code == 0 else "Some dependencies failed to install: " + out.strip()[-300:])

            yield stage("baseline", "running")
            baseline = self.tests(project)
            yield stage("baseline", "done" if baseline["ran"] else "skipped",
                        f"{baseline['passed']} passed, {baseline['failed'] + baseline['errors']} failing"
                        if baseline["ran"] else "No test suite found")

            yield stage("apply", "running")
            self.write_files(files)
            syntax = self.syntax_check(files)
            yield stage("apply", "failed" if syntax else "done",
                        "; ".join(syntax) if syntax else f"{len(files)} file(s) applied")

            after = {"ran": False}
            if baseline["ran"]:
                yield stage("tests", "running")
                after = self.tests(project)
                yield stage("tests", "done", f"{after.get('passed', 0)} passed, "
                                             f"{after.get('failed', 0) + after.get('errors', 0)} failing")

            preview_url = None
            if self.preview:
                yield stage("preview", "running")
                preview_url = self.start_preview(project)
                yield stage("preview", "done" if preview_url else "skipped",
                            preview_url or "This project has no web app to preview")

            before_bad = baseline.get("failed", 0) + baseline.get("errors", 0)
            after_bad = after.get("failed", 0) + after.get("errors", 0)
            if syntax:
                verdict, summary = "fail", "The changed files have syntax errors."
            elif after["ran"] and after_bad > before_bad:
                verdict, summary = "fail", (f"{after_bad - before_bad} new failing test(s): "
                                            f"{after['passed']} passed, {after_bad} failing (was {before_bad}).")
            elif after["ran"]:
                verdict, summary = "pass", (f"No regressions: {after['passed']} tests passed"
                                            + (f", {after_bad} already failing before the change." if after_bad else "."))
            else:
                verdict, summary = "no_tests", "No test suite to run; the changed files compile."

            self.keep_alive = bool(preview_url)
            yield {
                "type": "done", "verdict": verdict, "summary": summary,
                "baseline": {k: v for k, v in baseline.items() if k != "output"},
                "after": {k: v for k, v in after.items() if k != "output"},
                "output": after.get("output") or baseline.get("output", ""),
                "syntax_errors": syntax,
                "preview_url": preview_url,
                "preview_minutes": PREVIEW_LIFETIME // 60 if preview_url else None,
            }
        except Exception as e:
            yield {"type": "done", "verdict": "error", "summary": f"Sandbox error: {e}"}
        finally:
            if self.sb is not None and not self.keep_alive:
                try:
                    self.sb.terminate()
                except Exception:
                    pass
