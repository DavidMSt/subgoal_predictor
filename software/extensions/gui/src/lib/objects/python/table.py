from __future__ import annotations

import dataclasses
from typing import Any, TypeVar, ClassVar

from core.utils.callbacks import callback_definition
from core.utils.callbacks import CallbackContainer
from core.utils.dataclass_utils import update_dataclass_from_dict
from core.utils.events import event_definition, Event
from core.utils.uuid_utils import generate_uuid
from extensions.gui.src.lib.objects.objects import Widget


# ======================================================================================================================
# Callbacks


@callback_definition
class TableCallbacks:
    row_added: CallbackContainer
    row_deleted: CallbackContainer
    column_added: CallbackContainer
    column_deleted: CallbackContainer


# ======================================================================================================================
# Core model

@callback_definition
class CellCallbacks:
    update: CallbackContainer
    update_request: CallbackContainer


@event_definition
class CellEvents:
    update: Event
    update_request: Event


@dataclasses.dataclass(kw_only=True)
class Cell:
    id: str
    value: Any = None
    overwrites: dict[str, Any] = dataclasses.field(default_factory=dict)

    row: Row | None = None
    column: Column | None = None
    table: Table | None = None

    # Stores the *column class* (e.g. TextColumn), not the string type
    _column_type: type[Column] = dataclasses.field(init=False)

    @property
    def uid(self):
        if self.row is None or self.column is None:
            return None
        return f"r-{self.row.id}_c-{self.column.id}_{self.id}"

    # ------------------------------------------------------------------------------------------------------------------
    def __post_init__(self):
        self.callbacks = CellCallbacks()
        self.events = CellEvents()
        # Default, will be overwritten when attached to a column/row
        self._column_type = Column

    # ------------------------------------------------------------------------------------------------------------------
    def attach(self, *, row: Row, column: Column, table: Table) -> None:
        """Attach cell to its owning row/column/table and normalize invariants."""
        self.row = row
        self.column = column
        self.table = table
        self._column_type = type(column)

    # ------------------------------------------------------------------------------------------------------------------
    def set(self, value: Any) -> None:
        self.value = value
        if self.table is not None:
            self.table.update_cell(self)
        self.callbacks.update.call(self)

    # ------------------------------------------------------------------------------------------------------------------
    def update_request(self, value: Any):
        self.callbacks.update_request.call(value)
        self.events.update_request.set(value)

    # ------------------------------------------------------------------------------------------------------------------
    def get_configuration(self) -> dict:
        if self.row is None or self.column is None:
            raise RuntimeError(
                "Cell is not attached to a row/column. "
                "Ensure Column.make_cell() or Row.__setitem__ attaches the cell."
            )

        return {
            "id": self.uid,
            "row": self.row.id,
            "column": self.column.id,
            "column_type": self._column_type.column_type,
            "value": self.value,
            "overwrites": self.overwrites,
        }


@dataclasses.dataclass
class Row:
    id: str
    _table: Table
    cells: dict[str, Cell]  # {column_id: Cell}
    highlight: bool = False
    row_background_color: str | list | None = None
    group: TableGroup | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def get_cell(self, column: str | Column) -> Cell:
        col_id = column if isinstance(column, str) else column.id
        try:
            return self.cells[col_id]
        except KeyError as e:
            raise KeyError(f"Row '{self.id}' has no cell for column '{col_id}'.") from e

    # ------------------------------------------------------------------------------------------------------------------
    def delete(self) -> None:
        if self.group is not None:
            self.group.delete_row(self)
        else:
            self._table.delete_row(self)

    # ------------------------------------------------------------------------------------------------------------------
    def get_configuration(self) -> dict:
        return {
            "id": self.id,
            "group": self.group.id if self.group is not None else None,
            "highlight": self.highlight,
            "row_background_color": self.row_background_color,
            "cells": {cell_id: cell.get_configuration() for cell_id, cell in self.cells.items()},
        }

    # ------------------------------------------------------------------------------------------------------------------
    def __getitem__(self, column: str | Column) -> Cell:
        return self.get_cell(column)

    # ------------------------------------------------------------------------------------------------------------------
    def __setitem__(self, column: str | Column, value: Any | Cell) -> None:
        col_id = column if isinstance(column, str) else column.id
        try:
            col = self._table.columns[col_id]
        except KeyError as e:
            raise KeyError(f"Unknown column '{col_id}'.") from e

        if col_id in self.cells:
            cell = self.cells[col_id]
            cell.set(value)
        else:
            cell = col.make_cell(value=value)
            cell.attach(row=self, column=col, table=self._table)
            self.cells[col_id] = cell


