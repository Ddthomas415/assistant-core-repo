from __future__ import annotations

import argparse

import os
from server.chat_service import process_turn


def run_chat_loop(*, resume_session_id: str | None = None, enable_wake_word: bool = False) -> None:
    """
    Assistant shell.

    All turn logic (routing, tool execution, session persistence,
    pending clarification/confirmation) lives in server.chat_service.
    This module is pure I/O: read input, call the service, print output.

    enable_wake_word: start background wake word listener (needs pyaudio + SpeechRecognition).
    """
    session_id: str | None = resume_session_id

    if resume_session_id:
        print(f"Assistant Shell — resuming session {resume_session_id}")
    else:
        print("Assistant Shell — new session")
    print("Type 'quit' to exit.\n")

    if enable_wake_word:
        try:
            from core.wake import WakeWordDetector  # noqa: PLC0415
            wake_phrase = os.getenv("WAKE_WORD", "jarvis")

            def _on_wake():
                print(f"\n[Wake word detected — listening...]")

            detector = WakeWordDetector(on_wake=_on_wake, wake_phrase=wake_phrase)
            if detector.start():
                print(f"Wake word active: say \"{wake_phrase}\" to activate\n")
            else:
                print(f"Wake word unavailable: {detector.error}\n")
        except Exception as e:
            print(f"Wake word init failed: {e}\n")

    while True:
        try:
            user_message = input("you> ").strip()
        except KeyboardInterrupt:
            print("\nGoodbye.")
            break
        except EOFError:
            print("\nGoodbye.")
            break

        if not user_message:
            continue

        if user_message.lower() in {"quit", "exit"}:
            print("Goodbye.")
            break

        turn = process_turn(session_id=session_id, message=user_message)

        # Pin the session for the rest of this conversation.
        session_id = turn.session_id

        print(f"\nassistant> {turn.assistant_message}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assistant shell")
    parser.add_argument(
        "--resume",
        metavar="SESSION_ID",
        default=None,
        help="Resume an existing session by ID.",
    )
    parser.add_argument(
        "--wake-word",
        action="store_true",
        default=False,
        help="Enable wake word detection (requires pyaudio + SpeechRecognition).",
    )
    args = parser.parse_args()
    run_chat_loop(resume_session_id=args.resume, enable_wake_word=args.wake_word)


if __name__ == "__main__":
    main()
