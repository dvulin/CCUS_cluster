import sys

sys.stdout.reconfigure(encoding="utf-8")

from ccus_core.io.excel_import import _XlsxReader

reader = _XlsxReader("docs/examples/CCS TABLICE 2015-2022 example.xlsx")
rows = reader.sheet("storage")
print("storage rows:", len(rows))
for number in sorted(rows):
    cells = {chr(ord("A") + i): v for i, v in enumerate(rows[number])}
    values = {k: v for k, v in cells.items() if v not in (None, "")}
    if values.get("B") or values.get("C"):
        print(number, values)