CCol = TypeVar("CCol", bound="Column")
CCell = TypeVar("CCell", bound=Cell)


@dataclasses.dataclass(kw_only=True)
class Column:
    id: str
    width: float | str = "auto"
    title: str | None = None
    title_color: str | list | None = dataclasses.field(default_factory=lambda: [1.0, 1.0, 1.0, 0.7])
    title_font_size: int | None = 8
    background_color: str | list | None = dataclasses.field(default_factory=lambda: [1.0, 1.0, 1.0, 0.05])
    enabled: bool = True
    interactive: bool = False

    default_value: Any | None = None
    _table: Table | None = None

    # Render/semantic type string (e.g. "text") – subclasses override this
    column_type: str | None = None

    # Which Cell class this Column should create – subclasses should override
    cell_cls: ClassVar[type["Cell"]] = Cell

    def make_cell(self, *, id: str | None = None, value: Any = None, **overwrites) -> Cell:
        """
        Create a new cell instance for this column.
        Note: row attachment happens when the cell is inserted into a Row.
        """
        if id is None:
            id = generate_uuid(prefix="cell_")

        if value is None:
            value = self.default_value

        cell = self.cell_cls(id=id, value=value, overwrites=dict(overwrites))
        # attach will be done by Row/Column getters that place cells into rows
        cell._column_type = type(self)
        return cell

    def get_cell(self, row: str | int | Row) -> Cell:
        """Returns attached cell, creating if missing"""
        _row = self._table.get_row(row) if isinstance(row, (str, int)) else row
        if _row is None:
            raise KeyError(f"Row '{row}' not found.")

        # Ensure the cell exists (in case columns/rows were manipulated externally)
        if self.id not in _row.cells:
            cell = self.make_cell()
            cell.attach(row=_row, column=self, table=self._table)
            _row.cells[self.id] = cell

        # Ensure the cell is attached (defensive)
        cell = _row.cells[self.id]
        if cell.row is None or cell.column is None or cell.table is None:
            cell.attach(row=_row, column=self, table=self._table)

        return cell

    def get_configuration(self) -> dict:
        """
        Build a full configuration dict for this column, including:
        - all dataclass fields from this class and any parent dataclass (i.e. "own + parent params")
        - subclass-specific params automatically (no per-subclass override needed)
        """
        exclude_fields = {
            "_table",  # runtime pointer
            "cell_cls",  # class/type reference, not config
        }

        config: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            name = f.name
            if name in exclude_fields or name.startswith("_"):
                continue
            config[name] = getattr(self, name)

        # Normalize output keys expected by the frontend
        # Keep both "type" (historical) and do not leak "column_type" under the same name.
        config["type"] = self.column_type
        config.pop("column_type", None)

        return config

    def __getitem__(self, row: str | int | Row) -> Cell:
        return self.get_cell(row)


# ======================================================================================================================
# Column / Cell specializations


@dataclasses.dataclass(kw_only=True)
class TextColumn(Column):
    column_type: str | None = "text"
    text_color: str | list = "white"
    font_size: int | None = 8
    font_family: str | None = "sans-serif"
    font_align: str = "center"  # 'center', 'left', 'right'
    padding: str | None = None


@dataclasses.dataclass(kw_only=True)
class TextCell(Cell):
    value: str | None = None


TextColumn.cell_cls = TextCell


