"""Noxfile for the robust-python-demo project."""

import os
import shlex

from pathlib import Path
from textwrap import dedent
from typing import List

import nox
from nox.command import CommandFailed
from nox.sessions import Session


nox.options.default_venv_backend = "uv"

# Logic that helps avoid metaprogramming in cookiecutter-robust-python
MIN_PYTHON_VERSION_SLUG: int = int("3.9".lstrip("3."))
MAX_PYTHON_VERSION_SLUG: int = int("3.13".lstrip("3."))

PYTHON_VERSIONS: List[str] = [
    f"3.{VERSION_SLUG}" for VERSION_SLUG in range(MIN_PYTHON_VERSION_SLUG, MAX_PYTHON_VERSION_SLUG + 1)
]
DEFAULT_PYTHON_VERSION: str = PYTHON_VERSIONS[-1]

REPO_ROOT: Path = Path(__file__).parent.resolve()
SCRIPTS_FOLDER: Path = REPO_ROOT / "scripts"
CRATES_FOLDER: Path = REPO_ROOT / "rust"

PROJECT_NAME: str = "robust-python-demo"
PACKAGE_NAME: str = "robust_python_demo"
GITHUB_USER: str = "56kyle"

ENV: str = "env"
FORMAT: str = "format"
LINT: str = "lint"
TYPE: str = "type"
TEST: str = "test"
COVERAGE: str = "coverage"
SECURITY: str = "security"
PERF: str = "perf"
DOCS: str = "docs"
BUILD: str = "build"
RELEASE: str = "release"
CI: str = "ci"
PYTHON: str = "python"
RUST: str = "rust"


@nox.session(python=None, name="setup-git", tags=[ENV])
def setup_git(session: Session) -> None:
    """Set up the git repo for the current project."""
    session.run(
        "python", SCRIPTS_FOLDER / "setup-git.py", REPO_ROOT, external=True
    )


@nox.session(python=None, name="setup-venv", tags=[ENV])
def setup_venv(session: Session) -> None:
    """Set up the virtual environment for the current project."""
    session.run("python", SCRIPTS_FOLDER / "setup-venv.py", REPO_ROOT, "-p", PYTHON_VERSIONS[0], external=True)



@nox.session(python=DEFAULT_PYTHON_VERSION, name="pre-commit", tags=[CI])
def precommit(session: Session) -> None:
    """Lint using pre-commit."""
    args: list[str] = session.posargs or ["run", "--all-files", "--hook-stage=manual", "--show-diff-on-failure"]

    session.log("Installing pre-commit dependencies...")
    session.install("-e", ".", "--group", "dev")

    session.run("pre-commit", *args)
    if args and args[0] == "install":
        activate_virtualenv_in_precommit_hooks(session)


@nox.session(python=DEFAULT_PYTHON_VERSION, name="format-python", tags=[FORMAT, PYTHON])
def format_python(session: Session) -> None:
    """Run Python code formatter (Ruff format)."""
    session.log("Installing formatting dependencies...")
    session.install("-e", ".", "--group", "dev")

    session.log(f"Running Ruff formatter check with py{session.python}.")
    session.run("ruff", "format", *session.posargs)


@nox.session(python=DEFAULT_PYTHON_VERSION, name="lint-python", tags=[LINT, PYTHON])
def lint_python(session: Session) -> None:
    """Run Python code linters (Ruff check, Pydocstyle rules)."""
    session.log("Installing linting dependencies...")
    session.install("-e", ".", "--group", "dev")

    session.log(f"Running Ruff check with py{session.python}.")
    session.run("ruff", "check", "--fix", "--verbose")


@nox.session(python=PYTHON_VERSIONS, name="typecheck", tags=[TYPE, PYTHON, CI])
def typecheck(session: Session) -> None:
    """Run static type checking (Pyright) on Python code."""
    session.log("Installing type checking dependencies...")
    session.install("-e", ".", "--group", "dev")

    session.log(f"Running Pyright check with py{session.python}.")
    session.run("pyright")


@nox.session(python=DEFAULT_PYTHON_VERSION, name="security-python", tags=[SECURITY, PYTHON, CI])
def security_python(session: Session) -> None:
    """Run code security checks (Bandit) on Python code."""
    session.log("Installing security dependencies...")
    session.install("-e", ".", "--group", "dev")

    session.log(f"Running Bandit static security analysis with py{session.python}.")
    session.run("bandit", "-r", PACKAGE_NAME, "-c", "bandit.yml", "-ll")

    session.log(f"Running pip-audit dependency security check with py{session.python}.")
    session.run("pip-audit")


