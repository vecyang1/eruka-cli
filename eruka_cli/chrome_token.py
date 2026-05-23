from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChromeToken:
    token: str
    email: str | None
    tab_url: str


class ChromeTokenError(RuntimeError):
    pass


def _http_json(url: str, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _find_eurekaa_tab(cdp_url: str) -> dict[str, Any]:
    tabs = _http_json(f"{cdp_url.rstrip('/')}/json")
    for tab in tabs:
        url = tab.get("url") or ""
        if url.startswith("https://app.eurekaa.io/") and tab.get("webSocketDebuggerUrl"):
            return tab
    raise ChromeTokenError("No debuggable https://app.eurekaa.io/ tab found in Chrome.")


def load_token_from_chrome(cdp_url: str = "http://127.0.0.1:9222", timeout: float = 5.0) -> ChromeToken:
    try:
        return _load_token_from_direct_cdp(cdp_url=cdp_url, timeout=timeout)
    except Exception as direct_error:
        try:
            return _load_token_from_browser_harness(timeout=timeout)
        except Exception as harness_error:
            raise ChromeTokenError(
                f"Could not read Eurekaa API token from Chrome. Direct CDP failed: {direct_error}. "
                f"browser-harness failed: {harness_error}."
            ) from harness_error


def _load_token_from_direct_cdp(cdp_url: str, timeout: float) -> ChromeToken:
    try:
        import websocket
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ChromeTokenError("websocket-client is required for --from-chrome token access.") from exc

    tab = _find_eurekaa_tab(cdp_url)
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=timeout)
    try:
        expression = """
        (() => {
          const state = window.$nuxt && window.$nuxt.$store && window.$nuxt.$store.state;
          const userState = state && state.user;
          const token = userState && userState.API_TOKEN;
          const email = userState && userState.user && userState.user.email;
          return { token: token || null, email: email || null, href: location.href };
        })()
        """
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        }))
        payload = json.loads(ws.recv())
    finally:
        ws.close()

    value = payload.get("result", {}).get("result", {}).get("value") or {}
    token = value.get("token")
    if not token:
        raise ChromeTokenError("Eurekaa tab is present but no in-page API token was found.")
    return ChromeToken(token=token, email=value.get("email"), tab_url=value.get("href") or tab.get("url", ""))


def _load_token_from_browser_harness(timeout: float) -> ChromeToken:
    script = r'''
import json

targets = [tab for tab in list_tabs() if tab.get("url", "").startswith("https://app.eurekaa.io/")]
targets.sort(key=lambda tab: 0 if "/account" in tab.get("url", "") else 1)

if not targets:
    print(json.dumps({"error": "No https://app.eurekaa.io/ tab found"}))
else:
    last_error = None
    for target in targets:
        try:
            raw_state = js(
                "JSON.stringify((window.$nuxt && window.$nuxt.$store && window.$nuxt.$store.state && window.$nuxt.$store.state.user) || {})",
                target_id=target["targetId"],
            )
            user_state = json.loads(raw_state or "{}")
            token = user_state.get("API_TOKEN")
            user = user_state.get("user") or {}
            value = {
                "token": token or None,
                "email": user.get("email"),
                "href": target.get("url"),
            }
            if token:
                print(json.dumps(value))
                break
            last_error = "No API_TOKEN in Nuxt user state for " + target.get("url", "")
        except Exception as exc:
            last_error = str(exc)
    else:
        print(json.dumps({"error": last_error or "No Eurekaa API token found"}))
'''
    env = dict(os.environ)
    env.setdefault("BH_DOMAIN_SKILLS", "1")
    completed = subprocess.run(
        ["browser-harness"],
        input=script,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(timeout, 10.0),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise ChromeTokenError(completed.stderr.strip() or f"browser-harness exited {completed.returncode}")
    lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise ChromeTokenError("browser-harness did not return a JSON token payload.")
    value = json.loads(lines[-1])
    if value.get("error"):
        raise ChromeTokenError(value["error"])
    token = value.get("token")
    if not token:
        raise ChromeTokenError("Eurekaa tab is present but no in-page API token was found.")
    return ChromeToken(token=token, email=value.get("email"), tab_url=value.get("href") or "")
