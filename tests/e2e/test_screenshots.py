"""
tests/e2e/test_screenshots.py
Captures the README screenshots from the real app.

Not part of the normal suite — every spec here is skipped unless
LOCI_CAPTURE_SCREENSHOTS=1 is set. Run it with:

    make screenshots

These are **captures, not assertions**. Visual regression is deliberately out of
scope (see README.md "Not covered yet") because the design system animates, so
nothing here diffs an image against a baseline. The waits below exist to make a
shot look settled, not to prove anything about the app.

Images land in docs/images/ and are committed, so the README renders on GitHub
without anyone having to run this.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LOCI_CAPTURE_SCREENSHOTS") != "1",
    reason="screenshot capture is opt-in — run `make screenshots`",
)

REPO_ROOT = Path(__file__).resolve().parents[3]
IMAGE_DIR = REPO_ROOT / "docs" / "images"

# Deliberately a plain node with no asset. The asset-bearing overlay note
# (e2e00002) renders its resolved location as an absolute path, which under
# pytest is a tmp_path_factory directory containing the local username — not
# something to commit into a public README. Its body is also test scaffolding
# prose. This one reads like a real vault node.
DETAIL_UID = "ddd00001"

# Palette query. Broad on purpose — a single-hit search leaves the results panel
# mostly empty. PALETTE_WAIT_UID must be among the matches: the palette shows
# recent nodes until the debounce resolves, so waiting on "any result" would
# shoot the recent list instead (trap 3 in the README).
PALETTE_QUERY = "python"
PALETTE_WAIT_UID = "eee00001"

# Force-simulation settle time. GraphView decays `alphaRef` per frame with no
# "done" signal to wait on, so this is a plain sleep — long enough that the
# layout has stopped visibly moving before the shutter.
GRAPH_SETTLE_MS = 3500

# Committed image width. Captured at 2x this and resampled down — see _shoot.
VIEWPORT_WIDTH = 1440


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Fixed 2x viewport so the committed images are crisp and consistent."""
    return {
        **browser_context_args,
        "viewport": {"width": VIEWPORT_WIDTH, "height": 900},
        "device_scale_factor": 2,
    }


@pytest.fixture(scope="session", autouse=True)
def image_dir() -> Path:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGE_DIR


def _shoot(page, name: str) -> None:
    """
    Capture at 2x, then downscale to VIEWPORT_WIDTH and keep 24-bit colour.

    Shooting at 2x and resampling down supersamples the text, so the committed
    1440px image is sharper than a native 1x capture at a third of the bytes of
    the raw 2x one.

    Palette quantization was tried here and rejected: the design system's
    background is a wide, subtle dark-blue gradient that eats the whole 256-slot
    palette, leaving the saturated per-type dots to collapse into indistinct
    grey. Type colour is load-bearing in this UI, so these stay 24-bit.
    """
    try:
        from PIL import Image
    except ModuleNotFoundError:  # pragma: no cover - tooling guard
        pytest.fail(
            "Pillow is needed to downscale the captures — run `make screenshots`, "
            "which supplies it via `uv run --with pillow`.",
            pytrace=False,
        )

    path = IMAGE_DIR / f"{name}.png"
    page.screenshot(path=str(path))

    with Image.open(path) as im:
        if im.width > VIEWPORT_WIDTH:
            height = round(im.height * VIEWPORT_WIDTH / im.width)
            im = im.convert("RGB").resize(
                (VIEWPORT_WIDTH, height), Image.LANCZOS
            )
            im.save(path, optimize=True)

    print(f"  wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size // 1024}K)")


def test_capture_vault_index(app_page):
    """The default view: type filter bar, tag rail, node list."""
    app_page.wait_for_selector("[data-testid='rail-tag']")
    _shoot(app_page, "vault-index")


def test_capture_node_detail(app_page):
    """A node open in the reader — frontmatter grid and rendered body."""
    app_page.click(f"[data-testid='node-row'][data-uid='{DETAIL_UID}']")
    app_page.wait_for_selector(f"[data-testid='node-detail'][data-uid='{DETAIL_UID}']")
    app_page.wait_for_selector("[data-testid='node-frontmatter']")
    app_page.wait_for_selector("[data-testid='node-body']")
    _shoot(app_page, "node-detail")


def test_capture_graph_view(app_page):
    """The force-directed graph. Paused with space once settled, then shot."""
    app_page.keyboard.press("g")
    app_page.wait_for_selector("[data-testid='graph-node']")
    app_page.wait_for_timeout(GRAPH_SETTLE_MS)
    app_page.keyboard.press(" ")  # pause the simulation so the frame is stable
    app_page.wait_for_timeout(200)
    _shoot(app_page, "graph-view")


def test_capture_command_palette(app_page):
    """Cmd-K search. Waits on the specific uid — see trap 3 in the README."""
    app_page.keyboard.press("Meta+k")
    app_page.wait_for_selector("[data-testid='command-palette']")
    app_page.fill("[data-testid='palette-input']", PALETTE_QUERY)
    app_page.wait_for_selector(
        f"[data-testid='palette-result'][data-uid='{PALETTE_WAIT_UID}']"
    )
    _shoot(app_page, "command-palette")
