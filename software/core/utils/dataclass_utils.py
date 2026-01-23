"""
This module provides utilities for converting dictionaries into dataclass instances,
building nested values for unions and collections, freezing dataclass instances to
immutable versions, analyzing dataclass structure, and converting dataclasses to
dictionaries in an optimized way.

Caching is applied for metadata lookups (e.g. type hints and field definitions) to
improve performance on repeated calls. The code also leverages recursive approaches
to handle nested dataclasses.
"""

import copy
import dataclasses
import enum
from enum import IntEnum, Enum
from itertools import zip_longest
from functools import lru_cache
import dataclasses
import numpy as np
from enum import Enum
from typing import (
    Any, Dict, Iterable, Mapping, MutableMapping, Sequence, Tuple, Type, TypeVar,
    Optional, get_type_hints, get_origin, get_args, Union, Collection, List
)

import graphviz

from dataclasses import fields, make_dataclass, is_dataclass, field

# Imports from dacite for handling data conversion, defaults, caching, and errors
from dacite.cache import cache
from dacite.config import Config
from dacite.data import Data
from dacite.dataclasses import (
    get_default_value_for_field,
    DefaultValueNotFoundError,
    get_fields,
    is_frozen,
)
from dacite.exceptions import (
    ForwardReferenceError,
    WrongTypeError,
    DaciteError,
    UnionMatchError,
    MissingValueError,
    DaciteFieldError,
    UnexpectedDataError,
    StrictUnionMatchError,
)
from dacite.types import (
    is_instance,
    is_generic_collection,
    is_union,
    extract_generic,
    is_optional,
    extract_origin_collection,
    is_init_var,
    extract_init_var,
    is_subclass,
)

# Type variable for generic dataclass conversion
T = TypeVar("T")


def from_dict(data_class: Type[T], data: Data | dict, config: Optional[Config] = None) -> T:
    """
    Create a dataclass instance from a dictionary.

    This function recursively converts the input dictionary into an instance of the given
    dataclass, applying type conversions and defaults as specified in the configuration.

    Args:
        data_class (Type[T]): The target dataclass type.
        data (Data): The input data as a dictionary.
        config (Optional[Config]): Optional configuration for the conversion process.

    Returns:
        T: An instance of the provided dataclass.

    Raises:
        ForwardReferenceError: If there is an issue resolving forward references.
        UnexpectedDataError: If extra keys are found in data when strict mode is enabled.
        WrongTypeError: If a field value is not of the expected type.
        MissingValueError: If a required field is missing.
        DaciteFieldError: If an error occurs while building a field's value.
    """
    init_values: MutableMapping[str, Any] = {}
    post_init_values: MutableMapping[str, Any] = {}
    config = config or Config()

    # Cache type hints and field metadata for performance
    try:
        data_class_hints = cache(get_type_hints)(data_class, localns=config.hashable_forward_references)
    except NameError as error:
        raise ForwardReferenceError(str(error))
    data_class_fields = cache(get_fields)(data_class)

    # If strict mode is enabled, check for any unexpected fields in the input data
    if config.strict:
        extra_fields = set(data.keys()) - {f.name for f in data_class_fields}
        if extra_fields:
            raise UnexpectedDataError(keys=extra_fields)

    # Process each field defined in the dataclass
    for field in data_class_fields:
        field_type = data_class_hints[field.name]
        if field.name in data:
            try:
                field_data = data[field.name]
                # Build the field value recursively based on its type
                value = _build_value(type_=field_type, data=field_data, config=config)
            except DaciteFieldError as error:
                error.update_path(field.name)
                raise
            # Optionally check that the value matches the expected type
            if config.check_types and not is_instance(value, field_type):
                raise WrongTypeError(field_path=field.name, field_type=field_type, value=value)
        else:
            try:
                # Retrieve default value if field is missing in the input data
                value = get_default_value_for_field(field, field_type)
            except DefaultValueNotFoundError:
                if not field.init:
                    # Skip post-init fields without defaults
                    continue
                raise MissingValueError(field.name)

        if field.init:
            init_values[field.name] = value
        elif not is_frozen(data_class):
            # For non-frozen dataclasses, set post-init values after instantiation
            post_init_values[field.name] = value

    # Instantiate the dataclass with the initial values and set post-init values
    instance = data_class(**init_values)
    for key, value in post_init_values.items():
        setattr(instance, key, value)
    return instance


