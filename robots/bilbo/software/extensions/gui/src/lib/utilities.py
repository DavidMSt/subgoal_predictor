from typing import Set, Any

from core.utils.logging_utils import Logger


def check_for_spaces(string):
    return ' ' in string


def check_id(id_, allowed_special_characters: list = None) -> bool:
    if allowed_special_characters is None:
        allowed_special_characters = []

    allowed_special_characters.append('_')  # Allow underscore by default

    # 1. Check if the ID is a string
    if not isinstance(id_, str):
        return False

    # 2. Check if the ID is not empty
    if not id_:
        return False

    # 3. Check if there are spaces in the ID
    if check_for_spaces(id_):
        return False

    # 4. Check if the ID starts with a slash
    if id_.startswith('/'):
        return False

    # 5. Check if the ID contains any slashes
    if '/' in id_:
        return False

    # 6. Check if the ID contains any special characters that are not allowed
    for char in id_:
        if not (char.isalnum() or char in allowed_special_characters):
            return False

    # 7. Check if the ID is too long
    if len(id_) > 64:
        return False

    # 8. Check for reserved keywords
    reserved_keywords = ['id', 'parent', 'children', 'type', 'config', 'group', 'categories', 'popups', 'callouts']
    if id_ in reserved_keywords:
        return False

    return True


def split_path(path):
    # Remove any leading/trailing slashes
    path = path.strip('/')
    parts = path.split('/')

    if not parts or parts[0] == '':
        return '', ''

    first = parts[0]
    remainder = '/'.join(parts[1:])
    return first, remainder


def strip_id(path, target_id) -> str | None:
    # Ensure no leading or trailing slashes
    path = path.strip('/')
    parts = path.split('/')

    try:
        index = parts.index(target_id)
        return '/'.join(parts[index + 1:])
    except ValueError:
        # target_id not found
        return None


def warn_on_unknown_kwargs(kwargs: dict, config_template: dict, logger: Logger):
    """
    Logs a warning for any kwargs that aren't present in the config_template.

    Parameters:
        kwargs (dict): The keyword arguments passed in.
        config_template (dict): The set of allowed/default config keys.
        logger (Logger): Logger instance to use for warnings.
    """
    for key in kwargs:
        if key not in config_template:
            logger.warning(f"Warning: Unrecognized config key passed via kwargs: '{key}'")


def addIdPrefix(node: Any, prefix: str, field_names: list[str]) -> None:
    """
    Recursively add a prefix to string fields in a nested structure.

    Args:
        node: The data structure (dict, list, or other) to process in place.
        prefix: The prefix string to add (e.g., "parent/child").
        field_names: List of dict keys to target (e.g., ['id', 'parent']).

    Behavior:
        - For any dict, if a key is in field_names and its value is a string,
          ensures the value starts with prefix + '/', adding it if missing.
        - Recurses into nested dicts and lists.
    """
    _add_prefix(node, prefix.rstrip('/') + '/', set(field_names))


def removeIdPrefix(node: Any, prefix: str, field_names: list[str]) -> None:
    """
    Recursively remove a prefix from string fields in a nested structure.

    Args:
        node: The data structure (dict, list, or other) to process in place.
        prefix: The prefix string to remove (e.g., "parent/child").
        field_names: List of dict keys to target (e.g., ['id', 'parent']).

    Behavior:
        - For any dict, if a key is in field_names and its value is a string,
          removes the leading prefix + '/' if present.
        - Recurses into nested dicts and lists.
    """
    _remove_prefix(node, prefix.rstrip('/') + '/', set(field_names))


def _add_prefix(node: Any, prefix: str, field_names: Set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in field_names and isinstance(value, str):
                # Normalize value by stripping existing slashes
                base = value.lstrip('/')
                # Prepend prefix if not already present
                if not base.startswith(prefix):
                    node[key] = prefix + base
            else:
                _add_prefix(value, prefix, field_names)
    elif isinstance(node, list):
        for item in node:
            _add_prefix(item, prefix, field_names)
    # other types are ignored


def _remove_prefix(node: Any, prefix: str, field_names: Set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in field_names and isinstance(value, str):
                # Remove the prefix if present
                if value.startswith(prefix):
                    node[key] = value[len(prefix):]
            else:
                _remove_prefix(value, prefix, field_names)
    elif isinstance(node, list):
        for item in node:
            _remove_prefix(item, prefix, field_names)
    # other types are ignored
