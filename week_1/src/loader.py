import json
import sqlite3
from pathlib import Path


def create_jobs_table(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            source_id TEXT PRIMARY KEY,
            job_title TEXT NOT NULL,
            company TEXT NOT NULL,
            description TEXT NOT NULL,
            tech_stack TEXT
        )
        """
    )

    connection.commit()


def load_single_json(
    connection: sqlite3.Connection,
    json_file: Path,
) -> str:
    with json_file.open("r", encoding="utf-8") as file:
        data = json.load(file)

    source_id = data.get("source_id")
    job_title = data.get("job_title")
    company = data.get("company")
    description = data.get("description")
    tech_stack = data.get("tech_stack", "")

    if not source_id or not job_title or not company or not description:
        return "failed"

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO jobs (
            source_id,
            job_title,
            company,
            description,
            tech_stack
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            source_id,
            job_title,
            company,
            description,
            tech_stack,
        ),
    )

    connection.commit()

    if cursor.rowcount == 0:
        return "skipped"

    return "inserted"


def load_all_jsons(input_dir: Path, output_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "jobs.db"
    json_files = sorted(input_dir.glob("*.json"))

    total = len(json_files)
    inserted = 0
    skipped = 0
    failed = 0

    if total == 0:
        print("⚠️ No JSON files found.")
        print("📊 Gold Summary:")
        print("Total: 0 | Inserted: 0 | Skipped: 0 | Failed: 0")
        return

    connection = sqlite3.connect(db_path)

    try:
        create_jobs_table(connection)

        for json_file in json_files:
            try:
                result = load_single_json(connection, json_file)

                if result == "inserted":
                    inserted += 1
                    print(f"✅ Inserted: {json_file.name}")
                elif result == "skipped":
                    skipped += 1
                    print(f"⚠️ Skipped duplicate: {json_file.name}")
                else:
                    failed += 1
                    print(f"❌ Failed: {json_file.name}")

            except json.JSONDecodeError:
                failed += 1
                print(f"❌ Invalid JSON: {json_file.name}")

            except sqlite3.Error as error:
                failed += 1
                print(f"❌ Database error in {json_file.name}: {error}")

    finally:
        connection.close()

    print("\n📊 Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Skipped: {skipped} | Failed: {failed}")