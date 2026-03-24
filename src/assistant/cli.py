from __future__ import annotations

import argparse
from pathlib import Path

from assistant.engine import Engine
from assistant.session import SessionNotFoundError, SessionStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Terminal-first private assistant core")
    parser.add_argument(
        "--session-dir",
        default=".assistant_sessions",
        help="Directory for session files",
    )
    parser.add_argument(
        "--resume",
        help="Resume a previous session by session ID",
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help="Optional workspace root used for filesystem boundary validation",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    store = SessionStore(Path(args.session_dir))

    if args.resume:
        try:
            state = store.load(args.resume)
        except SessionNotFoundError as exc:
            raise SystemExit(f"Resume failed: {exc}")
    else:
        state = store.create()

    engine = Engine(workspace_root=args.workspace_root)

    store.save(state)

    print(f"Session: {state.session_id}")
    if args.workspace_root:
        print(f"Workspace root: {args.workspace_root}")
    print("Assistant ready. Type 'exit' or 'quit' to stop.")

    while True:
        try:
            user_input = input("> ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            break

        if user_input.strip().lower() in {"exit", "quit"}:
            break

        result = engine.handle_turn(state, user_input)
        print(result.rendered_output)
        store.save(state)


if __name__ == "__main__":
    main()
