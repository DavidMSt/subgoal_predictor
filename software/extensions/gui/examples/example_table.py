# import time
#
# from extensions.gui.src.gui import GUI, Category, Page
# from core.utils.network.network import getHostIP
# from extensions.gui.src.lib.objects.python.table import TextColumn, NumberColumn, SliderColumn, \
#     ButtonColumn, Table
#
#
# def main():
#     host = getHostIP()
#     app = GUI(id='gui', host=host, run_js=True)
#     # First category
#     category1 = Category(id='widgets',
#                          name='Widgets',
#                          icon='🤖',
#                          )
#
#     app.addCategory(category1)
#
#     # Make the pages
#     page_table = Page(id='table',
#                       name='Table',
#                       )
#
#     category1.addPage(page_table, position=1)
#
#     table = Table(widget_id='table_widget1')
#     table.add_column(
#         TextColumn(
#             id='col1',
#             title='Text'
#         )
#     )
#
#     table.add_column(
#         NumberColumn(
#             id='col2',
#             title='Number',
#             increment=0.01,
#         )
#     )
#
#     table.add_column(
#         SliderColumn(
#             id='col3',
#             title='Slider',
#             min_value=0,
#             max_value=100,
#             increment=1,
#         )
#     )
#
#     table.add_column(
#         ButtonColumn(id='col4',
#                      title='Button',
#                      width=0.2)
#     )
#
#     for i in range(2):
#         row1 = table.make_row(col1=f'Row {i+1}', col2=12.345, col3=50, col4='Button')
#
#     page_table.addWidget(table, width=30, height=10)
#
#     app.start()
#
#     # ==================================================================================================================
#     i = 4
#     while True:
#
#         row = table.make_row(col1=f'Row {i+1}', col2=12.345, col3=50, col4='Button')
#         i += 1
#         time.sleep(1)
#         table.delete_row(row)
#         time.sleep(1)
#
#
# if __name__ == '__main__':
#     main()


import time
import random

from extensions.gui.src.gui import GUI, Category, Page
from core.utils.network.network import getHostIP
from extensions.gui.src.lib.objects.python.table import (
    Table,
    TableGroup,
    TextColumn,
    TextInputColumn,
    NumberColumn,
    SliderColumn,
    CheckboxColumn,
    IndicatorColumn,
    SelectColumn,
    MultiSelectColumn,
    ButtonColumn,
)


def rgba(r, g, b, a=1.0):
    return [float(r), float(g), float(b), float(a)]


