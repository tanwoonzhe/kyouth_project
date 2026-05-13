import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from pydantic import BaseModel, ValidationError


class JobListing(BaseModel):
    source_id: str
    job_title: str
    company: str
    description: str


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    return " ".join(text.split())


def extract_source_id(soup: BeautifulSoup) -> str | None:
    meta_url = soup.find("meta", property="og:url")

    if not meta_url:
        return None

    content = meta_url.get("content", "").rstrip("/")

    if not content:
        return None

    last_segment = content.split("/")[-1]

    return last_segment if last_segment.isdigit() else None


def extract_job_title(soup: BeautifulSoup) -> str | None:
    title_tag = soup.find(attrs={"data-automation": "job-detail-title"})

    if not title_tag:
        return None

    title = clean_text(title_tag.get_text(separator=" ", strip=True))

    return title or None


def extract_company(soup: BeautifulSoup) -> str | None:
    company_tag = soup.find(attrs={"data-automation": "advertiser-name"})

    if not company_tag:
        return None

    company = clean_text(company_tag.get_text(separator=" ", strip=True))

    return company or None


def extract_description(soup: BeautifulSoup) -> str | None:
    job_ad_details = soup.find(attrs={"data-automation": "jobAdDetails"})

    if not job_ad_details:
        return None

    description = clean_text(job_ad_details.get_text(separator=" ", strip=True))

    return description or None


def process_single_html(file_path: Path) -> JobListing | None:
    html = file_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    source_id = extract_source_id(soup)
    job_title = extract_job_title(soup)
    company = extract_company(soup)
    description = extract_description(soup)

    if not source_id:
        print(f"⚠️ Missing source_id in: {file_path.name}")
        return None

    if not job_title:
        print(f"⚠️ Missing job_title in: {file_path.name}")
        return None

    if not company:
        print(f"⚠️ Missing company in: {file_path.name}")
        return None

    if not description:
        print(f"⚠️ Missing description in: {file_path.name}")
        return None

    try:
        return JobListing(
            source_id=source_id,
            job_title=job_title,
            company=company,
            description=description,
        )
    except ValidationError as error:
        print(f"⚠️ Validation failed in: {file_path.name}")
        print(error)
        return None


def process_all_html(input_dir: Path, output_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stale_file in output_dir.glob("*.json"):
        stale_file.unlink()

    html_files = sorted(input_dir.glob("*.html"))

    total = len(html_files)
    processed = 0
    skipped = 0

    if total == 0:
        print("⚠️ No HTML files found.")
        print("📊 Silver Summary:")
        print("Total: 0 | Processed: 0 | Skipped: 0")
        return

    for file_path in html_files:
        job_listing = process_single_html(file_path)

        if job_listing is None:
            skipped += 1
            continue

        output_file = output_dir / f"{file_path.stem}.json"

        output_file.write_text(
            json.dumps(
                job_listing.model_dump(),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        processed += 1
        print(f"✅ Processed: {output_file.name}")

    print("\n📊 Silver Summary:")
    print(f"Total: {total} | Processed: {processed} | Skipped: {skipped}")