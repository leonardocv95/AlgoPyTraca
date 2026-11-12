
import csv
from pathlib import Path

def export_to_csv(
    data,
    filename="trading_results.csv",
    columns=None
):

    if not data:
        print("No data to export.")
        return

    # Automatically detect columns if none are specified
    if columns is None:
        columns = list(dict.fromkeys(
            key
            for item in data
            for key in item.keys()
        ))

    file_path = Path(filename)

    # Create CSV file
    with file_path.open("w", newline="", encoding="utf-8-sig") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(data)

    print(f"Export completed successfully!")
    print(f"File: {file_path.resolve()}")
    print(f"Records exported: {len(data)}")
    print(f"Columns exported: {len(columns)}")