# ---------- Generic coercion helpers ----------

def _is_dataclass_type(tp: Any) -> bool:
    try:
        return dataclasses.is_dataclass(tp) and isinstance(tp, type)
    except Exception:
        return False


def _is_enum_type(tp: Any) -> bool:
    try:
        return issubclass(tp, Enum)
    except Exception:
        return False


def _coerce_enum(value: Any, enum_type: Type[Enum]) -> Enum:
    if isinstance(value, enum_type):
        return value
    # try by value first (covers ints and exact values)
    try:
        return enum_type(value)
    except Exception:
        # try by name (e.g. "BALANCING")
        return enum_type[str(value)]


def _to_ndarray(value: Any) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return value
    if isinstance(value, (list, tuple)):
        return np.asarray(value)
    return np.asarray(value)


def _simple_cast(value: Any, tp: Any) -> Any:
    # conservative simple casts
    if tp in (int, float, str, bool) and not isinstance(value, tp):
        # empty string to None for Optional[...]
        if value == "" and tp is not str:
            raise ValueError("empty cannot cast to non-str")
        return tp(value)
    return value


from typing import Any, get_origin, get_args, Union, Mapping, Iterable, Tuple, List, Sequence
import types as pytypes
import dataclasses
import numpy as np
from enum import Enum


def coerce_to_type(value: Any, target_type: Any, config) -> Any:
    """
    Convert 'value' into 'target_type' using typing annotations.
    Supports:
      - PEP 604 unions (A | B)
      - typing.Union / Optional
      - numpy arrays
      - Enums (by value or by name)
      - Nested dataclasses (via from_dict_auto)
      - Dict / List / Set / Tuple (fixed/variadic)
      - Primitive casts (int/float/str/bool)

    Falls back to returning the original value; if config.check_types=True,
    dacite will still validate types later.
    """
    if value is None:
        return None

    # Helper predicates
    def _is_dataclass_type(tp: Any) -> bool:
        try:
            return dataclasses.is_dataclass(tp) and isinstance(tp, type)
        except Exception:
            return False

    def _is_enum_type(tp: Any) -> bool:
        try:
            return issubclass(tp, Enum)
        except Exception:
            return False

    def _coerce_enum(v: Any, enum_type: type[Enum]) -> Enum:
        if isinstance(v, enum_type):
            return v
        # try by value (covers ints and exact values)
        try:
            return enum_type(v)
        except Exception:
            # try by name
            return enum_type[str(v)]

    def _to_ndarray(v: Any) -> np.ndarray:
        if isinstance(v, np.ndarray):
            return v
        if isinstance(v, (list, tuple)):
            return np.asarray(v)
        return np.asarray(v)

    def _simple_cast(v: Any, tp: Any) -> Any:
        if tp in (int, float, str, bool) and not isinstance(v, tp):
            if v == "" and tp is not str:
                # avoid surprising int("") etc.
                raise ValueError("empty cannot cast to non-str")
            return tp(v)
        return v

    origin = get_origin(target_type)
    args = get_args(target_type)

    # ----- Optional / Union (supports typing.Union and PEP 604 X | Y) -----
    if origin in (Union, pytypes.UnionType):
        last_err = None
        for opt in args:
            if opt is type(None):
                if value is None:
                    return None
                continue
            try:
                return coerce_to_type(value, opt, config)
            except Exception as e:
                last_err = e
        # None matched – re-raise the last error or a generic one
        raise last_err or TypeError(f"Cannot coerce {value!r} to {target_type}")

    # ----- numpy arrays -----
    if target_type is np.ndarray:
        return _to_ndarray(value)

    # ----- Enums -----
    if _is_enum_type(target_type):
        return _coerce_enum(value, target_type)

    # ----- Dataclasses -----
    if _is_dataclass_type(target_type):
        # value should be a Mapping; delegate to your dataclass builder
        # NOTE: from_dict_auto must be in scope
        return from_dict_auto(target_type, value, config=config)

    # ----- Mappings (e.g., Dict[K, V]) -----
    if origin in (dict, Mapping):
        k_t, v_t = args or (Any, Any)
        if not isinstance(value, Mapping):
            raise TypeError(f"Expected Mapping for {target_type}, got {type(value)}")
        out = {}
        for k, v in value.items():
            kk = coerce_to_type(k, k_t, config) if k_t is not Any else k
            vv = coerce_to_type(v, v_t, config) if v_t is not Any else v
            out[kk] = vv
        return out

    # ----- Sequences / Tuples / Sets -----
    if origin in (list, List, Sequence, tuple, Tuple, set, frozenset):
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes, bytearray)):
            raise TypeError(f"Expected iterable for {target_type}, got {type(value)}")

        def coerce_elem(e, i):
            # Homogeneous containers like List[T], Set[T], etc.
            if origin in (list, List, Sequence, set, frozenset):
                t = args[0] if args else Any
                return coerce_to_type(e, t, config) if t is not Any else e
            # Tuple handling: Tuple[T1, T2, ...] or Tuple[T, ...]
            if origin in (tuple, Tuple):
                if len(args) == 2 and args[1] is Ellipsis:
                    return coerce_to_type(e, args[0], config)
                if i >= len(args):
                    raise TypeError(f"Tuple index {i} out of bounds for {target_type}")
                return coerce_to_type(e, args[i], config)
            return e

        coerced = [coerce_elem(e, i) for i, e in enumerate(value)]
        if origin is set:
            return set(coerced)
        if origin is frozenset:
            return frozenset(coerced)
        if origin in (tuple, Tuple):
            return tuple(coerced)
        return list(coerced)

    # ----- Fall back: direct type or Annotated-like wrappers -----
    if isinstance(target_type, type):
        try:
            return _simple_cast(value, target_type)
        except Exception:
            pass
        if _is_dataclass_type(target_type):
            return from_dict_auto(target_type, value, config=config)
        if _is_enum_type(target_type):
            return _coerce_enum(value, target_type)

    # Unknown/Any: return as-is (dacite's type checking will catch real mismatches)
    return value


