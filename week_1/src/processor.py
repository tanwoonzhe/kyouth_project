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


def get_main_soup(soup: BeautifulSoup) -> BeautifulSoup:
    main = soup.find(attrs={"data-automation": "jobDetailsPage"})
    return main if main else soup


def get_visible_lines(soup: BeautifulSoup) -> list[str]:
    main_soup = get_main_soup(soup)
    working_soup = BeautifulSoup(str(main_soup), "html.parser")

    for tag in working_soup(["script", "style", "svg", "noscript"]):
        tag.decompose()

    raw_lines = working_soup.get_text("\n").splitlines()
    lines = []

    for line in raw_lines:
        cleaned = clean_text(line)

        if not cleaned:
            continue

        if lines and lines[-1] == cleaned:
            continue

        lines.append(cleaned)

    return lines


def extract_source_id(soup: BeautifulSoup, file_path: Path) -> str | None:
    og_url = soup.find("meta", property="og:url")

    if og_url:
        content = og_url.get("content", "")
        match = re.search(r"/job/(\d+)", content)

        if match:
            return match.group(1)

    for tag in soup.find_all(["a", "link"], href=True):
        href = tag.get("href", "")
        match = re.search(r"/job/(\d+)", href)

        if match:
            return match.group(1)

    match = re.search(r"(\d{6,})", file_path.stem)

    if match:
        return match.group(1)

    return None


def extract_job_title(soup: BeautifulSoup) -> str | None:
    title_tag = soup.find(attrs={"data-automation": "job-detail-title"})

    if title_tag:
        job_title = clean_text(title_tag.get_text(" "))

        if job_title:
            return job_title

    meta_title = soup.find("meta", property="og:title")

    if meta_title:
        job_title = clean_text(meta_title.get("content", ""))
        job_title = re.sub(r"\s+Job in\s+.*$", "", job_title)
        job_title = re.sub(r"\s+-\s+Jobstreet\s*$", "", job_title)

        if job_title:
            return job_title

    if soup.title:
        job_title = clean_text(soup.title.get_text(" "))
        job_title = re.sub(r"\s+Job in\s+.*$", "", job_title)
        job_title = re.sub(r"\s+-\s+Jobstreet\s*$", "", job_title)

        if job_title:
            return job_title

    return None


def extract_company(soup: BeautifulSoup, job_title: str | None) -> str | None:
    company_tag = soup.find(attrs={"data-automation": "advertiser-name"})

    if company_tag:
        company = clean_text(company_tag.get_text(" "))

        if company:
            return company

    for tag in soup.find_all(attrs={"aria-label": True}):
        aria_label = clean_text(tag.get("aria-label", ""))

        if not aria_label.startswith(("Apply for", "Save")):
            continue

        match = re.search(r"\bat\s+(.+)$", aria_label)

        if match:
            company = clean_text(match.group(1))

            if company:
                return company

    if job_title:
        lines = get_visible_lines(soup)

        for index, line in enumerate(lines[:-1]):
            if line.lower() == job_title.lower():
                candidate = lines[index + 1]

                if candidate not in {"Quick apply", "Save", "View all jobs"}:
                    return candidate

    return None


def extract_meta_description(soup: BeautifulSoup) -> str | None:
    meta_description = soup.find("meta", attrs={"name": "description"})

    if not meta_description:
        meta_description = soup.find("meta", property="og:description")

    if meta_description:
        description = clean_text(meta_description.get("content", ""))

        if description:
            return description

    return None


def is_rating_or_review(line: str) -> bool:
    if re.fullmatch(r"\d+(\.\d+)?", line):
        return True

    if re.fullmatch(r"\d+\s+reviews?", line, re.IGNORECASE):
        return True

    if line == "·":
        return True

    return False


def extract_overview_lines(
    lines: list[str],
    job_title: str,
    company: str,
) -> list[str]:
    title_positions = [
        index for index, line in enumerate(lines) if line.lower() == job_title.lower()
    ]

    if not title_positions:
        return []

    positions_with_company = [
        index
        for index in title_positions
        if index + 1 < len(lines) and lines[index + 1].lower() == company.lower()
    ]

    if positions_with_company:
        start_index = positions_with_company[-1] + 2
    else:
        start_index = title_positions[0] + 1

    stop_headings = {
        "JOB SUMMARY",
        "JOB DESCRIPTION",
        "ABOUT US",
        "ABOUT THE ROLE",
        "RESPONSIBILITIES",
        "RESPONSIBLITIES:-",
        "KEY RESPONSIBILITIES",
        "REQUIREMENTS",
        "REQUIREMENT",
        "WHAT YOU WILL DO",
        "QUALIFICATIONS",
    }

    skip_lines = {
        job_title,
        company,
        "View all jobs",
        "Quick apply",
        "Save",
    }

    overview = []

    for line in lines[start_index:]:
        if line.upper() in stop_headings:
            break

        if line in skip_lines:
            continue

        if is_rating_or_review(line):
            continue

        overview.append(line)

    return overview[:8]


def extract_description_body(lines: list[str]) -> str | None:
    heading_candidates = {
        "JOB SUMMARY",
        "JOB DESCRIPTION",
        "ABOUT US",
        "ABOUT THE ROLE",
        "RESPONSIBILITIES",
        "RESPONSIBLITIES:-",
        "KEY RESPONSIBILITIES",
        "WHAT YOU WILL DO",
    }

    stop_candidates = {
        "Unlock job insights",
        "Hirer responsiveness",
        "Salary match",
        "Number of applicants",
        "Employer questions",
        "Report this job advert",
        "Be careful",
        "Explore similar jobs",
        "Job seekers",
    }

    start_index = None

    for index, line in enumerate(lines):
        if line.upper() in heading_candidates:
            start_index = index
            break

    if start_index is None:
        return None

    body_lines = []

    for line in lines[start_index:]:
        if line in stop_candidates:
            break

        if line in {"Quick apply", "Save", "View all jobs"}:
            continue

        body_lines.append(line)

    description = "\n".join(body_lines).strip()

    if description:
        return description

    return None


def build_description(
    soup: BeautifulSoup,
    job_title: str,
    company: str,
) -> str | None:
    lines = get_visible_lines(soup)

    overview_lines = extract_overview_lines(lines, job_title, company)
    description_body = extract_description_body(lines)
    meta_description = extract_meta_description(soup)

    parts = []

    if overview_lines:
        overview_text = "Job Overview:\n" + "\n".join(overview_lines)
        parts.append(overview_text)

    if description_body:
        parts.append(description_body)
    elif meta_description:
        parts.append(meta_description)

    description = "\n\n".join(parts).strip()

    if description:
        return description

    return None


def process_single_html(file_path: Path) -> JobListing | None:
    html = file_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    source_id = extract_source_id(soup, file_path)
    job_title = extract_job_title(soup)
    company = extract_company(soup, job_title)
    description = None

    if job_title and company:
        description = build_description(soup, job_title, company)

    if not description:
        description = extract_meta_description(soup)

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