@dataclasses.dataclass(kw_only=True)
class TextInputColumn(Column):
    column_type: str | None = "text_input"
    input_color: str | list = "white"
    text_color: str | list = "black"
    font_size: int | None = None
    font_family: str | None = "sans-serif"
    font_align: str = "center"
    interactive: bool = True


@dataclasses.dataclass
class TextInputCell(Cell):
    value: str | None = None


TextInputColumn.cell_cls = TextInputCell


@dataclasses.dataclass(kw_only=True)
class NumberColumn(Column):
    column_type: str | None = "number"
    increment: float | None = 1
    align: str = "center"


@dataclasses.dataclass(kw_only=True)
class NumberCell(Cell):
    value: float | int | None = None


NumberColumn.cell_cls = NumberCell


@dataclasses.dataclass(kw_only=True)
class ButtonColumn(Column):
    column_type: str | None = "button"
    color: str | list | None = None
    text_color: str | list | None = None


@dataclasses.dataclass(kw_only=True)
class ButtonCell(Cell):
    # Keeping 'value' as generic; you can also add explicit fields if your UI needs them.
    # Example: text: str | None = None
    pass


ButtonColumn.cell_cls = ButtonCell


@dataclasses.dataclass(kw_only=True)
class CheckboxColumn(Column):
    column_type: str | None = "checkbox"


@dataclasses.dataclass(kw_only=True)
class CheckboxCell(Cell):
    value: bool | None = None


CheckboxColumn.cell_cls = CheckboxCell


@dataclasses.dataclass(kw_only=True)
class SliderColumn(Column):
    column_type: str | None = "slider"
    min_value: float = 0.0
    max_value: float = 100.0
    increment: float = 1.0


@dataclasses.dataclass(kw_only=True)
class SliderCell(Cell):
    value: float | int | None = None


SliderColumn.cell_cls = SliderCell


@dataclasses.dataclass(kw_only=True)
class IndicatorColumn(Column):
    column_type: str | None = "indicator"


# @dataclasses.dataclass(kw_only=True)
# class IndicatorCell(Cell):
#     value: list[float] | str | None = None  # color (rgba list) or string

@dataclasses.dataclass(kw_only=True)
class IndicatorCell(Cell):
    _color: Any = dataclasses.field(default=None, repr=False)
    _label: Any = dataclasses.field(default=None, repr=False)

    def _compose_value(self) -> Any:
        # matches your JS _normValue() accepted shapes
        # if self._color is not None and self._label not in (None, ""):
        #     return {"color": self._color, "label": str(self._label)}
        # if self._color is not None:
        #     return self._color
        # if self._label not in (None, ""):
        #     return str(self._label)
        return {"color": self._color, "label": self._label}

    @property
    def color(self) -> Any:
        return self._color

    @color.setter
    def color(self, v: Any) -> None:
        self._color = v
        super().set(self._compose_value())

    @property
    def label(self) -> Any:
        return self._label

    @label.setter
    def label(self, v: Any) -> None:
        self._label = None if v is None else str(v)
        super().set(self._compose_value())  # IMPORTANT: call super()

    def set(self, value: Any) -> None:
        """
        Allow raw set(...) to still work, while also updating _color/_label.
        """
        self._color = None
        self._label = None

        if value is None:
            pass
        elif isinstance(value, (str, int, float)):
            self._label = str(value)
        elif isinstance(value, (list, tuple)):
            if len(value) == 4:
                self._color = value
            elif len(value) >= 1 and isinstance(value[0], (list, tuple)):
                self._color = value[0]
                if len(value) > 1:
                    self._label = None if value[1] is None else str(value[1])
        elif isinstance(value, dict):
            self._color = value.get("color") or value.get("indicator_color")
            if "label" in value:
                self._label = None if value["label"] is None else str(value["label"])
        else:
            raise TypeError(f"Unsupported indicator value type: {type(value).__name__}")

        super().set(self._compose_value())


IndicatorColumn.cell_cls = IndicatorCell

# ======================================================================================================================
# Select (single)