def main():
    host = getHostIP()
    app = GUI(id="gui", host=host, run_js=True)

    # Category / page
    category = Category(id="widgets", name="Widgets", icon="🤖")
    app.addCategory(category)

    page = Page(id="table_demo", name="Table (Groups + Highlight + Colors)")
    category.addPage(page, position=1)

    # ------------------------------------------------------------------------------------------------------------------
    # Table + columns
    table = Table(widget_id="table_widget_groups_demo")

    table.add_column(TextColumn(id="name", title="Name", width=0.35, font_align="left"))
    table.add_column(TextInputColumn(id="note", title="Note (input)", width=0.30, font_align="left"))
    table.add_column(NumberColumn(id="score", title="Score", increment=0.01, width=0.12, align="right"))
    table.add_column(SliderColumn(id="progress", title="Progress", min_value=0, max_value=100, increment=1, width=0.16))
    table.add_column(CheckboxColumn(id="ok", title="OK?", width=0.07))
    table.add_column(IndicatorColumn(id="status", title="Status", width=0.08))
    table.add_column(SelectColumn(
        id="prio",
        title="Priority",
        width=0.12,
        options={"low": "Low", "med": "Medium", "high": "High"},
    ))
    table.add_column(MultiSelectColumn(
        id="tags",
        title="Tags",
        width=0.22,
        options={"a": "Tag A", "b": "Tag B", "c": "Tag C", "x": "Extra"},
    ))
    table.add_column(ButtonColumn(id="action", title="Action", width=0.12))

    # ------------------------------------------------------------------------------------------------------------------
    # Groups showcasing:
    # - title row spanning all columns
    # - group outline color
    # - collapsible groups (double click title row in UI)
    group_a = TableGroup(
        id="grp_alpha",
        title="Alpha Group (collapsible, blue outline) — double click to toggle",
        title_color="white",
        collapsible=True,
        group_color=rgba(0.2, 0.55, 1.0, 0.95),
    )
    group_b = TableGroup(
        id="grp_beta",
        title="Beta Group (green outline)",
        title_color="white",
        collapsible=False,
        group_color=rgba(0.2, 1.0, 0.45, 0.9),
    )
    group_c = TableGroup(
        id="grp_attention",
        title="Attention (red outline, has row highlights + row background colors)",
        title_color=rgba(1, 0.9, 0.9, 1),
        collapsible=True,
        group_color=rgba(1.0, 0.25, 0.25, 0.95),
    )

    # Attach groups to table:
    # (Your Table model stores items; we add groups there so the payload includes them.)
    table.items[group_a.id] = group_a
    table.items[group_b.id] = group_b
    table.items[group_c.id] = group_c

    # Make sure groups know their table (since we inserted them directly)
    group_a._table = table
    group_b._table = table
    group_c._table = table

    # ------------------------------------------------------------------------------------------------------------------
    # Populate groups with rows using group.make_row (recommended)

    # Alpha: normal rows
    group_a.make_row(
        name="Alice",
        note="editable note",
        score=12.345,
        progress=30,
        ok=True,
        status=[rgba(0.1, 0.9, 0.2, 0.9), "G"],
        prio="med",
        tags=["a", "c"],
        action="Ping",
    )
    group_a.make_row(
        name="Bob",
        note="try typing + Enter",
        score=7.891,
        progress=70,
        ok=False,
        status=[rgba(1.0, 0.75, 0.1, 0.9), "W"],
        prio="low",
        tags=["b"],
        action="Ping",
    )
    group_a.make_row(
        name="Charlie",
        note="multi-select works",
        score=99.001,
        progress=95,
        ok=True,
        status=[rgba(0.2, 0.7, 1.0, 0.9), "I"],
        prio="high",
        tags=["a", "b", "x"],
        action="Ping",
    )

    # Beta: demonstrate row_background_color applied to ALL cells in that row
    group_b.make_row(
        name="Dora (row_background_color)",
        note="entire row tinted",
        score=42.42,
        progress=10,
        ok=True,
        status=[rgba(0.9, 0.9, 0.9, 0.85), "•"],
        prio="med",
        tags=["c"],
        action="Run",
        row_background_color=rgba(0.2, 0.2, 0.2, 0.55),
    )
    group_b.make_row(
        name="Evan",
        note="normal row",
        score=3.14,
        progress=50,
        ok=False,
        status=[rgba(0.9, 0.4, 0.2, 0.9), "!"],
        prio="low",
        tags=[],
        action="Run",
    )

    # Attention: demonstrate highlight outline + background color
    group_c.make_row(
        name="Needs Review (highlight=True)",
        note="row is outlined",
        score=0.01,
        progress=5,
        ok=False,
        status=[rgba(1.0, 0.2, 0.2, 0.95), "!"],
        prio="high",
        tags=["x"],
        action="Fix",
        highlight=True,  # row outline (frontend draws it)
    )
    group_c.make_row(
        name="Critical (highlight + background)",
        note="outline + tinted bg",
        score=-12.34,
        progress=15,
        ok=False,
        status=[rgba(1.0, 0.15, 0.15, 0.95), "!!"],
        prio="high",
        tags=["a", "x"],
        action="Fix",
        highlight=True,
        row_background_color=rgba(0.35, 0.0, 0.0, 0.45),
    )

    # Ungrouped rows (no title row, no group outline)
    table.make_row(
        name="Ungrouped Row 1",
        note="still supports highlight",
        score=1.23,
        progress=60,
        ok=True,
        status=[rgba(0.3, 1.0, 0.6, 0.9), "✓"],
        prio="low",
        tags=["b"],
        action="Do",
        highlight=True,
    )
    table.make_row(
        name="Ungrouped Row 2 (bg)",
        note="row background applies",
        score=9.99,
        progress=80,
        ok=True,
        status=[rgba(0.7, 0.7, 1.0, 0.9), "i"],
        prio="med",
        tags=["a", "c"],
        action="Do",
        row_background_color=rgba(0.1, 0.15, 0.25, 0.55),
    )

    page.addWidget(table, width=40, height=12)
    app.start()

    # ------------------------------------------------------------------------------------------------------------------
    # Live updates: periodically add/remove rows, flip highlight/background, update a couple of cells
    counter = 0
    dynamic_rows = []

    while True:
        counter += 1

        # Add a new row into Alpha every few seconds (alternating styles)
        if counter % 3 == 1:
            r = group_a.make_row(
                name=f"Dynamic #{counter}",
                note="I appear/disappear",
                score=random.uniform(-5, 105),
                progress=random.randint(0, 100),
                ok=(counter % 2 == 0),
                status=[rgba(0.2, 0.55, 1.0, 0.9), "D"],
                prio=random.choice(["low", "med", "high"]),
                tags=random.sample(["a", "b", "c", "x"], k=random.randint(0, 3)),
                action="Ping",
                highlight=(counter % 2 == 0),
                row_background_color=(rgba(0.1, 0.25, 0.45, 0.35) if counter % 4 == 0 else None),
            )
            dynamic_rows.append(r)

        # Update some values in-place (shows cell updates)
        # pick first row in Alpha if it exists
        try:
            alpha_first = next(iter(group_a.rows.values()))
            alpha_first["score"] = float(alpha_first["score"].value) + random.uniform(-0.5, 0.5)
            alpha_first["progress"] = random.randint(0, 100)
            alpha_first["status"] = [rgba(0.2, 0.7, 1.0, 0.9), "U"]
        except Exception:
            pass

        # Remove the oldest dynamic row sometimes
        if len(dynamic_rows) > 3:
            old = dynamic_rows.pop(0)
            old.delete()

        time.sleep(1)


if __name__ == "__main__":
    main()