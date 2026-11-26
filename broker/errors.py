"""Broker errors. Messages must never contain a secret: they are shown to the agent."""


class BrokerError(RuntimeError):
    """Raised with a masked, agent-safe message."""


def masked(exc: BaseException) -> str:
    """Agent-safe description of an unexpected exception: type only, never the message
    (library errors such as Playwright's echo their arguments, which may be secrets)."""
    if isinstance(exc, BrokerError):
        return str(exc)
    return f"unexpected {type(exc).__name__} (details suppressed)"
