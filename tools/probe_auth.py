"""验证设备码轮询：pending 时应该继续轮询，取消时应该干净退出。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import auth  # noqa: E402


def main() -> int:
    d = auth.begin()
    print("user_code =", d.user_code, "| uri =", d.verification_uri)

    state = {"n": 0}

    def on_status(msg: str) -> None:
        print("  状态:", msg, flush=True)

    def cancelled() -> bool:
        state["n"] += 1
        return state["n"] > 2

    t0 = time.time()
    try:
        auth.wait_for_account(d, on_status, cancelled)
    except auth.AuthError as exc:
        print(f"AuthError[{exc.code}] {str(exc)[:80]}")
    print(f"轮询 {state['n']} 次，用时 {time.time() - t0:.1f}s")

    # 顺带验证一个错误分支：拿假 device_code 走 token 端点
    try:
        auth._form(auth.TOKEN_URL, {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": auth.CLIENT_ID,
            "device_code": "not-a-real-code",
        })
    except auth.AuthError as exc:
        print(f"假 device_code -> code={exc.code!r} msg={str(exc)[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
