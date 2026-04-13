import signal
from .errors import ParseError, format_error


def run_with_timeout(seconds: int):
    """
    Decorator that raises TimeoutError if the wrapped function takes longer
    than `seconds` to complete.

    Uses SIGALRM (Unix only) rather than a forked subprocess. The fork-based
    approach deadlocks when called from inside a ProcessPoolExecutor worker:
    fork() copies the worker's locked logging handlers into the child, and any
    subsequent log write in the child blocks forever waiting for a lock that
    will never be released.

    SIGALRM fires in the same process, so there are no inherited locks and no
    deadlock risk. Workers are single-threaded, so signal delivery is reliable.
    """
    def decorator(func):
        def wraps(*args, **kwargs):
            def _handler(signum, frame):
                raise TimeoutError(format_error(
                    ParseError.TIMEOUT,
                    f"Took longer than {seconds} seconds"
                ))

            old_handler = signal.signal(signal.SIGALRM, _handler)
            signal.alarm(seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)          # cancel any pending alarm
                signal.signal(signal.SIGALRM, old_handler)  # restore previous handler

        return wraps
    return decorator
