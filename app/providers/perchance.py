"""Perchance / URV AI Chat provider.

Perchance generators are browser-only — Cloudflare Turnstile guards the
endpoint and there is no REST API. We drive a real Chromium instance
through DrissionPage (3.2.x), open the chat page, and interact with the
chat DOM inside the generator iframe.

Design:
  * One long-lived Chromium process per Gateway instance (spawned via
    subprocess.Popen(start_new_session=True) so it survives the shell).
  * Per-request: type message into #user-input, press Enter, wait for
    the assistant's .message-content to appear, return the text.
  * Thread-safe via a per-instance Lock (DrissionPage is synchronous).

Caveats:
  * Termux-only Chrome flags are baked in (no-sandbox, headless=new).
  * Turnstile may or may not pass depending on IP/UA heuristics.
  * Perchance DOM can change without notice.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import time
import urllib.request
from typing import Any, AsyncIterator

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.providers.base import BaseProvider
from app.utils.tokens import usage_block

logger = logging.getLogger("goodtogreat.perchance")

_DEFAULT_MODELS = ["perchance:urv-ai-chat"]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        return "\n".join(
            str(p.get("text", ""))
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return str(content)


def _normalize_messages(messages: list[dict]) -> list[dict[str, str]]:
    """OpenAI messages → flat list of {role, content}."""
    return [
        {"role": str(m.get("role", "user")), "content": _content_text(m.get("content"))}
        for m in messages
    ]


def _build_prompt(messages: list[dict[str, str]]) -> str:
    """URV chat only takes one text input. Fold history into one prompt."""
    if len(messages) == 1 and messages[0]["role"] == "user":
        return messages[0]["content"]
    labels = {"system": "System", "user": "User", "assistant": "Assistant", "tool": "Tool"}
    lines = []
    for m in messages:
        role = labels.get(m["role"], m["role"].capitalize())
        lines.append(f"{role}: {m['content']}")
    return "\n\n".join(lines)


class PerchanceProvider(BaseProvider):
    name = "perchance"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._page = None
        self._chat_frame = None
        self._last_chat_html_len = 0

    # ---------------- browser lifecycle ----------------

    def _settings(self):
        return get_settings()

    def _chrome_binary(self) -> str:
        s = self._settings()
        path = str(getattr(s, "perchance_chrome_path", "") or "").strip()
        if path and os.path.isfile(path):
            return path
        # fallback to PATH
        import shutil as _sh
        for cand in ("chromium-browser", "chromium", "chrome"):
            w = _sh.which(cand)
            if w:
                return w
        raise RuntimeError(
            "Chromium not found. Set PERCHANCE_CHROME_PATH or install chromium."
        )

    def _ensure_browser(self):
        """Return a live ChromiumPage. Launch Chromium if needed."""
        if self._page is not None:
            try:
                _ = self._page.title  # cheap liveness probe
                return self._page
            except Exception:
                logger.info("perchance: stale page, reconnecting")
                self._page = None
                self._chat_frame = None

        s = self._settings()
        port = int(getattr(s, "perchance_port", 9333))
        udd = os.path.expanduser(str(getattr(s, "perchance_user_data_dir", "~/.cache/perchance-profile")))
        log_path = os.path.expanduser(str(getattr(s, "perchance_log_path", "~/.config/perchance/chrome.log")))
        os.makedirs(udd, exist_ok=True)
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

        # Kill any leftover browser we own.
        try:
            subprocess.run(["pkill", "-f", f"user-data-dir={udd}"], timeout=3)
        except Exception:
            pass
        try:
            subprocess.run(["pkill", "-f", f"remote-debugging-port={port}"], timeout=3)
        except Exception:
            pass
        time.sleep(1)

        chrome = self._chrome_binary()
        log_f = open(log_path, "wb")
        args = [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,800",
            "--user-agent=Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/155.0.8059.39 Mobile Safari/537.36",
            f"--user-data-dir={udd}",
            "about:blank",
        ]
        logger.info("perchance: spawning chromium pid pending, port=%d", port)
        self._proc = subprocess.Popen(
            args,
            stdout=log_f, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait for CDP.
        cdp_url = f"http://127.0.0.1:{port}/json/version"
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(1)
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"perchance: chromium exited early, rc={self._proc.returncode}. "
                    f"See {log_path}."
                )
            try:
                with urllib.request.urlopen(cdp_url, timeout=1) as r:
                    r.read()
                break
            except Exception:
                continue
        else:
            raise RuntimeError("perchance: chromium CDP did not come up in 20s")

        # Connect via DrissionPage.
        from DrissionPage import ChromiumPage
        self._page = ChromiumPage(f"127.0.0.1:{port}")

        url = str(getattr(s, "perchance_generator_url", "https://perchance.org/urv-ai-chat"))
        logger.info("perchance: opening %s", url)
        self._page.get(url)

        # Wait for iframe and Turnstile bypass.
        self._wait_for_chat_frame(timeout=30)
        return self._page

    def _wait_for_chat_frame(self, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(1)
            try:
                title = self._page.title or ""
            except Exception:
                title = ""
            if "just a moment" in title.lower() or "checking" in title.lower():
                continue
            fr = self._find_chat_frame()
            if fr is not None:
                try:
                    inp = fr.ele("#user-input", timeout=2)
                    if inp is not None:
                        self._chat_frame = fr
                        logger.info("perchance: chat frame ready")
                        return
                except Exception:
                    pass
        raise RuntimeError("perchance: chat iframe not ready in time")

    def _find_chat_frame(self):
        if self._page is None:
            return None
        marker = str(getattr(self._settings(), "perchance_generator", "urv-ai-chat"))
        try:
            for fr in self._page.get_frames():
                try:
                    if marker in (fr.url or ""):
                        return fr
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _get_chat_frame(self):
        fr = self._chat_frame or self._find_chat_frame()
        if fr is None:
            # try to reload once
            self._page = None
            self._ensure_browser()
            fr = self._chat_frame or self._find_chat_frame()
        if fr is None:
            raise RuntimeError("perchance: chat iframe lost")
        return fr

    # ---------------- core chat ----------------

    def _send_and_wait(self, prompt: str, timeout: float) -> str:
        with self._lock:
            self._ensure_browser()
            fr = self._get_chat_frame()

            # count messages before
            try:
                before = len(fr.eles("css:.message") or [])
            except Exception:
                before = 0

            # find input
            inp = fr.ele("#user-input", timeout=5)
            if inp is None:
                raise RuntimeError("perchance: #user-input disappeared")

            # focus + clear
            try:
                inp.click()
            except Exception:
                pass
            time.sleep(0.2)
            try:
                inp.clear()
            except Exception:
                # fallback: select-all + delete
                try:
                    inp.input(["\ue009", "a"])  # ctrl+a
                    inp.input("\ue003")          # delete
                except Exception:
                    pass

            # type + enter
            try:
                inp.input(prompt)
            except Exception as exc:
                raise RuntimeError(f"perchance: input failed: {exc}") from exc
            time.sleep(0.3)
            try:
                inp.input("\n")
            except Exception as exc:
                raise RuntimeError(f"perchance: enter failed: {exc}") from exc

            # wait for reply with ACTUAL content, not just the role badge
            deadline = time.time() + timeout
            last_count = before
            reply_text = None
            while time.time() < deadline:
                time.sleep(1)
                try:
                    cur_msgs = len(fr.eles("css:.message") or [])
                except Exception:
                    cur_msgs = last_count
                last_count = cur_msgs
                if cur_msgs < before + 2:
                    continue
                # message arrived — try to extract real content
                reply_text = self._try_extract_reply(fr, before)
                if reply_text:
                    # extra settle to catch trailing tokens
                    time.sleep(0.8)
                    reply_text = self._try_extract_reply(fr, before) or reply_text
                    break

            if not reply_text:
                raise RuntimeError(
                    f"perchance: no meaningful reply in {timeout}s "
                    f"(messages {before}→{last_count})"
                )

            return reply_text

    # ---------------- reply extraction ----------------

    _ROLE_NAMES = {"URV", "Assistant", "Bot", "AI", "System", "User"}

    def _try_extract_reply(self, fr, before_count=0):
        contents = []
        try:
            contents = fr.eles("css:.message-content") or []
        except Exception:
            contents = []

        for el in reversed(contents):
            try:
                parent = el.parent()
                pcls = (parent.attr("class") or "").lower() if parent else ""
                if "user" in pcls:
                    continue
                raw = (el.text or "").strip()
                if not raw:
                    continue
                lines = raw.split("\n", 1)
                if len(lines) >= 2:
                    role = lines[0].strip()
                    body = lines[1].strip()
                    if role in self._ROLE_NAMES:
                        if body:
                            return body
                        continue
                    return raw
                single = lines[0].strip()
                if single in self._ROLE_NAMES:
                    continue
                if len(single) < 2:
                    continue
                return single
            except Exception:
                continue

        try:
            msgs = fr.eles("css:.message") or []
        except Exception:
            msgs = []

        for el in reversed(msgs):
            try:
                cls = (el.attr("class") or "").lower()
                if "user" in cls:
                    continue
                raw = (el.text or "").strip()
                if not raw:
                    continue
                lines = raw.split("\n", 1)
                if len(lines) >= 2:
                    role = lines[0].strip()
                    body = lines[1].strip()
                    if role in self._ROLE_NAMES and body:
                        return body
                single = lines[0].strip() if lines else ""
                if single in self._ROLE_NAMES:
                    continue
                if len(single) >= 2:
                    return single
            except Exception:
                continue

        return None

    # ---------------- BaseProvider API ----------------

    async def list_models(self) -> list[dict[str, Any]]:
        s = self._settings()
        if not getattr(s, "perchance_enabled", False):
            return []
        now = int(time.time())
        return [
            {"id": m, "object": "model", "created": now, "owned_by": "perchance"}
            for m in _DEFAULT_MODELS
        ]

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> dict[str, Any]:
        normalized = _normalize_messages(messages)
        prompt = _build_prompt(normalized)
        timeout = float(getattr(self._settings(), "perchance_timeout_seconds", 120.0))

        try:
            content = await asyncio.wait_for(
                run_in_threadpool(self._send_and_wait, prompt, timeout),
                timeout=timeout + 15,
            )
        except asyncio.TimeoutError:
            logger.warning("perchance generate timeout")
            raise
        except Exception as exc:
            logger.warning("perchance generate failed: %s", exc)
            raise

        prompt_str = " ".join(m["content"] for m in normalized)
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage_block(prompt_str, content),
        }

    async def stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> AsyncIterator[str]:
        result = await self.generate(model, messages, **options)
        content = result["choices"][0]["message"]["content"]
        chunk = 64
        for off in range(0, len(content), chunk):
            yield content[off:off + chunk]

    async def health_check(self) -> dict[str, Any]:
        s = self._settings()
        if not getattr(s, "perchance_enabled", False):
            return {"enabled": False}
        try:
            chrome = self._chrome_binary()
        except Exception as exc:
            return {"enabled": True, "reachable": False, "error": str(exc)}
        alive = self._proc is not None and self._proc.poll() is None
        return {
            "enabled": True,
            "reachable": True,
            "chrome": chrome,
            "browser_running": alive,
            "note": "lazy init — browser starts on first request",
        }

    def __del__(self):
        try:
            if self._proc is not None and self._proc.poll() is None:
                self._proc.terminate()
        except Exception:
            pass
