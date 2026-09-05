"""
Z.A.I.N.E Phase 6 — Autonomous Web Browser Agent ("Cyber Hands")
Empowers Zaine with deep web browsing, semantic page extraction,
multi-page search research, and direct file downloading into workspace.
100% local, zero-cost, privacy-first.
"""

import re
import urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def browse_web(url: str, selector: str = "", extract_links: bool = False, max_chars: int = 3500) -> str:
    """
    Fetches and reads the contents of any public webpage, stripping ads, navigation, and boilerplate.
    Optional CSS selector can target specific page elements (e.g. 'article', 'main', '#content').
    """
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
        if resp.status_code >= 400:
            return f"Error: Received HTTP {resp.status_code} while trying to read '{url}'."

        soup = BeautifulSoup(resp.text, "html.parser")

        # Strip scripts, styles, noscripts, iframes
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav", "aside"]):
            tag.decompose()

        if selector.strip():
            target_elem = soup.select_one(selector.strip())
            if target_elem:
                text_content = target_elem.get_text(separator="\n", strip=True)
            else:
                text_content = f"Note: Selector '{selector}' not found. Reading general page body:\n\n"
                text_content += soup.get_text(separator="\n", strip=True)
        else:
            # Look for standard article/content wrappers first
            main_block = soup.find(["article", "main"]) or soup.find("div", {"id": re.compile(r"content|article|main", re.I)})
            if main_block:
                text_content = main_block.get_text(separator="\n", strip=True)
            else:
                text_content = soup.get_text(separator="\n", strip=True)

        # Clean multiple blank lines
        clean_text = re.sub(r"\n\s*\n+", "\n\n", text_content).strip()

        result_parts = [f"--- Content from {url} ---"]
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        if title:
            result_parts.append(f"Title: {title}\n")

        if len(clean_text) > max_chars:
            result_parts.append(clean_text[:max_chars] + f"\n\n[Content truncated. Showing first {max_chars} of {len(clean_text)} characters.]")
        else:
            result_parts.append(clean_text)

        if extract_links:
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if text and href and not href.startswith("#") and not href.startswith("javascript:"):
                    abs_href = urllib.parse.urljoin(url, href)
                    links.append(f"- [{text}]({abs_href})")
            if links:
                result_parts.append("\nKey Links Found:\n" + "\n".join(links[:15]))

        return "\n".join(result_parts)

    except requests.exceptions.Timeout:
        return f"Error: Request timed out while browsing '{url}' (15s limit)."
    except Exception as e:
        return f"Error browsing '{url}': {e}"


def search_and_extract(query: str, max_pages: int = 2) -> str:
    """
    Searches DuckDuckGo and directly visits the top result pages to extract detailed real-world content.
    Provides deep multi-source research rather than just short search snippet blurbs.
    """
    query = query.strip()
    if not query:
        return "Error: Search query cannot be empty."

    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        resp = requests.post(search_url, data={"q": query}, headers=DEFAULT_HEADERS, timeout=12)
        if resp.status_code != 200:
            return f"Search engine returned HTTP {resp.status_code}. Using fallback web search."

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for a in soup.find_all("a", class_="result__url", href=True):
            href = a["href"]
            # DuckDuckGo redirects through /l/?uddg=
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                actual_url = urllib.parse.unquote(match.group(1))
                if not any(block in actual_url for block in ("youtube.com", "facebook.com", "twitter.com", "instagram.com")):
                    results.append(actual_url)

        if not results:
            # Fallback to result__snippet
            snippets = [s.get_text(strip=True) for s in soup.find_all("a", class_="result__snippet")[:3]]
            return "Search Summary:\n" + "\n".join(f"- {s}" for s in snippets) if snippets else "No search results found."

        deep_results = [f"=== Deep Web Research for '{query}' ===\n"]
        for idx, page_url in enumerate(results[:max_pages], start=1):
            deep_results.append(f"\n[Source {idx}]: {page_url}")
            content = browse_web(page_url, max_chars=1200)
            deep_results.append(content)

        return "\n".join(deep_results)

    except Exception as e:
        return f"Error conducting deep web research: {e}"


def download_web_file(url: str, save_as: str = "") -> str:
    """
    Downloads any external web asset (dataset, CSV, JSON, code, image) directly into the workspace sandbox.
    """
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        filename = save_as.strip()
        if not filename:
            parsed = urllib.parse.urlparse(url)
            filename = Path(parsed.path).name or "downloaded_file"

        # Sanitize filename
        filename = re.sub(r'[\\/*?:"<>|]', "", filename)
        target_path = WORKSPACE_DIR / filename

        resp = requests.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=20)
        if resp.status_code >= 400:
            return f"Error: HTTP {resp.status_code} while downloading '{url}'."

        size_bytes = 0
        max_bytes = 50 * 1024 * 1024  # 50 MB safety guard
        with open(target_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        target_path.unlink(missing_ok=True)
                        return "Error: Download exceeded maximum safety limit (50 MB)."

        return f"Successfully downloaded '{filename}' ({size_bytes} bytes) into workspace."

    except Exception as e:
        return f"Error downloading file from '{url}': {e}"


if __name__ == "__main__":
    print("Testing browse_web on python.org...")
    out = browse_web("https://www.python.org", max_chars=300)
    print(out[:400])
