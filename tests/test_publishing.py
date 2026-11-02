"""What the PyPI publish depends on: the distribution name and the workflow.

The bare name `loci` on PyPI belongs to an unrelated project, so the
distribution is `loci-vault` while the import package and both commands stay
`loci`. These tests pin the two places where that difference can silently go
wrong: the metadata lookup, and the release workflow that publishes.
"""

import re
import tomllib
from pathlib import Path

import yaml

from loci import api

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())


def test_the_distribution_is_named_loci_vault():
    assert _pyproject()["project"]["name"] == "loci-vault"


def test_the_commands_and_import_package_keep_the_loci_name():
    scripts = _pyproject()["project"]["scripts"]

    assert set(scripts) == {"loci", "loci-mcp"}
    assert (REPO_ROOT / "src" / "loci" / "__init__.py").exists()


def test_app_version_reads_the_distribution_under_its_pypi_name():
    """version("loci") would raise for a loci-vault install and report
    "unknown" in the UI and /api/health."""
    assert api.app_version() == _pyproject()["project"]["version"]


def test_the_package_has_a_pypi_page_worth_showing():
    project = _pyproject()["project"]

    assert project["description"]
    assert project["readme"] == "README.md"
    assert "Source" in project["urls"]


def test_readme_links_use_absolute_urls_so_they_work_on_pypi():
    """PyPI shows the README out of context: a relative link is a 404."""
    readme = (REPO_ROOT / "README.md").read_text()
    targets = re.findall(r"(?<!!)\[[^\]]*\]\(([^)\s]+)", readme)

    assert targets
    relative = [t for t in targets if not t.startswith(("https://", "#"))]
    assert relative == []


def test_readme_images_use_absolute_urls_so_they_render_on_pypi():
    """PyPI shows the README out of context: a relative path is a broken image."""
    readme = (REPO_ROOT / "README.md").read_text()
    sources = re.findall(r'<img[^>]*\bsrc="([^"]+)"', readme)
    sources += re.findall(r"!\[[^\]]*\]\(([^)\s]+)", readme)

    assert sources
    relative = [s for s in sources if not s.startswith("https://")]
    assert relative == []


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def test_pypi_is_published_before_the_github_release_exists():
    """A missing or misnamed trusted publisher must fail before anything is
    public, not after a Release has already announced the version."""
    jobs = _workflow()["jobs"]

    assert jobs["publish-pypi"]["needs"] == "build"
    assert jobs["release"]["needs"] == "publish-pypi"


def test_only_the_release_job_may_write_to_the_repo():
    jobs = _workflow()["jobs"]

    assert _workflow()["permissions"] == {"contents": "read"}
    assert jobs["release"]["permissions"]["contents"] == "write"
    assert "contents" not in jobs["build"].get("permissions", {})
    assert "contents" not in jobs["publish-pypi"]["permissions"]


def test_only_the_publish_job_may_mint_an_identity_token():
    """Trusted publishing needs id-token: write. The build job runs repo code
    (tests, npm, the build), so it must not hold that permission."""
    jobs = _workflow()["jobs"]

    assert jobs["publish-pypi"]["permissions"]["id-token"] == "write"
    assert "id-token" not in jobs["build"].get("permissions", {})
    assert "id-token" not in jobs["release"].get("permissions", {})
    assert "id-token" not in _workflow().get("permissions", {})


def test_the_publish_job_uses_the_pypi_environment():
    environment = _workflow()["jobs"]["publish-pypi"]["environment"]

    assert environment["name"] == "pypi"
    assert environment["url"] == "https://pypi.org/p/loci-vault"


def test_the_publish_job_builds_nothing_and_ships_what_the_release_built():
    steps = _workflow()["jobs"]["publish-pypi"]["steps"]
    uses = [step.get("uses", "") for step in steps]

    assert any(u.startswith("actions/download-artifact@") for u in uses)
    assert any(u.startswith("pypa/gh-action-pypi-publish@") for u in uses)
    assert not any("run" in step for step in steps)


def test_every_action_in_the_publish_path_is_pinned_to_a_commit():
    """A tag can be moved; this job holds the right to publish the package."""
    jobs = _workflow()["jobs"]
    publish_actions = [
        step["uses"]
        for job in (jobs["build"], jobs["publish-pypi"], jobs["release"])
        for step in job["steps"]
        if step.get("uses", "").split("@")[0]
        in {
            "pypa/gh-action-pypi-publish",
            "actions/upload-artifact",
            "actions/download-artifact",
        }
    ]

    assert publish_actions
    for ref in publish_actions:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), ref


def test_the_distribution_metadata_is_checked_before_publishing():
    steps = _workflow()["jobs"]["build"]["steps"]
    runs = " ".join(step.get("run", "") for step in steps)

    assert "twine@" in runs and "check --strict" in runs


def test_twine_is_pinned_to_an_exact_version():
    """The build job makes what PyPI receives; it runs no floating tool."""
    runs = " ".join(
        step.get("run", "")
        for step in _workflow()["jobs"]["build"]["steps"]
    )

    assert re.search(r"uvx twine@\d+\.\d+\.\d+ check", runs)
