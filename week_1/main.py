import sys
from pathlib import Path

from src.ingestor import ingest_all_mhtml
from src.loader import load_all_jsons
from src.processor import process_all_html
from src.profiler import run_data_profile


SOURCE_DIR = Path("data/0_source")
BRONZE_DIR = Path("data/1_bronze")
SILVER_DIR = Path("data/2_silver")
GOLD_DIR = Path("data/3_gold")
DB_PATH = GOLD_DIR / "jobs.db"


def run_bronze() -> None:
    print("🥉 Bronze...")
    ingest_all_mhtml(SOURCE_DIR, BRONZE_DIR)


def run_silver() -> None:
    print("🥈 Silver...")
    process_all_html(BRONZE_DIR, SILVER_DIR)


def run_gold() -> None:
    print("🏆 Gold...")
    load_all_jsons(SILVER_DIR, GOLD_DIR)


def run_profile() -> None:
    print("🔍 Profile...")
    run_data_profile(DB_PATH)


def run_all() -> None:
    run_bronze()
    print()

    run_silver()
    print()

    run_gold()
    print()

    run_profile()


def show_usage() -> None:
    print("Usage: python main.py [ingest|process|load|profile|all]")


def main() -> None:
    if len(sys.argv) < 2:
        show_usage()
        return

    command = sys.argv[1].lower()

    if command == "ingest":
        run_bronze()
    elif command == "process":
        run_silver()
    elif command == "load":
        run_gold()
    elif command == "profile":
        run_profile()
    elif command == "all":
        run_all()
    else:
        print(f"Unknown command: {command}")
        show_usage()


if __name__ == "__main__":
    main()