# ---------- Your original from_dict, with one-line change ----------

def from_dict_auto(data_class: Type[T], data: Dict[str, Any], config: Optional[Config] = None) -> T:
    init_values: MutableMapping[str, Any] = {}
    post_init_values: MutableMapping[str, Any] = {}
    config = config or Config()

    try:
        data_class_hints = cache(get_type_hints)(data_class, localns=config.hashable_forward_references)
    except NameError as error:
        raise ForwardReferenceError(str(error))
    data_class_fields = cache(get_fields)(data_class)

    if config.strict:
        extra_fields = set(data.keys()) - {f.name for f in data_class_fields}
        if extra_fields:
            raise UnexpectedDataError(keys=extra_fields)

    for field in data_class_fields:
        field_type = data_class_hints[field.name]
        if field.name in data:
            try:
                field_data = data[field.name]
                # >>> the only change: use generic coercion <<<
                value = coerce_to_type(field_data, field_type, config)
            except DaciteFieldError as error:
                error.update_path(field.name)
                raise
            if config.check_types and not is_instance(value, field_type):
                raise WrongTypeError(field_path=field.name, field_type=field_type, value=value)
        else:
            try:
                value = get_default_value_for_field(field, field_type)
            except DefaultValueNotFoundError:
                if not field.init:
                    continue
                raise MissingValueError(field.name)

        if field.init:
            init_values[field.name] = value
        elif not is_frozen(data_class):
            post_init_values[field.name] = value

    instance = data_class(**init_values)
    for key, value in post_init_values.items():
        setattr(instance, key, value)
    return instance


