from multiprocessing import get_context
import queue as queue_mod
from .errors import ParseError, format_error

def _timeout_handler(queue, func, args, kwargs):
    try:
        queue.put(("ok", func(*args, **kwargs)))
    except BaseException as e:
        queue.put(("err", (type(e).__name__, str(e))))

def run_with_timeout(seconds: int):
    def decorator(func):
        def wraps(*args, **kwargs):
            ctx = get_context("fork")
            q = ctx.Queue()
            p = ctx.Process(target=_timeout_handler, args=(q, func, args, kwargs))
            p.start()
            p.join(timeout=seconds)

            if p.is_alive():
                p.terminate()
                p.join()
                raise TimeoutError(format_error(
                    ParseError.TIMEOUT,
                    f"Took longer than {seconds} seconds"
                ))
            
            try:
                tag, payload = q.get_nowait()
            except queue_mod.Empty:
                raise RuntimeError(format_error(
                    ParseError.UNKNOWN,
                    "Child process exited without returning"
                ))

            if tag == "err":
                _, msg = payload
                raise RuntimeError(msg)

            return payload

        return wraps
    return decorator