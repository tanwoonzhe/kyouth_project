from email import policy
from email.parser import BytesParser
from pathlib import Path
from quopri import decodestring


def extract_html_from_mhtml(file_path: Path) -> str | None:
    with file_path.open("rb") as file:
        message = BytesParser(policy=policy.default).parse(file)

    for part in message.walk():
        content_type = part.get_content_type()

        if content_type != "text/html":
            continue

        payload = part.get_payload(decode=True)

        if payload is None:
            raw_payload = part.get_payload()

            if isinstance(raw_payload, str):
                return decodestring(raw_payload.encode()).decode(
                    "utf-8",
                    errors="ignore",
                )

            return None

        return payload.decode("utf-8", errors="ignore")

    return None


def ingest_all_mhtml(input_dir: Path, output_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    mhtml_files = sorted(input_dir.glob("*.mhtml"))

    total = len(mhtml_files)
    extracted = 0
    failed = 0

    if total == 0:
        print("⚠️ No MHTML files found.")
        print("📊 Bronze Summary:")
        print("Total: 0 | Extracted: 0 | Failed: 0")
        return

    for file_path in mhtml_files:
        html_content = extract_html_from_mhtml(file_path)

        if not html_content:
            failed += 1
            print(f"⚠️ No HTML content found in: {file_path.name}")
            continue

        output_file = output_dir / f"{file_path.stem}.html"
        output_file.write_text(html_content, encoding="utf-8")

        extracted += 1
        print(f"✅ Extracted: {output_file.name}")

    print("\n📊 Bronze Summary:")
    print(f"Total: {total} | Extracted: {extracted} | Failed: {failed}")