@nox.session(python=PYTHON_VERSIONS, name="tests-python", tags=[TEST, PYTHON, CI])
def tests_python(session: Session) -> None:
    """Run the Python test suite (pytest with coverage)."""
    session.log("Installing test dependencies...")
    session.install("-e", ".", "--group", "dev")

    session.log(f"Running test suite with py{session.python}.")
    test_results_dir = Path("test-results")
    test_results_dir.mkdir(parents=True, exist_ok=True)
    junitxml_file = test_results_dir / f"test-results-py{session.python}.xml"

    session.run(
        "pytest",
        "--cov={}".format(PACKAGE_NAME),
        "--cov-report=xml",
        f"--junitxml={junitxml_file}",
        "tests/"
    )


@nox.session(python=DEFAULT_PYTHON_VERSION, name="docs-build", tags=[DOCS, BUILD])
def docs_build(session: Session) -> None:
    """Build the project documentation (Sphinx)."""
    session.log("Installing documentation dependencies...")
    session.install("-e", ".", "--group", "dev")

    session.log(f"Building documentation with py{session.python}.")
    docs_build_dir = Path("docs") / "_build" / "html"

    session.log(f"Cleaning build directory: {docs_build_dir}")
    session.run("sphinx-build", "-b", "html", "docs", str(docs_build_dir), "-E")

    session.log("Building documentation.")
    session.run("sphinx-build", "-b", "html", "docs", str(docs_build_dir), "-W")


@nox.session(python=DEFAULT_PYTHON_VERSION, name="build-python", tags=[BUILD, PYTHON])
def build_python(session: Session) -> None:
    """Build sdist and wheel packages (uv build)."""
    session.log("Installing build dependencies...")
    # Sync core & dev deps are needed for accessing project source code.
    session.install("-e", ".", "--group", "dev")

    session.log(f"Building sdist and wheel packages with py{session.python}.")
    session.run("uv", "build", "--sdist", "--wheel", "--outdir", "dist/", external=True)
    session.log("Built packages in ./dist directory:")
    for path in Path("dist/").glob("*"):
        session.log(f"- {path.name}")


@nox.session(python=DEFAULT_PYTHON_VERSION, name="build-container", tags=[BUILD])
def build_container(session: Session) -> None:
    """Build the Docker container image.

    Requires Docker or Podman installed and running on the host.
    Ensures core project dependencies are synced in the current environment
    *before* the build context is prepared.
    """
    session.log("Building application container image...")
    try:
        session.run("docker", "info", success_codes=[0], external=True, silent=True)
        container_cli = "docker"
    except CommandFailed:
        try:
            session.run("podman", "info", success_codes=[0], external=True, silent=True)
            container_cli = "podman"
        except CommandFailed:
            session.log("Neither Docker nor Podman command found. Please install a container runtime.")
            session.skip("Container runtime not available.")

    current_dir: Path = Path.cwd()
    session.log(f"Ensuring core dependencies are synced in {current_dir.resolve()} for build context...")
    session.run("-e", ".")

    session.log(f"Building Docker image using {container_cli}.")
    project_image_name = PACKAGE_NAME.replace("_", "-").lower()
    session.run(container_cli, "build", str(current_dir), "-t", f"{project_image_name}:latest", "--progress=plain", external=True)

    session.log(f"Container image {project_image_name}:latest built locally.")


@nox.session(python=DEFAULT_PYTHON_VERSION, name="publish-python", tags=[RELEASE])
def publish_python(session: Session) -> None:
    """Publish sdist and wheel packages to PyPI via uv publish.

    Requires packages to be built first (`nox -s build-python` or `nox -s build`).
    Requires TWINE_USERNAME/TWINE_PASSWORD or TWINE_API_KEY environment variables set (usually in CI).
    """
    session.install("-e", ".", "--group", "dev")

    session.log("Checking built packages with Twine.")
    session.run("twine", "check", "dist/*")

    session.log("Publishing packages to PyPI.")
    session.run("uv", "publish", "dist/*", external=True)


@nox.session(venv_backend="none", tags=[RELEASE])
def release(session: Session) -> None:
    """Run the release process using Commitizen.

    Requires uvx in PATH (from uv install). Requires Git. Assumes Conventional Commits.
    Optionally accepts increment (major, minor, patch) after '--'.
    """
    session.log("Running release process using Commitizen...")
    session.install("-e", ".", "--group", "dev")

    try:
        session.run("git", "version", success_codes=[0], external=True, silent=True)
    except CommandFailed:
        session.log("Git command not found. Commitizen requires Git.")
        session.skip("Git not available.")

    session.log("Checking Commitizen availability via uvx.")
    session.run("cz", "--version", success_codes=[0])

    increment = session.posargs[0] if session.posargs else None
    session.log(
        "Bumping version and tagging release (increment: %s).",
        increment if increment else "default",
    )

    cz_bump_args = ["uvx", "cz", "bump", "--changelog"]

    if increment:
         cz_bump_args.append(f"--increment={increment}")

    session.log("Running cz bump with args: %s", cz_bump_args)
    session.run(*cz_bump_args, success_codes=[0, 1], external=True)

    session.log("Version bumped and tag created locally via Commitizen/uvx.")
    session.log(
        "IMPORTANT: Push commits and tags to remote (`git push --follow-tags`) to trigger CD pipeline."
    )