def _build_value(type_: Type, data: Any, config: Config) -> Any:
    """
    Build a value for a given field based on its type and provided data.

    Handles various cases such as optional types, unions, generic collections,
    nested dataclasses, and IntEnum types. Also applies any type hooks and casts
    specified in the configuration.

    Args:
        type_ (Type): The expected type of the value.
        data (Any): The raw input data for the field.
        config (Config): The conversion configuration.

    Returns:
        Any: The processed field value.
    """
    # Handle initialization variables by extracting the underlying type
    if is_init_var(type_):
        type_ = extract_init_var(type_)

    # If a type hook is provided, apply it immediately
    if type_ in config.type_hooks:
        data = config.type_hooks[type_](data)

    # For optional types, if the data is None, return immediately
    if is_optional(type_) and data is None:
        return data

    # If the type is a union, process union types
    if is_union(type_):
        data = _build_value_for_union(union=type_, data=data, config=config)
    # If the type is a generic collection, process it accordingly
    elif is_generic_collection(type_):
        data = _build_value_for_collection(collection=type_, data=data, config=config)
    # If the type is a dataclass and data is a Mapping, recursively convert it
    elif cache(is_dataclass)(type_) and isinstance(data, Mapping):
        data = from_dict(data_class=type_, data=data, config=config)
    # Special handling for IntEnum types
    elif issubclass(type_, IntEnum):
        if isinstance(data, int):
            return type_(data)
        else:
            raise WrongTypeError(field_type=type_, value=data)

    # Apply any cast conversions specified in the configuration
    for cast_type in config.cast:
        if is_subclass(type_, cast_type):
            if is_generic_collection(type_):
                data = extract_origin_collection(type_)(data)
            else:
                data = type_(data)
            break

    return data


def _build_value_for_union(union: Type, data: Any, config: Config) -> Any:
    """
    Process a union type by attempting to convert the input data into one of the union's types.

    When strict union matching is enabled, all matching types are collected and an error is raised
    if more than one match is found. Otherwise, the first successful conversion is returned.

    Args:
        union (Type): The union type (e.g., Union[int, str]).
        data (Any): The raw input data.
        config (Config): The conversion configuration.

    Returns:
        Any: The converted value matching one of the union types.

    Raises:
        StrictUnionMatchError: If multiple union types match when strict mode is enabled.
        UnionMatchError: If no union member matches and type checking is enabled.
    """
    types = extract_generic(union)
    # Handle Optional[X] by processing the non-None type
    if is_optional(union) and len(types) == 2:
        return _build_value(type_=types[0], data=data, config=config)

    union_matches = {}
    for inner_type in types:
        try:
            # Try building the value for the inner type; skip on any exception
            try:
                value = _build_value(type_=inner_type, data=data, config=config)
            except Exception:
                continue
            if is_instance(value, inner_type):
                if config.strict_unions_match:
                    union_matches[inner_type] = value
                else:
                    return value  # Return immediately if not in strict mode
        except DaciteError:
            pass

    if config.strict_unions_match:
        if len(union_matches) > 1:
            raise StrictUnionMatchError(union_matches)
        # Return the single matching value if available
        return union_matches.popitem()[1]
    if not config.check_types:
        return data
    raise UnionMatchError(field_type=union, value=data)


def _build_value_for_collection(collection: Type, data: Any, config: Config) -> Any:
    """
    Process a generic collection type (e.g., List, Tuple, Dict) by recursively converting its elements.

    Args:
        collection (Type): The expected collection type.
        data (Any): The raw input data.
        config (Config): The conversion configuration.

    Returns:
        Any: The processed collection with its elements converted.
    """
    data_type = data.__class__

    # Process Mapping types (e.g., dict)
    if isinstance(data, Mapping) and is_subclass(collection, Mapping):
        # Extract the type for the mapping's values (ignore keys)
        item_type = extract_generic(collection, defaults=(Any, Any))[1]
        return data_type((key, _build_value(type_=item_type, data=value, config=config))
                         for key, value in data.items())
    # Process Tuple types (both fixed-length and variable-length)
    elif isinstance(data, tuple) and is_subclass(collection, tuple):
        if not data:
            return data_type()
        types = extract_generic(collection)
        # If variable-length tuple (e.g., Tuple[int, ...])
        if len(types) == 2 and types[1] == Ellipsis:
            return data_type(_build_value(type_=types[0], data=item, config=config)
                             for item in data)
        # Fixed-length tuple: match each element with corresponding type
        return data_type(_build_value(type_=type_, data=item, config=config)
                         for item, type_ in zip_longest(data, types))
    # Process other Collection types (e.g., list, set)
    elif isinstance(data, Collection) and is_subclass(collection, Collection):
        item_type = extract_generic(collection, defaults=(Any,))[0]
        return data_type(_build_value(type_=item_type, data=item, config=config)
                         for item in data)
    return data


