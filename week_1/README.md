# Week 1: Data Component

## Project Description

This project builds a ETL (Extract, Transform, Load) pipeline for job listing data. It extracts raw `.mhtml` files, converts them into `.html`, processes the HTML into structured `.json`, loads the cleaned data into a SQLite database, and runs a data quality report.

Final output:

```text
data/3_gold/jobs.db
```

Database table:

```text
jobs(source_id, job_title, company, description, tech_stack)
```

---

## Project Structure

```text
week_1/
├── data/
│   ├── 0_source/
│   ├── 1_bronze/
│   ├── 2_silver/
│   └── 3_gold/
├── src/
│   ├── ingestor.py
│   ├── processor.py
│   ├── loader.py
│   └── profiler.py
├── main.py
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
└── README.md
```

---

## Setup Instructions

Install Python 3.14:

```bash
uv python install 3.14
```

Install dependencies:

```bash
uv sync
```

If dependencies are missing, run:

```bash
uv add beautifulsoup4 pydantic ruff
```

Place the provided `.mhtml` files inside:

```text
data/0_source/
```

---

## Usage

Run all commands from the `week_1` folder.

### Module 1: Extractor / Bronze Layer

Extract `.mhtml` files into `.html` files.

```bash
uv run python main.py ingest
```

Input:

```text
data/0_source/*.mhtml
```

Output:

```text
data/1_bronze/*.html
```

Expected summary:

```text
Total: 100 | Extracted: 100 | Failed: 0
```

---

### Module 2: Treatment Plant / Silver Layer

Process `.html` files into structured `.json` files.

```bash
uv run python main.py process
```

Input:

```text
data/1_bronze/*.html
```

Output:

```text
data/2_silver/*.json
```

Expected summary:

```text
Total: 100 | Processed: 84 | Skipped: 16
```

---

### Module 3: Blueprint & The Vault / Gold Layer

Load `.json` files into SQLite.

```bash
uv run python main.py load
```

Input:

```text
data/2_silver/*.json
```

Output:

```text
data/3_gold/jobs.db
```

Expected summary for the first run:

```text
Total: 84 | Inserted: 84 | Skipped: 0 | Failed: 0
```

If the command is run again, duplicate records will be skipped because `source_id` is the primary key.

---

### Module 4: QA Inspector & Orchestrator

Run the data quality report.

```bash
uv run python main.py profile
```

Expected output format:

```text
--- 🔍 DATA QUALITY REPORT ---
📊 Total Records: 84
❓ Missing Values -> job_title: 0, company: 0, description: 0
📏 Avg Description Length: <number> chars
⚠️ Shortest Description: <number> chars
   ↳ source_id: <SOURCE_ID> | job_title: <JOB_TITLE>
📌 Longest Description: <number> chars
   ↳ source_id: <SOURCE_ID> | job_title: <JOB_TITLE>


Run the full pipeline:

```bash
uv run python main.py all
```

Full sequence:

```text
ingest -> process -> load -> profile
```

---

## Command Summary

| Command | Purpose |
|---|---|
| `uv run python main.py ingest` | Extract `.mhtml` into `.html` |
| `uv run python main.py process` | Process `.html` into `.json` |
| `uv run python main.py load` | Load `.json` into SQLite |
| `uv run python main.py profile` | Run data quality checks |
| `uv run python main.py all` | Run the full pipeline |

---

## Technical Reflections

### Module 1: The Extractor (Medallion & Lakehouses)

Why is it useful to keep the original raw HTML files instead of directly inserting processed data into the database? What problems become easier to debug or recover from?

- **Answer**: Because we still need the raw data like `.mhtml` files, it can act like a backup of our data. If we want to redo the process, get new information from the raw data, or validate the processed data by ourselves, we can always refer back to the original files.

### Module 2: Treatment Plant (ETL vs ELT & Scale)

Why do cloud systems prefer loading raw data first before cleaning it (ELT)? What problems happen when processing files sequentially, and how does distributed processing help?

- **Answer**: Because cloud systems can store the raw data first and transform it later using powerful cloud computing resources. If the cleaning rules change or if an error is found in the transformation logic, they can still work with the raw data again. Processing files sequentially is too slow because each file has to be processed one by one. Distributed processing can separate the tasks to different computers and also provide better fault tolerance.

### Module 3: Blueprint & The Vault (Storage & Contracts)

What should happen if an important field like `job_title` disappears? Why fail early instead of silently inserting nulls into the database? How does `INSERT OR IGNORE` help prevent duplicate records?

- **Answer**: If an important field like `job_title` disappears, the system should stop and show an error instead of silently inserting null into the database. This is because the data may look successful, but actually the quality is already wrong. Failing early helps us find problems earlier before they affect dashboards, analytics, or other systems later. `INSERT OR IGNORE` helps prevent duplicate records because if the same record already exists, it will ignore it instead of inserting it again.

### Module 4: QA Inspector & Orchestrator (Orchestration & DAGs)

What happens if `process.py` crashes halfway? How are automated orchestration tools more reliable than manual retries with Python scripts?

- **Answer**: If `process.py` crashes halfway, some files may already be processed while some are not. This can make the pipeline incomplete and confusing when we want to rerun it manually. Automated orchestration tools are more reliable because they can track which task failed, retry the failed task, and make sure the next step only runs after the previous step is completed.