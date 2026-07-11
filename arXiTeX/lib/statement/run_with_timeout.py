"""
Cross-platform timeout helper.

The previous implementation used ``signal.SIGALRM``, which is Unix-only and
breaks on Windows. This version runs the work on a daemon thread and abandons it
if it overruns. Methods that shell out (the ``tex`` method) are also given the
timeout directly so their subprocess is killed rather than merely abandoned.
"""

import threading
from typing import Any, Callable

from .errors import ParseError, format_error


def run_with_timeout(seconds: int, func: Callable[..., Any], *args, **kwargs) -> Any:
    """Run ``func(*args, **kwargs)``, raising ``TimeoutError`` after ``seconds``.

    If ``seconds`` is falsy, the function is run directly with no timeout.
    """
    if not seconds or seconds <= 0:
        return func(*args, **kwargs)

    box: dict = {}

    def _target():
        try:
            box["value"] = func(*args, **kwargs)
        except BaseException as e:  # noqa: BLE001 - re-raised on the caller thread
            box["error"] = e

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(seconds)

    if thread.is_alive():
        raise TimeoutError(format_error(
            ParseError.TIMEOUT,
            f"Took longer than {seconds} seconds",
        ))

    if "error" in box:
        raise box["error"]
    return box.get("value")
