from collections.abc import Mapping, MutableSequence, MutableSet
import copy
import re
from typing import Any, Dict, List, Optional, Union


def _is_mutable_container(v):
    return isinstance(v, (Mapping, MutableSequence, MutableSet))


def update_dict(original: dict,
                *updates: dict,
                allow_add: bool = True,
                prefer_existing: bool = False,
                copy_on_assign: bool = True) -> dict:
    """
    Merge updates into `original` in place and return it.

    - Recurses when both sides have a dict at the same key.
    - If `prefer_existing=True`, existing keys in `original` are NOT overwritten
      (useful when applying defaults).
    - If assigning a whole value (not recursing), we do a defensive copy for
      mutable containers to avoid aliasing, but skip copies for immutables.

    Parameters
    ----------
    original : dict
        Target dict to mutate.
    *updates : dict
        One or more dicts to merge from left to right.
    allow_add : bool
        If False, ignore keys not already in `original`.
    prefer_existing : bool
        If True, keep `original[key]` when it already exists.
    copy_on_assign : bool
        If True, copy mutable containers when assigning.
    """
    for upd in updates:
        for key, value in upd.items():
            # If both sides are dicts, recurse without replacing the object
            if key in original and isinstance(original[key], Mapping) and isinstance(value, Mapping):
                update_dict(original[key], value,
                            allow_add=allow_add,
                            prefer_existing=prefer_existing,
                            copy_on_assign=copy_on_assign)
                continue

            # Respect allow_add / prefer_existing
            if not allow_add and key not in original:
                continue
            if prefer_existing and key in original:
                continue

            # Assign (with copy to avoid aliasing when needed)
            if copy_on_assign and _is_mutable_container(value):
                original[key] = copy.deepcopy(value)
            else:
                original[key] = value
    return original


def flatten_dict(data: dict, indent: int = 0) -> list[tuple[str, str]]:
    """
    Recursively flatten a dictionary into a list of (key, value) tuples.
    The key is indented by two spaces per level. If a value is a dict, the key
    is shown with an empty value, and its contents are flattened below.
    Lists are displayed as a comma-separated list inside square brackets.
    """
    rows = []
    for key, value in data.items():
        prefix = "  " * indent + str(key)
        if isinstance(value, dict):
            rows.append((prefix, ""))
            rows.extend(flatten_dict(value, indent=indent + 1))
        elif isinstance(value, list):
            rows.append((prefix, "[" + ", ".join(str(x) for x in value) + "]"))
        else:
            rows.append((prefix, str(value)))
    return rows


def replaceField(data, expected_type, key, new_value):
    """
    Recursively replaces the value of the specified key(s) with a new value
    if the existing value matches the given type.

    Parameters:
        data (dict or list): The input dictionary (or list of dictionaries) to process.
        expected_type (type): The type to match before replacing the value.
        key (str or list): The key or list of keys to search for.
        new_value: The value to replace with.

    Returns:
        None: Modifies the input dictionary in place.
    """
    if isinstance(key, str):
        keys = [key]
    else:
        keys = key

    if isinstance(data, dict):
        for k in data:
            if k in keys and isinstance(data[k], expected_type):
                data[k] = new_value
            else:
                replaceField(data[k], expected_type, keys, new_value)
    elif isinstance(data, list):
        for item in data:
            replaceField(item, expected_type, keys, new_value)


def replaceStringInDict(
        data: Union[Dict[str, Any], List[Any]],
        key: Union[str, List[str]],
        new_value: str,
        regex: Optional[Union[str, re.Pattern]] = None,
        regex_flags: int = 0
) -> None:
    """
    Recursively replaces the value of the specified key(s) with `new_value`
    **only when the current value is a string**. If `regex` is provided,
    replacement occurs only when the string value matches the pattern.

    Parameters:
        data (dict or list): The input dictionary (or list) to process (modified in place).
        key (str or list[str]): The key or keys whose string values may be replaced.
        new_value (str): The value to write when conditions are met.
        regex (str or Pattern, optional): A regular expression that the current string
            value must match to be replaced. If None, all string values for matching
            keys are replaced.
        regex_flags (int): Flags passed to `re.compile` if `regex` is a string.

    Returns:
        None
    """
    keys = [key] if isinstance(key, str) else key

    # Prepare matcher
    if regex is None:
        def _matches(_: str) -> bool:
            return True
    else:
        pattern = re.compile(regex, regex_flags) if isinstance(regex, str) else regex

        def _matches(s: str) -> bool:
            return bool(pattern.search(s))

    if isinstance(data, dict):
        for k, v in list(data.items()):
            if k in keys and isinstance(v, str) and _matches(v):
                data[k] = new_value
            else:
                if isinstance(v, (dict, list)):
                    replaceStringInDict(v, keys, new_value, regex, regex_flags)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                replaceStringInDict(item, keys, new_value, regex, regex_flags)


# ======================================================================================================================
class ObservableDict(dict):
    def __init__(self, *args, on_change=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_change = on_change

    def _notify(self):
        if self._on_change:
            self._on_change()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._notify()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._notify()

    def clear(self):
        super().clear()
        self._notify()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._notify()

    def pop(self, *args):
        result = super().pop(*args)
        self._notify()
        return result

    def popitem(self):
        result = super().popitem()
        self._notify()
        return result