@nox.session(venv_backend="none")
def tox(session: Session) -> None:
    """Run the 'tox' test matrix.

    Requires uvx in PATH. Requires tox.ini file.
    Useful for specific ecosystem conventions (e.g., pytest plugins,
    cookiecutter-driven matrix testing).
    Accepts tox args after '--' (e.g., `nox -s tox -- -e py39`).
    """
    session.log("Running Tox test matrix via uvx...")
    session.install("-e", ".", "--group", "dev")

    tox_ini_path = Path("tox.ini")
    if not tox_ini_path.exists():
        session.log("tox.ini file not found at %s. Tox requires this file.", str(tox_ini_path))
        session.skip("tox.ini not present.")

    session.log("Checking Tox availability via uvx.")
    session.run("tox", "--version", success_codes=[0])

    session.run("tox", *session.posargs)


@nox.session(python=DEFAULT_PYTHON_VERSION, tags=[COVERAGE])
def coverage(session: Session) -> None:
    """Collect and report coverage.

    Requires tests to have been run with --cov and --cov-report=xml across matrix
    (e.g., via `nox -s test-python`).
    """
    session.log("Collecting and reporting coverage across all test runs.")
    session.log("Note: Ensure 'nox -s test-python' was run across all desired Python versions first to generate coverage data.")

    session.log("Installing dependencies for coverage report session...")
    session.install("-e", ".", "--group", "dev")

    coverage_combined_file: Path = Path.cwd() / ".coverage"

    session.log("Combining coverage data.")
    try:
        session.run("coverage", "combine")
        session.log(f"Combined coverage data into {coverage_combined_file.resolve()}")
    except CommandFailed as e:
        if e.returncode == 1:
             session.log("No coverage data found to combine. Run tests first with coverage enabled.")
        else:
             session.error(f"Failed to combine coverage data: {e}")
        session.skip("Could not combine coverage data.")

    session.log("Generating HTML coverage report.")
    coverage_html_dir = Path("coverage-html")
    session.run("coverage", "html", "--directory", str(coverage_html_dir))

    session.log("Running terminal coverage report.")
    session.run("coverage", "report")

    session.log(f"Coverage reports generated in ./{coverage_html_dir} and terminal.")


def activate_virtualenv_in_precommit_hooks(session: Session) -> None:
    """Activate virtualenv in hooks installed by pre-commit.

    This function patches git hooks installed by pre-commit to activate the
    session's virtual environment. This allows pre-commit to locate hooks in
    that environment when invoked from git.

    Args:
        session: The Session object.
    """
    assert session.bin is not None  # nosec

    # Only patch hooks containing a reference to this session's bindir. Support
    # quoting rules for Python and bash, but strip the outermost quotes so we
    # can detect paths within the bindir, like <bindir>/python.
    bindirs = [
        bindir[1:-1] if bindir[0] in "'\"" else bindir for bindir in (repr(session.bin), shlex.quote(session.bin))
    ]

    virtualenv = session.env.get("VIRTUAL_ENV")
    if virtualenv is None:
        return

    headers = {
        # pre-commit < 2.16.0
        "python": f"""\
            import os
            os.environ["VIRTUAL_ENV"] = {virtualenv!r}
            os.environ["PATH"] = os.pathsep.join((
                {session.bin!r},
                os.environ.get("PATH", ""),
            ))
            """,
        # pre-commit >= 2.16.0
        "bash": f"""\
            VIRTUAL_ENV={shlex.quote(virtualenv)}
            PATH={shlex.quote(session.bin)}"{os.pathsep}$PATH"
            """,
        # pre-commit >= 2.17.0 on Windows forces sh shebang
        "/bin/sh": f"""\
            VIRTUAL_ENV={shlex.quote(virtualenv)}
            PATH={shlex.quote(session.bin)}"{os.pathsep}$PATH"
            """,
    }

    hookdir: Path = Path(".git") / "hooks"
    if not hookdir.is_dir():
        return

    for hook in hookdir.iterdir():
        if hook.name.endswith(".sample") or not hook.is_file():
            continue

        if not hook.read_bytes().startswith(b"#!"):
            continue

        text: str = hook.read_text()

        if not any((Path("A") == Path("a") and bindir.lower() in text.lower()) or bindir in text for bindir in bindirs):
            continue

        lines: list[str] = text.splitlines()

        for executable, header in headers.items():
            if executable in lines[0].lower():
                lines.insert(1, dedent(header))
                hook.write_text("\n".join(lines))
                break
