import os
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "sample.md"

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

BASE_URL = os.getenv("CONFLUENCE_WIKI_URL")
EMAIL = os.getenv("CONFLUENCE_USER_EMAIL")
TOKEN = os.getenv("CONFLUENCE_ACCESS_TOKEN")
SPACES = os.getenv("CONFLUENCE_SPACES", "SPACE1,SPACE2")
SAMPLE_PAGE_ID = os.getenv("CONFLUENCE_SAMPLE_PAGE_ID", "123456789")

def call_confluence(path, params=None):
    response = requests.get(
        f"{BASE_URL}{path}",
        params=params,
        auth=(EMAIL, TOKEN),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def find_one_page():
    cql = f"type=page AND space in ({SPACES})"

    data = call_confluence(
        "/rest/api/content/search",
        params={
            "cql": cql,
            "limit": 1,
        },
    )

    results = data.get("results", [])

    if not results:
        raise RuntimeError("조회된 Confluence 페이지가 없습니다.")

    return results[0]


def fetch_page_detail(page_id):
    return call_confluence(
        f"/rest/api/content/{page_id}",
        params={
            "expand": "body.storage,space,version",
        },
    )


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def main():
    page_detail = fetch_page_detail(SAMPLE_PAGE_ID)

    title = page_detail["title"]
    page_id = page_detail["id"]
    space_key = page_detail["space"]["key"]
    version = page_detail["version"]["number"]
    page_url = f'{BASE_URL}{page_detail["_links"]["webui"]}'

    html = page_detail["body"]["storage"]["value"]
    text = html_to_text(html)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_PATH.write_text(
        f"# {title}\n\n"
        f"- source: {page_url}\n"
        f"- space: {space_key}\n"
        f"- page_id: {page_id}\n"
        f"- version: {version}\n\n"
        f"---\n\n"
        f"{text}\n",
        encoding="utf-8",
    )

    print(f"저장 완료: {OUTPUT_PATH}")
    print(f"제목: {title}")
    print(f"스페이스: {space_key}")
    print(f"URL: {page_url}")


if __name__ == "__main__":
    main()
