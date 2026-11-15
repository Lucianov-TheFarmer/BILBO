"""URLs opened by the user's browser, separate from container-internal API URLs."""

import os


def public_base_url() -> str:
    configured = os.getenv("BILBO_PUBLIC_BASE_URL", "").strip()
    return configured.rstrip("/") if configured else f"http://localhost:{os.getenv('BILBO_HOST_PORT', '8890')}"


def public_url(url: str) -> str:
    internal_browser_origin = "http://localhost:8890"
    if url.startswith(internal_browser_origin):
        return public_base_url() + url[len(internal_browser_origin):]
    return url


def launch_public_url(page, url: str):
    return page.launch_url(public_url(url))
