from enum import Enum

class ParseError(Enum):
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"
    SYNTAX = "SYNTAX"
    DOWNLOAD = "DOWNLOAD"
    PLASTEX = "PLASTEX"
    VALIDATION = "VALIDATION"

def format_error(
    error_type: ParseError,
    message: str,
    max_message_length: int = 256
) -> str:
    """
    Formats an error message. Truncates the message if needed.

    Parameters
    ----------
    error_type : ParseError
        The general type of error.
    message : str
        The full error message.
    max_message_length : int, optional
        The maximum length of a displayed message. Truncates long messages and adds '...'. Default,
        256.

    Returns
    -------
    formatted_error : str
        The formatted error message
    """
    
    truncated_message = message if len(message) <= max_message_length \
        else message[:max_message_length] + "..."
    
    return f"[{error_type.value} ERROR] {truncated_message}"