# Global cache for frozen dataclass types to avoid recreating them multiple times.
_frozen_dataclass_cache: Dict[Tuple[type, Tuple[str, type]], type] = {}


def freeze_dataclass_instance(instance: Any) -> Any:
    """
    Convert a dataclass instance and all its nested dataclasses into an immutable (frozen) version.

    This function leverages a cache to avoid re-creating frozen dataclass types for the same original class.
    It recursively processes nested dataclass fields.

    Args:
        instance (Any): The dataclass instance to freeze.

    Returns:
        Any: A frozen (immutable) copy of the dataclass instance.

    Raises:
        ValueError: If the provided instance is not a dataclass.
    """
    if not is_dataclass(instance):
        raise ValueError("The input must be an instance of a dataclass.")

    def get_frozen_dataclass_type(cls: type) -> type:
        """
        Retrieve or create a frozen version of the given dataclass type.

        Args:
            cls (type): The original dataclass type.

        Returns:
            type: A frozen version of the dataclass type.
        """
        # Use a tuple of (field name, field type) as part of the cache key
        cls_fields = tuple((f.name, f.type) for f in fields(cls))
        cache_key = (cls, cls_fields)

        if cache_key not in _frozen_dataclass_cache:
            # Create a new frozen dataclass using the same fields and defaults as the original
            frozen_cls = make_dataclass(
                cls.__name__ + "Frozen",
                [
                    (
                        f.name,
                        f.type,
                        field(
                            default=f.default
                            if f.default is not dataclasses.MISSING
                            else dataclasses.MISSING,
                            default_factory=f.default_factory
                            if f.default_factory is not dataclasses.MISSING
                            else dataclasses.MISSING,
                        ),
                    )
                    for f in fields(cls)
                ],
                frozen=True
            )
            _frozen_dataclass_cache[cache_key] = frozen_cls
        return _frozen_dataclass_cache[cache_key]

    def freeze_instance(dataclass_instance: Any) -> Any:
        """
        Recursively convert a dataclass instance into its frozen version.

        Args:
            dataclass_instance (Any): The original dataclass instance.

        Returns:
            Any: The frozen version of the instance.
        """
        cls = type(dataclass_instance)
        frozen_cls = get_frozen_dataclass_type(cls)

        frozen_kwargs = {}
        for f in fields(cls):
            value = getattr(dataclass_instance, f.name)
            if is_dataclass(value):
                frozen_kwargs[f.name] = freeze_instance(value)
            else:
                # Use deepcopy to ensure immutability of mutable fields
                frozen_kwargs[f.name] = copy.deepcopy(value)
        return frozen_cls(**frozen_kwargs)

    return freeze_instance(instance)


