import sqlite3
from pathlib import Path


def run_data_profile(db_path: Path) -> None:
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'jobs'
            """
        )

        table_exists = cursor.fetchone()

        if not table_exists:
            print("❌ jobs table not found.")
            return

        total_records = get_total_records(cursor)
        missing_values = get_missing_values(cursor)
        avg_description_length = get_average_description_length(cursor)
        shortest_description = get_shortest_description(cursor)
        longest_description = get_longest_description(cursor)

        print("\n--- 🔍 DATA QUALITY REPORT ---")
        print(f"📊 Total Records: {total_records}")
        print(
            "❓ Missing Values -> "
            f"job_title: {missing_values['job_title']}, "
            f"company: {missing_values['company']}, "
            f"description: {missing_values['description']}"
        )
        print(f"📏 Avg Description Length: {avg_description_length} chars")

        if shortest_description:
            print(
                "⚠️ Shortest Description: "
                f"{shortest_description['description_length']} chars"
            )
            print(
                f"   ↳ source_id: {shortest_description['source_id']} | "
                f"job_title: {shortest_description['job_title']}"
            )

        if longest_description:
            print(
                "📌 Longest Description: "
                f"{longest_description['description_length']} chars"
            )
            print(
                f"   ↳ source_id: {longest_description['source_id']} | "
                f"job_title: {longest_description['job_title']}"
            )

    except sqlite3.Error as error:
        print(f"❌ Database error: {error}")

    finally:
        connection.close()


def get_total_records(cursor: sqlite3.Cursor) -> int:
    cursor.execute("SELECT COUNT(*) FROM jobs")
    result = cursor.fetchone()
    return result[0] if result else 0


def get_missing_values(cursor: sqlite3.Cursor) -> dict[str, int]:
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN job_title IS NULL OR TRIM(job_title) = '' THEN 1 ELSE 0 END),
            SUM(CASE WHEN company IS NULL OR TRIM(company) = '' THEN 1 ELSE 0 END),
            SUM(CASE WHEN description IS NULL OR TRIM(description) = '' THEN 1 ELSE 0 END)
        FROM jobs
        """
    )

    result = cursor.fetchone()

    return {
        "job_title": result[0] or 0,
        "company": result[1] or 0,
        "description": result[2] or 0,
    }


def get_average_description_length(cursor: sqlite3.Cursor) -> int:
    cursor.execute(
        """
        SELECT AVG(LENGTH(description))
        FROM jobs
        WHERE description IS NOT NULL AND TRIM(description) != ''
        """
    )

    result = cursor.fetchone()

    if not result or result[0] is None:
        return 0

    return round(result[0])


def get_shortest_description(cursor: sqlite3.Cursor) -> dict[str, str | int] | None:
    cursor.execute(
        """
        SELECT
            source_id,
            job_title,
            LENGTH(description) AS description_length
        FROM jobs
        WHERE description IS NOT NULL AND TRIM(description) != ''
        ORDER BY description_length ASC
        LIMIT 1
        """
    )

    result = cursor.fetchone()

    if not result:
        return None

    return {
        "source_id": result[0],
        "job_title": result[1],
        "description_length": result[2],
    }


def get_longest_description(cursor: sqlite3.Cursor) -> dict[str, str | int] | None:
    cursor.execute(
        """
        SELECT
            source_id,
            job_title,
            LENGTH(description) AS description_length
        FROM jobs
        WHERE description IS NOT NULL AND TRIM(description) != ''
        ORDER BY description_length DESC
        LIMIT 1
        """
    )

    result = cursor.fetchone()

    if not result:
        return None

    return {
        "source_id": result[0],
        "job_title": result[1],
        "description_length": result[2],
    }