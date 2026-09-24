"""Bounded CSV implementation used only by the documentation exercise."""
import csv
import io

def export_saved_searches(records):
    if not records:
        return None
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["name", "query"])
    writer.writerows((record["name"], record["query"]) for record in records)
    return output.getvalue()