def analyze_dataclass(
        dataclass_type: Type[Any],
        print_to_terminal: bool = False,
        print_to_file: bool = True,
        generate_figure: bool = False,
):
    """
    Generate diagnostics for a dataclass including its field paths and nested structure.

    This function extracts field names and types recursively, writes the paths to a file,
    optionally prints them to the terminal, and can generate a visual tree diagram using Graphviz.

    Args:
        dataclass_type (Type[Any]): The dataclass type to analyze.
        print_to_terminal (bool): If True, prints the field paths to the terminal.
        print_to_file (bool): If True, writes the field paths to a text file.
        generate_figure (bool): If True, generates a tree diagram in PNG format.

    Raises:
        ValueError: If the provided type is not a dataclass.
    """
    if not is_dataclass(dataclass_type):
        raise ValueError("The provided type is not a dataclass.")

    # Define color mapping for various field types
    type_colors = {
        "dataclass": "lightblue",
        "float": "lightgreen",
        "int": "lightcoral",
        "str": "wheat",
        "List": "yellow",
        "Dict": "pink",
        "Optional": "gray",
    }

    def get_color(field_type):
        """
        Get the fill color for a given field type based on the mapping.

        Args:
            field_type: The type of the field.

        Returns:
            str: The color name.
        """
        if hasattr(field_type, "__origin__"):  # Handle generics like List, Dict, Optional
            origin = field_type.__origin__.__name__
            return type_colors.get(origin, "white")
        if is_dataclass(field_type):
            return type_colors["dataclass"]
        return type_colors.get(field_type.__name__, "white")

    def get_field_paths_and_structure(data_type, prefix=""):
        """
        Recursively extract field paths and structure from a dataclass.

        Args:
            data_type: The dataclass type to process.
            prefix (str): The prefix for nested field names.

        Returns:
            Tuple[List[str], List[Tuple[str, str, Any, bool]]]: A list of field paths and a structure list.
        """
        paths = []
        structure = []
        for field in fields(data_type):
            field_name = field.name
            field_type = field.type
            full_path = f"{prefix}{field_name}"
            paths.append(full_path)
            structure.append((prefix, field_name, field_type, is_dataclass(field_type)))
            # Recursively process nested dataclasses
            if is_dataclass(field_type):
                nested_paths, nested_structure = get_field_paths_and_structure(field_type, prefix=f"{full_path}.")
                paths.extend(nested_paths)
                structure.extend(nested_structure)
        return paths, structure

    # Generate field paths and structure for the given dataclass
    all_paths, structure = get_field_paths_and_structure(dataclass_type)

    dataclass_name = dataclass_type.__name__

    # Write field paths to an output file if enabled
    if print_to_file:
        txt_file_name = f"{dataclass_name}.txt"
        with open(txt_file_name, "w") as file:
            file.write(f"Fields and Paths for Dataclass: {dataclass_name}\n")
            for path in all_paths:
                file.write(f"{path}\n")

    # Optionally print the field paths to the terminal
    if print_to_terminal:
        print(f"Fields and Paths for Dataclass: {dataclass_name}")
        for path in all_paths:
            print(path)

    # Optionally generate a visual tree diagram using Graphviz
    if generate_figure:
        graph = graphviz.Digraph(format="png")
        graph.attr(rankdir="TB")  # Top-to-bottom layout
        graph.attr("node", shape="box")

        # Add the root node representing the dataclass
        root_name = dataclass_type.__name__
        graph.node(root_name, f"{root_name} (dataclass)", style="filled", fillcolor=type_colors["dataclass"])

        def add_to_graph(parent, current_prefix, structure):
            """
            Recursively add nodes and edges for each field to the Graphviz graph.

            Args:
                parent: The parent node ID.
                current_prefix: The prefix corresponding to the parent's path.
                structure: The list of field structure tuples.
            """
            for prefix, field_name, field_type, is_nested in structure:
                # Connect only immediate children of the current parent
                if prefix.rstrip(".") == current_prefix.rstrip("."):
                    node_id = f"{prefix}{field_name}".replace(".", "_")
                    # Label the node with the field name and type if not a nested dataclass
                    node_label = f"{field_name} ({field_type.__name__})" if not is_nested else field_name
                    color = get_color(field_type)
                    graph.node(node_id, node_label, style="filled", fillcolor=color)
                    graph.edge(parent, node_id)
                    # Recursively add nested dataclass children
                    if is_nested:
                        nested_structure = [
                            item for item in structure if item[0].startswith(f"{prefix}{field_name}.")
                        ]
                        add_to_graph(node_id, f"{prefix}{field_name}.", nested_structure)

        add_to_graph(root_name, "", structure)
        graph.render(dataclass_name, cleanup=True)


