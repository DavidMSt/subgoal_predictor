# from __future__ import annotations
# import dataclasses
# import uuid
# from typing import Any, Callable
#
# from core.utils.callbacks import callback_definition, CallbackContainer
# from core.utils.events import event_definition, Event, EventFlag
# from extensions.gui.src.lib.objects.objects import Widget
#
#
# @callback_definition
# class CellCallbacks:
#     """Callbacks for cell events."""
#     cell_changed: CallbackContainer
#     cell_select_changed: CallbackContainer
#     cell_button_clicked: CallbackContainer
#
#
# @event_definition
# class CellEvents:
#     cell_changed: Event = Event(copy_data_on_set=False)
#     cell_select_changed: Event = Event(copy_data_on_set=False)
#     cell_button_clicked: Event = Event(copy_data_on_set=False)
#
#
# @dataclasses.dataclass
# class TableWidgetCell:
#     row: TableWidgetRow | None = None
#     column: TableWidgetColumn | None = None
#     table: TableWidget | None = None
#
#     cell_type: str = 'text'  # 'text', 'number', 'date', 'datetime', 'boolean', 'select', 'button', 'checkbox', 'input'
#     _value: Any | None = None
#     font_size: int | None = None  # pt
#     background_color: str | list | None = None
#     text_color: str | list | None = None
#     text_align: str | None = None  # can be None (inherit), 'left', 'center', or 'right'
#     editable: bool | None = None
#     font_weight: str | None = None
#     font_style: str | None = None
#     font_family: str | None = None
#     selectable: bool = False
#
#     button_color: str | list | None = None  # For 'button' types
#     disabled: bool = None  # Whether the button can be clicked
#
#     input_validator: Callable | None = None  # Custom validation function for 'input' types
#
#     select_options: list[str] | None = None  # For 'select' types
#     callbacks: CellCallbacks = dataclasses.field(default_factory=CellCallbacks)
#     events: CellEvents = dataclasses.field(default_factory=CellEvents)
#
#     def __post_init__(self):
#         self.events = CellEvents()
#
#     def update(self):
#         """Update the cell's value in the table."""
#         if self.table:
#             self.table.onCellChanged(self)
#
#     def set(self, value: Any) -> None:
#         """Set the cell's value (and notify the table)."""
#         self.value = value
#
#     # ------------------------------------------------------------------------------------------------------------------
#     @property
#     def value(self) -> Any | None:
#         return self._value
#
#     @value.setter
#     def value(self, new_value: Any) -> None:
#
#         if self.cell_type == 'select' and self.select_options is not None:
#             if new_value not in self.select_options:
#                 if self.table:
#                     self.table.logger.error(
#                         f"Value '{new_value}' is not in the select options for column '{self.column.column_id}'")
#                 self.value = self._value  # Reset to previous value
#                 return
#         elif self.cell_type == 'checkbox':
#             if isinstance(new_value, str):
#                 new_value = new_value.lower() in ['true', '1', 'yes']
#             elif isinstance(new_value, int):
#                 new_value = bool(new_value)
#
#             if not isinstance(new_value, bool):
#                 if self.table:
#                     self.table.logger.error(
#                         f"Checkbox cell value must be boolean, got {type(new_value).__name__} for column '{self.column.column_id}'")
#                 self.value = self._value  # Reset to previous value
#
#         elif self.cell_type == 'input':
#
#             valid = True
#
#             validator = self.input_validator if self.input_validator else self.column.input_validator if self.column else None
#             if validator:
#                 try:
#                     valid = validator(new_value)
#                 except Exception as e:
#                     valid = False
#
#             if not valid:
#                 new_value = self._value  # Reset to previous value
#
#             message = None
#             if not valid:
#                 message = f"Invalid input"
#
#             self.table.function(function_name='validateInputCell',
#                                 args={'row': self.row.id, 'column': self.column.column_id, 'valid': valid,
#                                       'value': new_value, 'message': message})
#
#             self._value = new_value
#             return  # We have to return early because we don't want to trigger the change event.
#             # We already did it in the validateInputCell function.
#
#         self._value = new_value
#         if self.table:
#             self.table.onCellChanged(self)
#
#     def serialize(self) -> dict:
#         """Return a JSON-serializable dict of this cell's data."""
#         return {
#             "row_id": self.row.id if self.row else None,
#             "column_id": self.column.column_id if self.column else None,
#             "value": self.value,
#             "font_size": self.font_size,
#             "background_color": self.background_color,
#             "text_color": self.text_color,
#             "text_align": self.text_align,
#             "editable": self.editable,
#             "font_weight": self.font_weight,
#             "font_style": self.font_style,
#             "font_family": self.font_family,
#             "selectable": self.selectable,
#             "select_options": self.select_options,
#             "cell_type": self.cell_type,
#             "button_color": self.button_color,
#             "disabled": self.disabled,
#         }
#
#
# @dataclasses.dataclass
# class TableWidgetColumn:
#     column_id: str
#     width: float | str = 'auto'  # Can also be a text indicating pixels or a float number indicating percentage
#     type: str = 'text'  # 'text', 'number', 'date', 'datetime', 'boolean', 'select', 'button', 'checkbox', 'input'
#     number_increment: float | None = None  # For 'number' type, step increment, like 0.01
#     font_size: int | None = None  # pt
#     title: str = ''
#     background_color: str | list | None = None
#     header_background_color: str | list | None = None
#     header_text_color: str | list | None = None
#     text_align: str = 'center'  # can be 'center', 'left', 'right'
#     text_color: str | list | None = None
#     editable: bool | None = False
#     selectable: bool = True
#     font_family: str | None = None
#     font_weight: str | None = None  # can be 'normal', 'bold', 'bolder', 'lighter'
#     default_value: Any | None = None  # Default value for new cells in this column
#     default_select_options: list[str] | None = None  # For 'select' type columns
#
#     button_color: str | list | None = dataclasses.field(
#         default_factory=lambda: [0.2, 0.2, 0.2])  # For 'button' type columns
#
#     disabled: bool = False  # Whether the column is disabled (no interaction allowed)
#
#     input_validator: None = dataclasses.field(default=None)
#
#     def serialize(self) -> dict:
#         """Return a JSON-serializable dict of this column's data."""
#         data = dataclasses.asdict(self)
#         data.pop("input_validator", None)
#         return data
#
#
# @dataclasses.dataclass
# class TableWidgetRow:
#     id: str
#     index: int
#     font_size: int | None = None  # pt
#     background_color: str | list | None = None
#     text_align: str | None = None  # can be 'center', 'left', 'right'
#     text_color: str | list | None = None
#     font_family: str | None = None
#     editable: bool | None = None
#     line_width: int | None = None
#
#     cells: list[TableWidgetCell] = dataclasses.field(default_factory=list)
#
#     def getCell(self, column: TableWidgetColumn | str | None = None) -> TableWidgetCell | None:
#         """Retrieve the cell in this row for the given column (by id or object)."""
#         if column is None:
#             return None
#         col_id = column.column_id if isinstance(column, TableWidgetColumn) else column
#         for cell in self.cells:
#             if cell.column and cell.column.column_id == col_id:
#                 return cell
#         return None
#
#     def serialize(self) -> dict:
#         """Return a JSON-serializable dict of this row and its cells."""
#         return {
#             "row_id": self.id,
#             "index": self.index,
#             "font_size": self.font_size,
#             "background_color": self.background_color,
#             "text_align": self.text_align,
#             "text_color": self.text_color,
#             "font_family": self.font_family,
#             "editable": self.editable,
#             "line_width": self.line_width,
#             "cells": [cell.serialize() for cell in self.cells],
#         }
#
#
# @callback_definition
# class TableWidgetCallbacks:
#     row_selected: CallbackContainer
#     cell_selected: CallbackContainer
#     cell_changed: CallbackContainer
#
#     cell_button_clicked: CallbackContainer
#     cell_select_changed: CallbackContainer
#     cell_checkbox_changed: CallbackContainer
#
#
# @event_definition
# class TableWidgetEvents:
#     row_selected: Event = Event(copy_data_on_set=False)
#     cell_selected: Event = Event(copy_data_on_set=False)
#     cell_changed: Event = Event(copy_data_on_set=False, flags=[EventFlag('row', str), EventFlag('column', str)])
#
#     cell_select_changed: Event = Event(copy_data_on_set=False,
#                                        flags=[EventFlag('row', str), EventFlag('column', str)])
#
#     cell_button_clicked: Event = Event(copy_data_on_set=False,
#                                        flags=[EventFlag('row', str), EventFlag('column', str)])
#     # Backend-generated events
#     row_added: Event = Event(copy_data_on_set=False)
#     row_removed: Event = Event(copy_data_on_set=False)
#     column_added: Event = Event(copy_data_on_set=False)
#     column_removed: Event = Event(copy_data_on_set=False)
#
#
# @dataclasses.dataclass
# class CellChangedMessage:
#     row: str
#     column: str
#     data: dict
#     type: str = 'cell_change'
#
#
# @dataclasses.dataclass
# class RowAddedMessage:
#     data: dict
#     type: str = 'row_added'
#
#
# class TableWidget(Widget):
#     type = 'table'
#
#     def __init__(self, widget_id: str = None, **kwargs):
#         super().__init__(widget_id)
#         default_config = {
#             'title': None,
#             'has_header': True,
#             'header_background_color': 'transparent',
#             'header_font_size': 10,
#             'header_font_weight': 'bold',
#             'header_font_style': 'normal',
#             'header_text_color': [1, 1, 1, 0.8],
#             'text_color': [1, 1, 1, 0.8],
#             'font_size': 10,
#             'vertical_fit': False,
#             'line_width': 1,
#             'line_color': [1, 1, 1, 0.3],
#             'background_color': 'transparent',
#         }
#         self.config = {**default_config, **kwargs}
#         self.columns: dict[str, TableWidgetColumn] = {}
#         self.rows: dict[str, TableWidgetRow] = {}
#
#         self.callbacks = TableWidgetCallbacks()
#         self.events = TableWidgetEvents()
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def addRow(
#             self,
#             id: str | None = None,
#             index: int | None = None,
#             row: TableWidgetRow | None = None,
#             cells: list[Any | TableWidgetCell] | None = None,
#             **kwargs
#     ) -> TableWidgetRow:
#         """Add a new row (or insert at index), creating cells for each column."""
#         # Generate or override ID
#         row_id = id or (row.id if row else uuid.uuid4().hex)
#         # Compute index
#         if index is None:
#             index = max((r.index for r in self.rows.values()), default=-1) + 1
#         else:
#             # bump existing rows at or after this index
#             for r in self.rows.values():
#                 if r.index >= index:
#                     r.index += 1
#
#         # Prepare the row object
#         if row:
#             row.id = row_id
#             row.index = index
#         else:
#             row = TableWidgetRow(id=row_id, index=index, **kwargs)
#
#         # Build cells list
#         row.cells = []
#         cols = list(self.columns.values())
#         for idx, col in enumerate(cols):
#             raw = None
#             if cells and idx < len(cells):
#                 raw = cells[idx]
#             if isinstance(raw, TableWidgetCell):
#                 cell = raw
#                 cell.row = row
#                 cell.column = col
#                 cell.table = self
#             else:
#                 if raw is not None and col.type == 'select' and raw not in col.default_select_options:
#                     raise ValueError(
#                         f"Value '{raw}' for column '{col.column_id}' is not in the default select options.")
#
#                 if raw is not None:
#                     cell_value = raw
#                 else:
#                     cell_value = col.default_value if col.default_value is not None else None
#                 cell = TableWidgetCell(
#                     row=row,
#                     column=col,
#                     table=self,
#                     _value=cell_value,
#                     select_options=col.default_select_options if col.default_select_options else None,
#                     cell_type=col.type,
#                 )
#             row.cells.append(cell)
#
#         # Save and trigger event
#         self.rows[row_id] = row
#
#         self.events.row_added.set(row)
#
#         message = RowAddedMessage(data=row.serialize())
#         self.sendUpdate(message, important=True)
#
#         return row
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def addColumn(
#             self,
#             id: str | None = None,
#             title: str | None = None,
#             column: TableWidgetColumn | None = None,
#             default_value: Any = None,
#             **kwargs
#
#     ) -> TableWidgetColumn:
#         """Add a new column, filling existing rows with empty cells."""
#         # Generate or override ID
#         col_id = id or (column.column_id if column else uuid.uuid4().hex)
#         # Prepare column object
#         if column:
#             column.column_id = col_id
#             column.title = title or column.title or col_id
#         else:
#             column = TableWidgetColumn(
#                 column_id=col_id,
#                 title=title or col_id,
#                 default_value=default_value,
#                 **kwargs
#             )
#         # Save column
#         self.columns[col_id] = column
#         # Append a cell to each existing row
#         for row in self.rows.values():
#             cell = TableWidgetCell(
#                 row=row,
#                 column=column,
#                 table=self,
#                 _value=default_value
#             )
#             row.cells.append(cell)
#         # Trigger event
#         self.events.column_added.set(column)
#         self.updateConfig()
#         return column
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def deleteColumn(self, column: str | TableWidgetColumn) -> None:
#         """Remove a column and its cells from all rows."""
#         # Resolve column object
#         col_obj = column if isinstance(column, TableWidgetColumn) else self.columns.get(column)
#         if not col_obj:
#             return
#         # Remove from the registry
#         self.columns.pop(col_obj.column_id, None)
#         # Remove cells in each row
#         for row in self.rows.values():
#             row.cells = [c for c in row.cells if c.column and c.column.column_id != col_obj.column_id]
#         # Trigger event
#         self.events.column_removed.set(col_obj)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def getRow(self, row_id: str | None = None, row_index: int | None = None) -> TableWidgetRow | None:
#         """Fetch a row by its ID or index."""
#         if row_id is not None:
#             return self.rows.get(row_id)
#         if row_index is not None:
#             for row in self.rows.values():
#                 if row.index == row_index:
#                     return row
#         return None
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def deleteRow(self, row: str | int | TableWidgetRow) -> None:
#         """Delete a row (by ID, index, or object) and reindex remaining rows."""
#         # Resolve row object
#         if isinstance(row, TableWidgetRow):
#             row_obj = row
#         elif isinstance(row, str):
#             row_obj = self.getRow(row_id=row)
#         elif isinstance(row, int):
#             row_obj = self.getRow(row_index=row)
#         else:
#             row_obj = None
#         if not row_obj or row_obj.id not in self.rows:
#             return
#         # Remove and trigger
#         self.rows.pop(row_obj.id)
#         self.events.row_removed.set(row_obj)
#         # Reindex remaining rows sequentially
#         for new_index, r in enumerate(sorted(self.rows.values(), key=lambda r: r.index)):
#             r.index = new_index
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def getColumn(self, column_id: str | None = None) -> TableWidgetColumn | None:
#         """Fetch a column by its ID."""
#         if column_id is None:
#             return None
#         return self.columns.get(column_id)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def getCell(
#             self,
#             row: TableWidgetRow | str | int | None = None,
#             column: TableWidgetColumn | str | None = None
#     ) -> TableWidgetCell | None:
#         """Retrieve a single cell by row and column identifiers."""
#         # Resolve row
#         if isinstance(row, TableWidgetRow):
#             row_obj = row
#         elif isinstance(row, str):
#             row_obj = self.getRow(row_id=row)
#         elif isinstance(row, int):
#             row_obj = self.getRow(row_index=row)
#         else:
#             row_obj = None
#         # Resolve column
#         if isinstance(column, TableWidgetColumn):
#             col_obj = column
#         elif isinstance(column, str):
#             col_obj = self.getColumn(column)
#         else:
#             col_obj = None
#         if not row_obj or not col_obj:
#             return None
#         return row_obj.getCell(col_obj)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def onCellChanged(self, cell: TableWidgetCell) -> None:
#         """Internal: called when a cell's value changes."""
#         # Trigger backend event
#         self.events.cell_changed.set(cell)
#         # Notify any registered callbacks
#         self.callbacks.cell_changed.call(cell)
#
#         message = CellChangedMessage(
#             row=cell.row.id if cell.row else None,
#             column=cell.column.column_id if cell.column else None,
#             data=cell.serialize()
#         )
#
#         self.sendUpdate(message, important=True)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def getConfiguration(self) -> dict:
#         """Return a JSON-serializable configuration for the frontend, using each object's serialize()."""
#         config = {
#             'columns': {col_id: col.serialize() for col_id, col in self.columns.items()},
#             'rows': {row_id: row.serialize() for row_id, row in self.rows.items()},
#             **self.config
#         }
#         return config
#
#     def handleEvent(self, message, sender=None) -> Any:
#         data = message.get('data')
#         if data is None:
#             self.logger.error("Received message without 'data' field")
#             return
#         match message.get('event'):
#             case 'select':
#                 row_id = data.get('row_id')
#                 column_id = data.get('column_id')
#                 value = data.get('value')
#                 cell = self.getCell(row=row_id, column=column_id)
#                 if cell:
#                     cell.set(value)
#                     self.callbacks.cell_select_changed.call(cell)
#                     self.events.cell_select_changed.set(data=cell, flags={'row': row_id, 'column': column_id})
#                     cell.callbacks.cell_select_changed.call()
#                     cell.events.cell_select_changed.set()
#                 else:
#                     self.logger.error(f"Cell {row_id}/{column_id} not found")
#             case 'button':
#                 row_id = data.get('row_id')
#                 column_id = data.get('column_id')
#                 cell = self.getCell(row=row_id, column=column_id)
#                 if cell:
#                     self.callbacks.cell_button_clicked.call(cell)
#                     self.events.cell_button_clicked.set(data=cell, flags={'row': row_id, 'column': column_id})
#                     cell.callbacks.cell_button_clicked.call()
#                     cell.events.cell_button_clicked.set()
#                 else:
#                     self.logger.error(f"Button cell {row_id}/{column_id} not found")
#             case 'checkbox':
#                 row_id = data.get('row_id')
#                 column_id = data.get('column_id')
#                 value = data.get('value')
#                 cell = self.getCell(row=row_id, column=column_id)
#                 if cell:
#                     cell.value = value
#                     self.callbacks.cell_checkbox_changed.call(cell)
#                     self.events.cell_select_changed.set(data=cell, flags={'row': row_id, 'column': column_id})
#                     cell.callbacks.cell_select_changed.call()
#                     cell.events.cell_select_changed.set()
#                 else:
#                     self.logger.error(f"Checkbox cell {row_id}/{column_id} not found")
#             case 'input':
#                 row_id = data.get('row_id')
#                 column_id = data.get('column_id')
#                 value = data.get('value')
#                 cell = self.getCell(row=row_id, column=column_id)
#                 if cell:
#                     cell.set(value)
#                     self.callbacks.cell_changed.call(cell)
#                     self.events.cell_changed.set(data=cell, flags={'row': row_id, 'column': column_id})
#                     cell.callbacks.cell_changed.call()
#                     cell.events.cell_changed.set()
#                 else:
#                     self.logger.error(f"Input cell {row_id}/{column_id} not found")
#             case _:
#                 self.logger.warning(f"Unknown message event: {message.get('event')} with data: {data}")
#
#     def init(self, *args, **kwargs):
#         pass


from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Callable

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event, EventFlag
from extensions.gui.src.lib.objects.objects import Widget


# ======================================================================================================================
# Cells
# ======================================================================================================================

@callback_definition
class CellCallbacks:
    """Callbacks for cell events."""
    cell_changed: CallbackContainer
    cell_select_changed: CallbackContainer
    cell_button_clicked: CallbackContainer


@event_definition
class CellEvents:
    cell_changed: Event = Event(copy_data_on_set=False)
    cell_select_changed: Event = Event(copy_data_on_set=False)
    cell_button_clicked: Event = Event(copy_data_on_set=False)


@dataclasses.dataclass
class TableWidgetCell:
    row: TableWidgetRow | None = None
    column: TableWidgetColumn | None = None
    table: TableWidget | None = None

    cell_type: str = 'text'  # 'text', 'number', 'date', 'datetime', 'boolean', 'select', 'button', 'checkbox', 'input'
    _value: Any | None = None
    font_size: int | None = None  # pt
    background_color: str | list | None = None
    text_color: str | list | None = None
    text_align: str | None = None  # can be None (inherit), 'left', 'center', or 'right'
    editable: bool | None = None
    font_weight: str | None = None
    font_style: str | None = None
    font_family: str | None = None
    selectable: bool = False

    button_color: str | list | None = None  # For 'button' types
    disabled: bool = None  # Whether the button can be clicked

    input_validator: Callable | None = None  # Custom validation function for 'input' types

    select_options: list[str] | None = None  # For 'select' types
    callbacks: CellCallbacks = dataclasses.field(default_factory=CellCallbacks)
    events: CellEvents = dataclasses.field(default_factory=CellEvents)

    def __post_init__(self):
        self.events = CellEvents()

    def update(self):
        """Update the cell's value in the table."""
        if self.table:
            self.table.onCellChanged(self)

    def set(self, value: Any) -> None:
        """Set the cell's value (and notify the table)."""
        self.value = value

    @property
    def value(self) -> Any | None:
        return self._value

    @value.setter
    def value(self, new_value: Any) -> None:
        # --- validate types -------------------------------------------------
        if self.cell_type == 'select' and self.select_options is not None:
            if new_value not in self.select_options:
                if self.table:
                    self.table.logger.error(
                        f"Value '{new_value}' is not in the select options for column '{self.column.column_id}'")
                self._value = self._value
                return

        elif self.cell_type == 'checkbox':
            if isinstance(new_value, str):
                new_value = new_value.lower() in ['true', '1', 'yes']
            elif isinstance(new_value, int):
                new_value = bool(new_value)

            if not isinstance(new_value, bool):
                if self.table:
                    self.table.logger.error(
                        f"Checkbox cell value must be boolean, got {type(new_value).__name__} "
                        f"for column '{self.column.column_id}'")
                self._value = self._value
                return

        elif self.cell_type == 'input':
            valid = True
            validator = self.input_validator if self.input_validator else self.column.input_validator if self.column else None
            if validator:
                try:
                    valid = validator(new_value)
                except Exception:
                    valid = False

            if not valid:
                new_value = self._value

            message = None if valid else "Invalid input"

            # IMPORTANT: validation on frontend should not trigger normal "cell_change" twice
            if self.table and self.row and self.column:
                self.table.function(
                    function_name='validateInputCell',
                    args={
                        'row': self.row.id,
                        'column': self.column.column_id,
                        'valid': valid,
                        'value': new_value,
                        'message': message
                    }
                )

            self._value = new_value
            return

        # --- normal commit --------------------------------------------------
        self._value = new_value
        if self.table:
            self.table.onCellChanged(self)

    def serialize(self) -> dict:
        return {
            "row_id": self.row.id if self.row else None,
            "column_id": self.column.column_id if self.column else None,
            "value": self.value,
            "font_size": self.font_size,
            "background_color": self.background_color,
            "text_color": self.text_color,
            "text_align": self.text_align,
            "editable": self.editable,
            "font_weight": self.font_weight,
            "font_style": self.font_style,
            "font_family": self.font_family,
            "selectable": self.selectable,
            "select_options": self.select_options,
            "cell_type": self.cell_type,
            "button_color": self.button_color,
            "disabled": self.disabled,
        }


# ======================================================================================================================
# Row/Column
# ======================================================================================================================

@dataclasses.dataclass
class TableWidgetColumn:
    column_id: str
    width: float | str = 'auto'
    type: str = 'text'
    number_increment: float | None = None
    font_size: int | None = None
    title: str = ''
    background_color: str | list | None = None
    header_background_color: str | list | None = None
    header_text_color: str | list | None = None
    text_align: str = 'center'
    text_color: str | list | None = None
    editable: bool | None = False
    selectable: bool = True
    font_family: str | None = None
    font_weight: str | None = None
    default_value: Any | None = None
    default_select_options: list[str] | None = None

    button_color: str | list | None = dataclasses.field(default_factory=lambda: [0.2, 0.2, 0.2])
    disabled: bool = False
    input_validator: None = dataclasses.field(default=None)

    def serialize(self) -> dict:
        data = dataclasses.asdict(self)
        data.pop("input_validator", None)
        return data


@dataclasses.dataclass
class TableWidgetRow:
    id: str
    index: int
    font_size: int | None = None
    background_color: str | list | None = None
    text_align: str | None = None
    text_color: str | list | None = None
    font_family: str | None = None
    editable: bool | None = None
    line_width: int | None = None

    cells: list[TableWidgetCell] = dataclasses.field(default_factory=list)

    def getCell(self, column: TableWidgetColumn | str | None = None) -> TableWidgetCell | None:
        if column is None:
            return None
        col_id = column.column_id if isinstance(column, TableWidgetColumn) else column
        for cell in self.cells:
            if cell.column and cell.column.column_id == col_id:
                return cell
        return None

    # Ergonomics: row["x"] / row["x"]=...
    def __getitem__(self, column_id: str) -> Any:
        cell = self.getCell(column_id)
        return cell.value if cell else None

    def __setitem__(self, column_id: str, value: Any) -> None:
        cell = self.getCell(column_id)
        if cell:
            cell.set(value)

    def serialize(self) -> dict:
        return {
            "row_id": self.id,
            "index": self.index,
            "font_size": self.font_size,
            "background_color": self.background_color,
            "text_align": self.text_align,
            "text_color": self.text_color,
            "font_family": self.font_family,
            "editable": self.editable,
            "line_width": self.line_width,
            "cells": [cell.serialize() for cell in self.cells],
        }


# ======================================================================================================================
# Callbacks/Events
# ======================================================================================================================

@callback_definition
class TableWidgetCallbacks:
    row_selected: CallbackContainer
    cell_selected: CallbackContainer
    cell_changed: CallbackContainer

    cell_button_clicked: CallbackContainer
    cell_select_changed: CallbackContainer
    cell_checkbox_changed: CallbackContainer


@event_definition
class TableWidgetEvents:
    row_selected: Event = Event(copy_data_on_set=False)
    cell_selected: Event = Event(copy_data_on_set=False)
    cell_changed: Event = Event(copy_data_on_set=False, flags=[EventFlag('row', str), EventFlag('column', str)])

    cell_select_changed: Event = Event(copy_data_on_set=False, flags=[EventFlag('row', str), EventFlag('column', str)])
    cell_button_clicked: Event = Event(copy_data_on_set=False, flags=[EventFlag('row', str), EventFlag('column', str)])

    # Backend-generated events
    row_added: Event = Event(copy_data_on_set=False)
    row_removed: Event = Event(copy_data_on_set=False)
    rows_reindexed: Event = Event(copy_data_on_set=False)

    column_added: Event = Event(copy_data_on_set=False)
    column_removed: Event = Event(copy_data_on_set=False)


# ======================================================================================================================
# Update Message Types (backend -> frontend)
# ======================================================================================================================

@dataclasses.dataclass
class CellChangedMessage:
    row: str
    column: str
    data: dict
    type: str = 'cell_change'


@dataclasses.dataclass
class RowAddedMessage:
    data: dict
    type: str = 'row_added'


@dataclasses.dataclass
class RowRemovedMessage:
    data: dict  # {row_id: "..."}
    type: str = 'row_removed'


@dataclasses.dataclass
class RowsReindexedMessage:
    data: dict  # {rows: [{row_id, index}, ...]}
    type: str = 'rows_reindexed'


@dataclasses.dataclass
class ColumnAddedMessage:
    data: dict  # {column: {...}, index: int}
    type: str = 'column_added'


@dataclasses.dataclass
class ColumnRemovedMessage:
    data: dict  # {column_id: "..."}
    type: str = 'column_removed'


# ======================================================================================================================
# Table Widget
# ======================================================================================================================

class TableWidget(Widget):
    type = 'table'

    def __init__(self, widget_id: str = None, **kwargs):
        super().__init__(widget_id)

        default_config = {
            'title': None,
            'has_header': True,
            'header_background_color': 'transparent',
            'header_font_size': 10,
            'header_font_weight': 'bold',
            'header_font_style': 'normal',
            'header_text_color': [1, 1, 1, 0.8],
            'text_color': [1, 1, 1, 0.8],
            'font_size': 10,
            'vertical_fit': False,
            'line_width': 1,
            'line_color': [1, 1, 1, 0.3],
            'background_color': 'transparent',
        }
        self.config = {**default_config, **kwargs}

        self.columns: dict[str, TableWidgetColumn] = {}
        self.rows: dict[str, TableWidgetRow] = {}

        # preserve deterministic order
        self._column_order: list[str] = []
        self._row_order: list[str] = []

        self.callbacks = TableWidgetCallbacks()
        self.events = TableWidgetEvents()

    # ------------------------------------------------------------------------------------------------------------------
    # Convenience API
    # ------------------------------------------------------------------------------------------------------------------

    def row(self, row_id: str) -> TableWidgetRow | None:
        return self.getRow(row_id=row_id)

    def col(self, column_id: str) -> TableWidgetColumn | None:
        return self.getColumn(column_id)

    def cell(self, row: str | int | TableWidgetRow, column: str | TableWidgetColumn) -> TableWidgetCell | None:
        return self.getCell(row=row, column=column)

    def set(self, row_id: str, column_id: str, value: Any) -> None:
        c = self.getCell(row=row_id, column=column_id)
        if c:
            c.set(value)

    def setRow(self, row_id: str, **column_values) -> None:
        r = self.getRow(row_id=row_id)
        if not r:
            return
        for k, v in column_values.items():
            cell = r.getCell(k)
            if cell:
                cell.set(v)

    # ------------------------------------------------------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _row_field_names() -> set[str]:
        return {f.name for f in dataclasses.fields(TableWidgetRow) if f.init and f.name not in ('cells', 'id', 'index')}

    def _columns_in_order(self) -> list[TableWidgetColumn]:
        cols = []
        for cid in self._column_order:
            c = self.columns.get(cid)
            if c:
                cols.append(c)
        # fallback for any columns not in order list
        for cid, c in self.columns.items():
            if cid not in self._column_order:
                cols.append(c)
        return cols

    def _rows_in_order(self) -> list[TableWidgetRow]:
        rows = list(self.rows.values())
        rows.sort(key=lambda r: r.index)
        return rows

    def _emit_rows_reindexed(self) -> None:
        payload = {"rows": [{"row_id": r.id, "index": r.index} for r in self._rows_in_order()]}
        self.events.rows_reindexed.set(payload)
        self.sendUpdate(RowsReindexedMessage(data=payload), important=True)

    # ------------------------------------------------------------------------------------------------------------------
    # Row/Column mutations (LIVE updates)
    # ------------------------------------------------------------------------------------------------------------------

    def addRow(
            self,
            id: str | None = None,
            index: int | None = None,
            row: TableWidgetRow | None = None,
            cells: list[Any | TableWidgetCell] | None = None,
            values: dict[str, Any] | None = None,
            **kwargs
    ) -> TableWidgetRow:
        """
        Add a row.

        Usability improvements:
          - You can pass column-id kwargs directly:
              table.addRow(id="a", object_id="a", valid="❌", x=1.2)
          - You can also pass values={...}
          - Row styling kwargs still work (font_size=..., background_color=..., etc.)
        """
        row_id = id or (row.id if row else uuid.uuid4().hex)

        # split kwargs into row-style fields vs column values
        row_fields = self._row_field_names()
        row_kwargs = {k: v for k, v in kwargs.items() if k in row_fields}
        col_kwargs = {k: v for k, v in kwargs.items() if k not in row_fields}

        # merge provided value sources (priority: explicit cells list > kwargs/values > defaults)
        value_map: dict[str, Any] = {}
        if values:
            value_map.update(values)
        value_map.update(col_kwargs)

        # compute insertion index
        if index is None:
            index = max((r.index for r in self.rows.values()), default=-1) + 1
        else:
            # bump existing rows at or after this index
            for r in self.rows.values():
                if r.index >= index:
                    r.index += 1

        # create/normalize row object
        if row:
            row.id = row_id
            row.index = index
            for k, v in row_kwargs.items():
                setattr(row, k, v)
        else:
            row = TableWidgetRow(id=row_id, index=index, **row_kwargs)

        # build cells in column order
        row.cells = []
        cols = self._columns_in_order()
        for idx, col in enumerate(cols):
            raw = None

            # highest priority: explicit list by column order
            if cells and idx < len(cells):
                raw = cells[idx]
            else:
                # next: values map by column_id
                if col.column_id in value_map:
                    raw = value_map[col.column_id]

            if isinstance(raw, TableWidgetCell):
                cell = raw
                cell.row = row
                cell.column = col
                cell.table = self
            else:
                if raw is not None:
                    cell_value = raw
                else:
                    cell_value = col.default_value if col.default_value is not None else None

                cell = TableWidgetCell(
                    row=row,
                    column=col,
                    table=self,
                    _value=cell_value,
                    select_options=col.default_select_options if col.default_select_options else None,
                    cell_type=col.type,
                )

            row.cells.append(cell)

        self.rows[row_id] = row
        if row_id not in self._row_order:
            self._row_order.append(row_id)

        self.events.row_added.set(row)
        self.sendUpdate(RowAddedMessage(data=row.serialize()), important=True)

        print("XXXX")
        # if we inserted into the middle, indices shifted => keep frontend ordering correct
        self._emit_rows_reindexed()

        return row

    def deleteRow(self, row: str | int | TableWidgetRow) -> None:
        """Delete a row (by id, index, or object) and keep the frontend in sync live."""
        if isinstance(row, TableWidgetRow):
            row_obj = row
        elif isinstance(row, str):
            row_obj = self.getRow(row_id=row)
        elif isinstance(row, int):
            row_obj = self.getRow(row_index=row)
        else:
            row_obj = None

        if not row_obj or row_obj.id not in self.rows:
            return

        removed = self.rows.pop(row_obj.id, None)
        if removed and removed.id in self._row_order:
            self._row_order.remove(removed.id)

        self.events.row_removed.set(row_obj)
        self.sendUpdate(RowRemovedMessage(data={"row_id": row_obj.id}), important=True)

        # reindex sequentially (keeps your original behavior)
        for new_index, r in enumerate(sorted(self.rows.values(), key=lambda r: r.index)):
            r.index = new_index

        self._emit_rows_reindexed()

    def addColumn(
            self,
            id: str | None = None,
            title: str | None = None,
            index: int | None = None,
            column: TableWidgetColumn | None = None,
            default_value: Any = None,
            **kwargs
    ) -> TableWidgetColumn:
        """Add a column and live-update the frontend (no full refresh)."""
        col_id = id or (column.column_id if column else uuid.uuid4().hex)

        if column:
            column.column_id = col_id
            column.title = title or column.title or col_id
            if default_value is not None:
                column.default_value = default_value
        else:
            column = TableWidgetColumn(
                column_id=col_id,
                title=title or col_id,
                default_value=default_value,
                **kwargs
            )

        self.columns[col_id] = column

        # insert into order list
        if col_id not in self._column_order:
            if index is None or index >= len(self._column_order):
                self._column_order.append(col_id)
                col_index = len(self._column_order) - 1
            else:
                self._column_order.insert(index, col_id)
                col_index = index
        else:
            col_index = self._column_order.index(col_id)

        # append a cell to each row, matching the new column position
        for row in self.rows.values():
            new_cell = TableWidgetCell(row=row, column=column, table=self, _value=column.default_value)
            # insert at correct position
            cols = self._columns_in_order()
            insert_pos = next((i for i, c in enumerate(cols) if c.column_id == col_id), len(row.cells))
            row.cells.insert(insert_pos, new_cell)

        self.events.column_added.set(column)
        self.sendUpdate(ColumnAddedMessage(data={"column": column.serialize(), "index": col_index}), important=True)

        return column

    def deleteColumn(self, column: str | TableWidgetColumn) -> None:
        """Remove a column and live-update the frontend."""
        col_obj = column if isinstance(column, TableWidgetColumn) else self.columns.get(column)
        if not col_obj:
            return

        col_id = col_obj.column_id

        self.columns.pop(col_id, None)
        if col_id in self._column_order:
            self._column_order.remove(col_id)

        for row in self.rows.values():
            row.cells = [c for c in row.cells if c.column and c.column.column_id != col_id]

        self.events.column_removed.set(col_obj)
        self.sendUpdate(ColumnRemovedMessage(data={"column_id": col_id}), important=True)

    # ------------------------------------------------------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------------------------------------------------------

    def getRow(self, row_id: str | None = None, row_index: int | None = None) -> TableWidgetRow | None:
        if row_id is not None:
            return self.rows.get(row_id)
        if row_index is not None:
            for row in self.rows.values():
                if row.index == row_index:
                    return row
        return None

    def getColumn(self, column_id: str | None = None) -> TableWidgetColumn | None:
        if column_id is None:
            return None
        return self.columns.get(column_id)

    def getCell(
            self,
            row: TableWidgetRow | str | int | None = None,
            column: TableWidgetColumn | str | None = None
    ) -> TableWidgetCell | None:
        if isinstance(row, TableWidgetRow):
            row_obj = row
        elif isinstance(row, str):
            row_obj = self.getRow(row_id=row)
        elif isinstance(row, int):
            row_obj = self.getRow(row_index=row)
        else:
            row_obj = None

        if isinstance(column, TableWidgetColumn):
            col_obj = column
        elif isinstance(column, str):
            col_obj = self.getColumn(column)
        else:
            col_obj = None

        if not row_obj or not col_obj:
            return None
        return row_obj.getCell(col_obj)

    # ------------------------------------------------------------------------------------------------------------------
    # Cell changed
    # ------------------------------------------------------------------------------------------------------------------

    def onCellChanged(self, cell: TableWidgetCell) -> None:
        self.events.cell_changed.set(cell)
        self.callbacks.cell_changed.call(cell)

        message = CellChangedMessage(
            row=cell.row.id if cell.row else None,
            column=cell.column.column_id if cell.column else None,
            data=cell.serialize()
        )
        self.sendUpdate(message, important=True)

    # ------------------------------------------------------------------------------------------------------------------
    # Configuration payload
    # ------------------------------------------------------------------------------------------------------------------

    def getConfiguration(self) -> dict:
        # NOTE: preserve deterministic order by emitting rows/cols ordered
        cols = {col.column_id: col.serialize() for col in self._columns_in_order()}
        rows = {row.id: row.serialize() for row in self._rows_in_order()}

        config = {
            'columns': cols,
            'rows': rows,
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    # Frontend -> backend events
    # ------------------------------------------------------------------------------------------------------------------

    def handleEvent(self, message, sender=None) -> Any:
        data = message.get('data')
        if data is None:
            self.logger.error("Received message without 'data' field")
            return

        match message.get('event'):
            case 'select':
                row_id = data.get('row_id')
                column_id = data.get('column_id')
                value = data.get('value')
                cell = self.getCell(row=row_id, column=column_id)
                if cell:
                    cell.set(value)
                    self.callbacks.cell_select_changed.call(cell)
                    self.events.cell_select_changed.set(data=cell, flags={'row': row_id, 'column': column_id})
                    cell.callbacks.cell_select_changed.call()
                    cell.events.cell_select_changed.set()
                else:
                    self.logger.error(f"Cell {row_id}/{column_id} not found")

            case 'button':
                row_id = data.get('row_id')
                column_id = data.get('column_id')
                cell = self.getCell(row=row_id, column=column_id)
                if cell:
                    self.callbacks.cell_button_clicked.call(cell)
                    self.events.cell_button_clicked.set(data=cell, flags={'row': row_id, 'column': column_id})
                    cell.callbacks.cell_button_clicked.call()
                    cell.events.cell_button_clicked.set()
                else:
                    self.logger.error(f"Button cell {row_id}/{column_id} not found")

            case 'checkbox':
                row_id = data.get('row_id')
                column_id = data.get('column_id')
                value = data.get('value')
                cell = self.getCell(row=row_id, column=column_id)
                if cell:
                    cell.value = value
                    self.callbacks.cell_checkbox_changed.call(cell)
                    self.events.cell_select_changed.set(data=cell, flags={'row': row_id, 'column': column_id})
                    cell.callbacks.cell_select_changed.call()
                    cell.events.cell_select_changed.set()
                else:
                    self.logger.error(f"Checkbox cell {row_id}/{column_id} not found")

            case 'input':
                row_id = data.get('row_id')
                column_id = data.get('column_id')
                value = data.get('value')
                cell = self.getCell(row=row_id, column=column_id)
                if cell:
                    cell.set(value)
                    self.callbacks.cell_changed.call(cell)
                    self.events.cell_changed.set(data=cell, flags={'row': row_id, 'column': column_id})
                    cell.callbacks.cell_changed.call()
                    cell.events.cell_changed.set()
                else:
                    self.logger.error(f"Input cell {row_id}/{column_id} not found")

            case _:
                self.logger.warning(f"Unknown message event: {message.get('event')} with data: {data}")

    def init(self, *args, **kwargs):
        pass
