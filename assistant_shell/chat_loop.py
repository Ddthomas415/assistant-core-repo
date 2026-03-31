from __future__ import annotations

from core.router import route_user_message
from core.types import PendingClarification, PendingConfirmation


def run_chat_loop() -> None:
    """
    First assistant shell slice.

    Thin shell only:
    - in-memory pending clarification / confirmation
    - routes through core.router
    - prints direct answers, clarification prompts, confirmation prompts,
      and visible tool previews
    - does not execute real tools yet
    """
    pending_clarification: PendingClarification | None = None
    pending_confirmation: PendingConfirmation | None = None

    print("Assistant Shell v1")
    print("Type 'quit' to exit.\n")

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

        route, policy = route_user_message(
            user_message,
            pending_clarification=pending_clarification,
            pending_confirmation=pending_confirmation,
        )

        pending_clarification = None
        pending_confirmation = None

        if route.kind == "answer":
            message = route.answer_text or "I don't have an answer yet."

        elif route.kind == "clarify":
            pending_clarification = PendingClarification(
                clarification_id="in-memory-clarification",
                created_at="now",
                expires_at="later",
                prompt=route.clarification_prompt or "Please clarify.",
                target=route.clarification_target or "user_intent",
                bound_user_request=user_message,
                allowed_reply_kinds=[route.clarification_target or "user_intent"],
            )
            message = route.clarification_prompt or "Please clarify."

        elif route.kind == "confirm":
            pending_confirmation = PendingConfirmation(
                confirmation_id="in-memory-confirmation",
                action_id="in-memory-action",
                created_at="now",
                expires_at="later",
                prompt=route.confirmation_prompt or "Please confirm.",
                requested_action=route.requested_action,
            )
            message = route.confirmation_prompt or "Please confirm."

        elif route.kind == "tool":
            if route.tool_request is not None:
                message = (
                    f"[{route.tool_request.user_facing_label}...]\n"
                    "Tool execution not wired yet in this first shell slice."
                )
            else:
                message = "[tool...]\nTool execution not wired yet."

        else:
            message = "Unknown route."

        if policy is not None:
            message = f"{message}\n\n[policy: {policy.kind}] {policy.reason}"

        print(f"\nassistant> {message}\n")


if __name__ == "__main__":
    run_chat_loop()
