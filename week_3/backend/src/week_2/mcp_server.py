"""FastMCP server — wraps all SQLite operations for the jobs database.

Both tag_data.py and find_skill_gaps.py import the `mcp` instance here and
connect to it in-process (no subprocess needed). The server can also be
started standalone with `uv run mcp_server.py` for external MCP clients.
"""

import sqlite3

from fastmcp import FastMCP

# Shared FastMCP server instance imported by tag_data.py and find_skill_gaps.py
mcp = FastMCP("jobs-db")


@mcp.tool()
def ensure_tech_stack_column(db_path: str) -> str:
    """Add the tech_stack column to the jobs table if it does not yet exist."""
    conn = sqlite3.connect(db_path)
    try:
        columns = conn.execute("PRAGMA table_info(jobs)").fetchall()
        if "tech_stack" not in [col[1] for col in columns]:
            conn.execute("ALTER TABLE jobs ADD COLUMN tech_stack TEXT")
            conn.commit()
            return "added"
        return "exists"
    finally:
        conn.close()


@mcp.tool()
def get_untagged_jobs(db_path: str) -> list[dict]:
    """
    Return jobs that still need a tech_stack tag.

    Only rows with a non-empty description and no existing tech_stack value
    are returned, so the script can safely be re-run without repeating work.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT source_id, job_title, description
            FROM jobs
            WHERE description IS NOT NULL
              AND TRIM(description) != ''
              AND (tech_stack IS NULL OR TRIM(tech_stack) = '')
            """
        ).fetchall()
        return [
            {"source_id": r[0], "job_title": r[1], "description": r[2]} for r in rows
        ]
    finally:
        conn.close()


@mcp.tool()
def update_tech_stack(db_path: str, source_id: str, skills: str) -> bool:
    """Persist the extracted tech_stack value for a single job row."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE jobs SET tech_stack = ? WHERE source_id = ?",
            (skills, source_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


@mcp.tool()
def get_market_skills(db_path: str) -> list[str]:
    """
    Return all tech_stack strings from successfully tagged jobs.

    Rows that contain API error messages (rate-limit responses stored by
    mistake) are filtered out to avoid polluting the market skill pool.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT tech_stack
            FROM jobs
            WHERE tech_stack IS NOT NULL
              AND TRIM(tech_stack) != ''
              AND tech_stack NOT LIKE '%RESOURCE_EXHAUSTED%'
              AND tech_stack NOT LIKE '%quotaValue%'
              AND tech_stack NOT LIKE '%retryDelay%'
            """
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    # Run as a standalone stdio MCP server (for external MCP clients)
    mcp.run()