@dataclasses.dataclass(kw_only=True)
class SelectColumn(Column):
    """
    Single-select dropdown.
    options: dict[id -> label]
    """
    column_type: str | None = "select"

    options: dict[str, str] = dataclasses.field(default_factory=dict)

    select_color: str | list | None = dataclasses.field(default_factory=lambda: [0.8, 0.8, 0.8, 0.7])
    text_color: str | list | None = dataclasses.field(default_factory=lambda: [0.8, 0.8, 0.8, 0.7])
    font_size: int | None = 12
    font_family: str | None = "sans-serif"
    font_align: str = "center"
    active: bool = True

    # Optional: default selection id
    default_value: Any | None = None


@dataclasses.dataclass(kw_only=True)
class SelectCell(Cell):
    """
    value: selected option id (string) or None
    """
    value: str | None = None


SelectColumn.cell_cls = SelectCell


# ======================================================================================================================
# MultiSelect


@dataclasses.dataclass(kw_only=True)
class MultiSelectColumn(Column):
    """
    Multi-select dropdown.
    options: dict[id -> label]
    value is typically list[str], but the JS also supports comma-separated string.
    """
    column_type: str | None = "multi-select"

    options: dict[str, str] = dataclasses.field(default_factory=dict)

    select_color: str | list | None = dataclasses.field(default_factory=lambda: [0.8, 0.8, 0.8, 0.7])
    text_color: str | list | None = dataclasses.field(default_factory=lambda: [0.8, 0.8, 0.8, 0.7])
    font_size: int | None = 12
    font_family: str | None = "sans-serif"
    font_align: str = "left"
    active: bool = True

    # Display behavior (frontend uses these)
    max_labels_inline: int = 2
    placeholder: str = "Select…"

    # Optional: default selection(s) - list[str] recommended
    default_value: Any | None = dataclasses.field(default_factory=list)


@dataclasses.dataclass(kw_only=True)
class MultiSelectCell(Cell):
    """
    value: list[str] (preferred) or comma-separated str or None
    """
    value: list[str] | str | None = dataclasses.field(default_factory=list)

    def set(self, value: Any) -> None:
        """
        Normalize common forms:
        - None -> []
        - "a,b,c" -> ["a","b","c"]
        - ["a", "b"] -> ["a","b"]
        - any scalar -> ["<scalar>"]
        """
        if value is None:
            norm = []
        elif isinstance(value, list):
            norm = [str(x) for x in value]
        elif isinstance(value, str):
            s = value.strip()
            if not s:
                norm = []
            else:
                norm = [p.strip() for p in s.split(",") if p.strip()]
        else:
            norm = [str(value)]

        super().set(norm)


MultiSelectColumn.cell_cls = MultiSelectCell


# ======================================================================================================================
# Groups (optional)


@dataclasses.dataclass(kw_only=True)
class TableGroup:
    id: str
    title: str | None
    title_color: str | list | None = "white"
    collapsible: bool = False
    group_color: str | list | None = dataclasses.field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    rows: dict[str, Row] = dataclasses.field(default_factory=dict)
    _table: Table | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def make_row(self, *, id: str | None = None, **kwargs) -> Row:
        if id is None:
            id = generate_uuid(prefix="row_")

        row = Row(id=id, _table=self._table, group=self, cells={})
        update_dataclass_from_dict(row, kwargs)

        # Build cells for all existing columns
        for column_id, column in self._table.columns.items():
            value = kwargs[column_id] if column_id in kwargs else column.default_value
            cell = column.make_cell(value=value)
            cell.attach(row=row, column=column, table=self._table)
            row.cells[column_id] = cell

        self.add_row(row, index=kwargs.get("index"))
        return row

    # ------------------------------------------------------------------------------------------------------------------
    def add_row(self, row: Row, index: int | None = None) -> None:
        if index is None:
            index = len(self.rows)

        if row.id in self.rows:
            raise ValueError(f"Row with id {row.id} already exists.")

        # Ensure row knows its table
        row.table = self._table

        # Ensure row has all columns + attached cells
        for column_id, column in self._table.columns.items():
            if column_id not in row.cells:
                cell = column.make_cell()
                cell.attach(row=row, column=column, table=self._table)
                row.cells[column_id] = cell
            else:
                cell = row.cells[column_id]
                if cell.row is None or cell.column is None or cell.table is None:
                    cell.attach(row=row, column=column, table=self._table)

        self.rows[row.id] = row
        self._table.callbacks.row_added.call(row)

        self._table.function(
            function_name='add_row_from_config',
            args={
                'id': row.id,
                'config': row.get_configuration(),
            }
        )

    # ------------------------------------------------------------------------------------------------------------------
    def delete_row(self, row: str | Row) -> None:
        if isinstance(row, (str, int)):
            row = self.rows.get(row)

        if row is not None:
            del self.rows[row.id]
            self._table.callbacks.row_deleted.call(row)

        self._table.function(
            function_name='delete_row',
            args=row.id if row is not None else None,
        )

    def get_configuration(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "title_color": self.title_color,
            "collapsible": self.collapsible,
            "group_color": self.group_color,
            "rows": [item.get_configuration() for item in self.rows.values()],
        }


