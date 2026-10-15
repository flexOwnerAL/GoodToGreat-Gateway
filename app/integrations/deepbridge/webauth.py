"""DeepBridge web authentication entry point."""

import sys

from app.integrations.deepbridge.engine.auth import (
    DEFAULT_PROFILE_DIR,
    DEFAULT_SESSION_FILE,
    login,
)


def main():
    print("=== DeepBridge WebAuth ===")
    print(f"Profile: {DEFAULT_PROFILE_DIR}")
    print(f"Session: {DEFAULT_SESSION_FILE}")

    try:
        session = login(
            profile_dir=DEFAULT_PROFILE_DIR,
            headless=False,
        )

        if session is None or not session.token:
            print("Login failed: no session token was captured.")
            return 1

        DEFAULT_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        session.save(DEFAULT_SESSION_FILE)

        print("DeepBridge session saved successfully.")
        print(f"Session path: {DEFAULT_SESSION_FILE}")
        return 0

    except KeyboardInterrupt:
        print("\nLogin cancelled.")
        return 130
    except Exception as exc:
        print(f"Login failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
