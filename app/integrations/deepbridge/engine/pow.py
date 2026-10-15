"""
DeepSeekHashV1 proof-of-work adapter.

Executes the bundled upstream WebAssembly module through Node.js,
avoiding the unavailable Wasmtime native library on Android/Termux.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

ENGINE_DIR = Path(__file__).resolve().parent
WASM_PATH = ENGINE_DIR / "sha3_wasm_bg.wasm"
NODE_BRIDGE = ENGINE_DIR / "node_pow_bridge.mjs"
NODE = os.getenv("DEEPBRIDGE_NODE") or shutil.which("node")


class DeepSeekPow:
    def __init__(self, wasm_path: Path = WASM_PATH):
        self.wasm_path = Path(wasm_path)

        if not NODE:
            raise RuntimeError(
                "Node.js was not found. Install it in Termux with: pkg install nodejs"
            )

        if not self.wasm_path.is_file():
            raise FileNotFoundError(
                f"DeepSeek WASM module not found: {self.wasm_path}"
            )

        if not NODE_BRIDGE.is_file():
            raise FileNotFoundError(
                f"Node WASM bridge not found: {NODE_BRIDGE}"
            )

        # Verify that Node can load the module before handling requests.
        result = subprocess.run(
            [NODE, str(NODE_BRIDGE), "--inspect"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Node.js could not load the DeepSeek WASM module: "
                + (result.stderr.strip() or "unknown error")
            )

        try:
            info = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Node WASM bridge returned invalid inspection output"
            ) from exc

        if info.get("status") != "ok":
            raise RuntimeError("DeepSeek WASM module failed its load check")

    def solve(
        self,
        challenge: str,
        prefix: str,
        difficulty: float,
    ) -> Optional[int]:
        payload = {
            "challenge": challenge,
            "prefix": prefix,
            "difficulty": float(difficulty),
        }

        try:
            result = subprocess.run(
                [NODE, str(NODE_BRIDGE)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "DeepSeek PoW computation exceeded 180 seconds"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                "Node.js PoW computation failed: "
                + (result.stderr.strip() or "unknown error")
            )

        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Node.js PoW bridge returned invalid output"
            ) from exc

        answer = output.get("answer")
        if answer is None:
            return None

        if isinstance(answer, bool) or not isinstance(answer, int):
            raise RuntimeError("Node.js PoW bridge returned an invalid answer")

        return answer

    def make_header(self, challenge: dict) -> str:
        import base64

        prefix = f"{challenge['salt']}_{challenge['expire_at']}_"
        answer = self.solve(
            challenge["challenge"],
            prefix,
            challenge["difficulty"],
        )

        if answer is None:
            raise RuntimeError(
                "PoW solver returned no answer (challenge may have expired)"
            )

        payload = {
            "algorithm": challenge["algorithm"],
            "challenge": challenge["challenge"],
            "salt": challenge["salt"],
            "answer": answer,
            "signature": challenge["signature"],
            "target_path": challenge["target_path"],
        }

        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.b64encode(raw).decode("utf-8")
