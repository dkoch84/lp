"""Shared fixtures for the browser tests.

Launching is shared because "which Chromium" differs per machine and getting it
wrong is silent: a fixture that insists on channel="chrome" SKIPS on a box with
only Playwright's bundled browser, so the browser tests quietly do not run and
the suite still reports green.
"""
import pytest


@pytest.fixture(scope="session")
def chromium():
    """A launched Chromium, preferring the system Chrome.

    The system Chrome is first so the tests exercise the browser the kiosk is
    actually driven from; the bundled build is the fallback so a machine without
    Chrome still runs them. Skips only when neither exists, and says which.
    """
    api = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright not installed (requirements-dev.txt)")

    with api.sync_playwright() as p:
        problems = []
        for label, kwargs in (("system Chrome", {"channel": "chrome"}),
                              ("bundled Chromium", {})):
            try:
                browser = p.chromium.launch(**kwargs)
            except Exception as e:
                problems.append(f"{label}: {str(e).splitlines()[0]}")
                continue
            yield browser
            browser.close()
            return
        pytest.skip("no usable browser (" + "; ".join(problems) + ")")