@lru_cache(maxsize=20)
def get_dataclass_fields(cls):
    """
    Retrieve the fields for a dataclass type using caching.

    This function is cached to speed up repeated access to field metadata.

    Args:
        cls: The dataclass type.

    Returns:
        A tuple of Field objects for the dataclass.
    """
    return fields(cls)


def asdict_optimized(obj):
    """
    Convert a dataclass instance to a dictionary using cached field metadata.

    This function recursively converts dataclass instances, as well as their nested
    lists, tuples, and dictionaries, to dictionaries.

    Args:
        obj: The dataclass instance or container to convert.

    Returns:
        A dictionary representation of the dataclass.
    """
    if is_dataclass(obj):
        result = {}
        for f in get_dataclass_fields(type(obj)):
            value = getattr(obj, f.name)
            # Recursively convert nested dataclasses or collections
            result[f.name] = asdict_optimized(value)
        return result
    elif isinstance(obj, (list, tuple)):
        # Preserve the original type (list or tuple) for sequences
        return type(obj)(asdict_optimized(item) for item in obj)
    elif isinstance(obj, dict):
        # Recursively process dictionary values
        return {key: asdict_optimized(value) for key, value in obj.items()}
    else:
        return obj


# ======================================================================================================================
def update_dataclass_from_dict(dataclass_instance, update_dict):
    if not is_dataclass(dataclass_instance):
        raise TypeError("Provided object is not a dataclass instance")

    for field in fields(dataclass_instance):
        if field.name in update_dict:
            setattr(dataclass_instance, field.name, update_dict[field.name])


# ======================================================================================================================
# ======================================================================================================================
# Optimized dataclass deepcopy with global cache
# - Compiles one copier per dataclass type and caches it globally via @lru_cache.
# - Uses type hints to specialize container element copying.
# - Honors field metadata {"shallow": True} to keep references instead of copying.
# - Handles common containers; treats primitives & Enums as atomic.
# - Note: This assumes acyclic object graphs (typical for records/trees). For cyclic graphs,
#         stick with copy.deepcopy or extend this with a memo table.
# ======================================================================================================================

# Atomic / passthrough types
_ATOMIC = (int, float, bool, str, bytes, type(None))


def _is_atomic_value(x: Any) -> bool:
    return isinstance(x, _ATOMIC) or isinstance(x, enum.Enum)


def deepcopy_dataclass(obj: Any) -> Any:
    """
    Deep-copy a dataclass instance (and nested dataclasses/containers) using a
    globally cached, per-type copier. Falls back to a fast generic copier for
    non-dataclass values.
    """
    if is_dataclass(obj):
        return _compile_dataclass_copier(type(obj))(obj)
    return _generic_copy(obj)


def prewarm_dataclass_copiers(*classes: type) -> None:
    """
    Optionally pre-compile copier functions for the provided dataclass classes.
    Useful if you want to JIT them up front (e.g., before a tight loop).
    """
    for cls in classes:
        if not is_dataclass(cls):
            raise TypeError(f"{cls!r} is not a dataclass type")
        _compile_dataclass_copier(cls)  # populate cache


# ------------------------------- generic copy helpers -------------------------------

def _generic_value_copier(v: Any) -> Any:
    return _generic_copy(v)


def _generic_copy(x: Any) -> Any:
    # Keep very fast exits first
    if _is_atomic_value(x):
        return x
    if is_dataclass(x):
        return _compile_dataclass_copier(type(x))(x)
    if isinstance(x, list):
        c = _generic_value_copier
        return [c(e) for e in x]
    if isinstance(x, tuple):
        c = _generic_value_copier
        return tuple(c(e) for e in x)
    if isinstance(x, set):
        c = _generic_value_copier
        return {c(e) for e in x}
    if isinstance(x, dict):
        ck = _generic_value_copier
        cv = _generic_value_copier
        return {ck(k): cv(v) for k, v in x.items()}
    # Unknown user class: return as-is (acts like shallow copy)
    return x


