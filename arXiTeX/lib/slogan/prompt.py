from pathlib import Path
from typing import Dict
from jinja2 import Environment, FileSystemLoader, StrictUndefined

def get_prompt(
    prompt_file: Path | str,
    context: Dict 
) -> str:
    """
    Retrieves and fills in a jinja2 ('.j2') prompt template.

    Parameters
    ----------
    prompt_file : Path | str
        Path to a jinja2 ('.j2') prompt template.
    context : Dict
        Dict of all contexts. Must match exactly the fields in the prompt file.

    Returns
    -------
    prompt : str
        The filled in prompt.
    """

    env = Environment(loader=FileSystemLoader("."), undefined=StrictUndefined)
    template = env.get_template(prompt_file)

    return template.render(context)