# ======================================================================================================================
# Table


class Table(Widget):
    type = 'table'
    columns: dict[str, Column]
    items: dict[str, Row | TableGroup]

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, widget_id: str | None = None, **kwargs):
        super().__init__(widget_id=widget_id, **kwargs)
        self.columns = {}
        self.items = {}
        self.callbacks = TableCallbacks()

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = super().getConfiguration()
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = super().getPayload()
        payload["table"] = self.get_table_payload()
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        event_name = message.get('event') if isinstance(message, dict) else None
        if event_name == 'cell_edit':
            data = message.get('data', {})
            row_id = data.get('row_id')
            column_id = data.get('column_id')
            value = data.get('value')
            row = self._find_row(row_id)
            if row is not None and column_id in row.cells:
                row.cells[column_id].update_request(value)
            else:
                self.logger.warning(f"cell_edit: row '{row_id}' or column '{column_id}' not found")
        else:
            self.logger.important(f"TableWidget received event {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def _find_row(self, row_id: str) -> Row | None:
        if row_id in self.items and isinstance(self.items[row_id], Row):
            return self.items[row_id]
        for item in self.items.values():
            if isinstance(item, TableGroup) and row_id in item.rows:
                return item.rows[row_id]
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def accept_cell(self, row_id: str, column_id: str, value) -> None:
        self.function('accept_cell', {'row_id': row_id, 'column_id': column_id, 'value': value})

    # ------------------------------------------------------------------------------------------------------------------
    def reject_cell(self, row_id: str, column_id: str) -> None:
        self.function('reject_cell', {'row_id': row_id, 'column_id': column_id})

    # ------------------------------------------------------------------------------------------------------------------
    def mark_cell_dirty(self, row_id: str, column_id: str) -> None:
        self.function('mark_cell_dirty', {'row_id': row_id, 'column_id': column_id})

    # ------------------------------------------------------------------------------------------------------------------
    def mark_cell_clean(self, row_id: str, column_id: str) -> None:
        self.function('mark_cell_clean', {'row_id': row_id, 'column_id': column_id})

    # ------------------------------------------------------------------------------------------------------------------
    def update_cell(self, cell: Cell):
        row_id = cell.row.id if cell.row is not None else None
        col_id = cell.column.id if cell.column is not None else None

        self.function(
            function_name='update_cell',
            args={
                'row': row_id,
                'column': col_id,
                'value': cell.value,
                'config': cell.get_configuration()
            }
        )

    # ------------------------------------------------------------------------------------------------------------------
    def make_row(self, *, id: str | None = None, **kwargs) -> Row:
        if id is None:
            id = generate_uuid(prefix="row_")

        if id in self.items:
            raise ValueError(f"Row with id {id} already exists.")

        row = Row(id=id, _table=self, cells={})
        update_dataclass_from_dict(row, kwargs)

        # Build cells for all existing columns
        for column_id, column in self.columns.items():
            value = kwargs[column_id] if column_id in kwargs else column.default_value
            cell = column.make_cell(value=value)
            cell.attach(row=row, column=column, table=self)
            row.cells[column_id] = cell

        self.add_row(row)
        return row

    # ------------------------------------------------------------------------------------------------------------------
    def add_row(self, row: Row) -> None:

        if row.id in self.items:
            raise ValueError(f"Row with id {row.id} already exists.")

        row._table = self

        # Ensure row has all columns + attached cells
        for column_id, column in self.columns.items():
            if column_id not in row.cells:
                cell = column.make_cell()
                cell.attach(row=row, column=column, table=self)
                row.cells[column_id] = cell
            else:
                cell = row.cells[column_id]
                if cell.row is None or cell.column is None or cell.table is None:
                    cell.attach(row=row, column=column, table=self)

        self.items[row.id] = row
        self.callbacks.row_added.call(row)

        self.function(
            function_name='add_row_from_config',
            args={
                'id': row.id,
                'config': row.get_configuration(),
            }
        )

    # ------------------------------------------------------------------------------------------------------------------
    def delete_row(self, row: str | int | Row) -> None:
        if isinstance(row, (str, int)):
            row = self.get_row(row)

        if row is not None:
            self.items.pop(row.id)
            self.callbacks.row_deleted.call(row)

        self.function(
            function_name='delete_row',
            args=row.id if row is not None else None,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def make_column(self, *, column_type: type[Column], id: str | None = None, **kwargs) -> Column:
        if id is None:
            id = generate_uuid(prefix="col_")
        column = column_type(id=id, _table=self, **kwargs)
        self.add_column(column)
        return column

    # ------------------------------------------------------------------------------------------------------------------
    def add_column(self, column: Column) -> Column:
        if column.id in self.columns:
            raise ValueError(f"Column with id {column.id} already exists.")

        column._table = self
        self.columns[column.id] = column

        # Backfill existing rows with attached cells
        for row in self.items.values():
            cell = column.make_cell()
            cell.attach(row=row, column=column, table=self)
            row.cells[column.id] = cell

        self.callbacks.column_added.call(column)

        self.function(
            function_name='add_column',
            args={
                'id': column.id,
                'config': column.get_configuration(),
            }
        )

        return column

    # ------------------------------------------------------------------------------------------------------------------
    def delete_column(self, column: str | Column) -> None:
        col_id = column if isinstance(column, str) else column.id
        try:
            col = self.columns.pop(col_id)
        except KeyError as e:
            raise KeyError(f"Column '{col_id}' not found.") from e

        for row in self.items.values():
            if isinstance(row, Row):
                row.cells.pop(col_id, None)

        self.function(
            function_name='delete_column',
            args={
                'id': col_id,
            }
        )

        self.callbacks.column_deleted.call(col)

    # # ----------------------------------------------------------------------------------------------------------------
    # def get_row_by_index(self, index: int) -> Row:
    #     return self.items[index]

    # ------------------------------------------------------------------------------------------------------------------
    def get_row_by_id(self, row_id: str) -> Row | None:
        if row_id not in self.items:
            return None
        return self.items[row_id]

    # ------------------------------------------------------------------------------------------------------------------
    def get_row(self, row: str | Row) -> Row | None:
        if isinstance(row, Row):
            return row

        if isinstance(row, str):
            return self.get_row_by_id(row)

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def get_table_payload(self) -> dict:
        return {
            "columns": {column.id: column.get_configuration() for column in self.columns.values()},
            "items": [row.get_configuration() for row in self.items.values()],
        }

    # ------------------------------------------------------------------------------------------------------------------
    def __getitem__(self, row: str | Row) -> Row | None:
        if isinstance(row, str):
            return self.get_row_by_id(row)
        if isinstance(row, Row):
            return row
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def __setitem__(self, row: str, value: Row) -> None:
        """
        Dict/list-like set:
        - table['row_id'] = row_obj  -> replace row with that id (or add if missing)
        - table[index] = row_obj     -> replace at index
        """
        if isinstance(row, str):
            existing = self.get_row(row)
            if existing is None:
                # Add new row (force id)
                value.id = row
                self.add_row(value)
                return
            else:
                raise NotImplementedError