def _generic_container_copier_for(container_type: type):
    if container_type is list:
        def _copy_list(x):
            return x if x is None else [_generic_value_copier(v) for v in x]

        return _copy_list
    if container_type is tuple:
        def _copy_tuple(x):
            return x if x is None else tuple(_generic_value_copier(v) for v in x)

        return _copy_tuple
    if container_type is set:
        def _copy_set(x):
            return x if x is None else {_generic_value_copier(v) for v in x}

        return _copy_set
    if container_type is dict:
        def _copy_dict(x):
            if x is None:
                return x
            ck = _generic_value_copier
            cv = _generic_value_copier
            return {ck(k): cv(v) for k, v in x.items()}

        return _copy_dict
    return _generic_copy


# ------------------------------- compiler: per-type copiers -------------------------------

@lru_cache(maxsize=None)
def _compile_dataclass_copier(cls: type):
    """
    Build and cache a fast copier for a dataclass type.
    Uses evaluated type hints to specialize container element copying.
    Supports field metadata {"shallow": True}.
    """
    # Get evaluated type hints; if resolution fails, fall back to empty
    try:
        # Prefer your existing cache for get_type_hints if you want:
        # hints = cache(get_type_hints)(cls)
        hints = get_type_hints(cls, include_extras=True)
    except Exception:
        hints = {}

    field_specs = []
    for f in fields(cls):
        shallow = (f.metadata or {}).get("shallow", False)
        hint = hints.get(f.name, Any)
        copier = _compile_field_copier(hint, shallow)
        field_specs.append((f.name, copier))

    def _copy_instance(x):
        # kwargs assembly is fast and avoids dataclasses.replace overhead
        kw = {}
        for name, copier in field_specs:
            kw[name] = copier(getattr(x, name))
        return cls(**kw)

    return _copy_instance


def _compile_field_copier(hint: Any, shallow: bool):
    if shallow:
        return lambda v: v

    # Dataclass type directly?
    if isinstance(hint, type) and is_dataclass(hint):
        copier = _compile_dataclass_copier(hint)
        return lambda v: None if v is None else copier(v)

    origin = get_origin(hint)
    args = get_args(hint)

    # Parameterized containers
    if origin in (list, set):
        elem_c = _compile_hint_copier(args[0]) if args else _generic_value_copier
        if origin is list:
            return lambda v: None if v is None else [elem_c(e) for e in v]
        return lambda v: None if v is None else {elem_c(e) for e in v}

    if origin is dict:
        key_c = _compile_hint_copier(args[0]) if args else _generic_value_copier
        val_c = _compile_hint_copier(args[1]) if len(args) > 1 else _generic_value_copier
        return lambda v: None if v is None else {key_c(k): val_c(val) for k, val in v.items()}

    if origin is tuple:
        # tuple[T, ...] or just tuple[Any, ...]
        if not args or args[-1] is ...:
            elem_c = _compile_hint_copier(args[0]) if args and args[-1] is ... else _generic_value_copier
            return lambda v: None if v is None else tuple(elem_c(e) for e in v)
        # tuple[T1, T2, ...]
        elem_cs = tuple(_compile_hint_copier(a) for a in args)
        return lambda v: None if v is None else tuple(c(e) for c, e in zip(elem_cs, v))

    if origin is Union:
        # Optional[T] fast-path
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            inner = _compile_hint_copier(non_none[0])
            return lambda v: None if v is None else inner(v)
        # General union: fall back (runtime check)
        return _generic_value_copier

    # Primitive / enums via hint
    if hint in _ATOMIC:
        return lambda v: v
    if isinstance(hint, type) and issubclass(hint, enum.Enum):
        return lambda v: v

    # Unknown or Any
    return _generic_value_copier


@lru_cache(maxsize=None)
def _compile_hint_copier(hint: Any):
    return _compile_field_copier(hint, shallow=False)


# Example usage and simple test of the implemented functions

if __name__ == "__main__":
    from dataclasses import dataclass


    @dataclass
    class Address:
        street: str
        city: str


    @dataclass
    class Person:
        name: str
        age: int
        address: Address


    addr = Address("123 Main St", "Anytown")
    person = Person("Alice", 30, addr)

    # Convert dataclass to dictionary using the optimized asdict function
    person_dict = asdict_optimized(person)
    print("Converted dataclass to dict:", person_dict)
