#!/usr/bin/env python3
"""Build the contribution README and SVG preview with the GitHub GraphQL API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any, Mapping
from unicodedata import category, east_asian_width
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.github.com/graphql"
API_VERSION = "2022-11-28"
DEFAULT_USERNAME = "YangSiJun528"
DEFAULT_TITLE = "Open Source Contributions"
DEFAULT_MIN_STARS = 100
SEARCH_LIMIT = 1_000
GITHUB_START = date(2008, 1, 1)
PLACEHOLDERS = ("{{TITLE}}", "{{CONTRIBUTIONS}}")

DATE_WIDTH = 7
TYPE_WIDTH = 5
STATE_WIDTH = 7
REPOSITORY_WIDTH = 27
TITLE_CLIP_AT = 81
TITLE_MAX_WIDTH = 84
PREVIEW_COUNT = 5
PREVIEW_WIDTH = 960
PREVIEW_TITLE_WIDTH = 68
NBSP = "\N{NO-BREAK SPACE}"
ZWJ = "\N{ZERO WIDTH JOINER}"
VS16 = "\N{VARIATION SELECTOR-16}"
KEYCAP = "\N{COMBINING ENCLOSING KEYCAP}"


SEARCH_QUERY = """
query Contributions($query: String!, $cursor: String) {
  search(query: $query, type: ISSUE, first: 100, after: $cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      __typename
      ... on Issue {
        number title url state createdAt
        author { login }
        repository { nameWithOwner stargazerCount }
        lastClose: timelineItems(itemTypes: [CLOSED_EVENT], last: 1) {
          nodes { ... on ClosedEvent { actor { login } } }
        }
      }
      ... on PullRequest {
        number title url state createdAt mergedAt
        author { login }
        repository { nameWithOwner stargazerCount }
        lastClose: timelineItems(itemTypes: [CLOSED_EVENT], last: 1) {
          nodes { ... on ClosedEvent { actor { login } } }
        }
      }
    }
  }
}
"""


class TrackerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    username: str
    title: str
    min_stars: int
    include_repos: frozenset[str]
    exclude_repos: frozenset[str]
    show_self_closed_repos: frozenset[str]
    show_self_closed_items: frozenset[str]
    status_overrides: Mapping[str, str]


@dataclass(frozen=True)
class Repository:
    full_name: str
    stars: int


@dataclass(frozen=True)
class Contribution:
    title: str
    url: str
    repository: str
    stars: int
    created_at: datetime
    item_type: str
    state: str
    merged_at: datetime | None


def log(message: str) -> None:
    print(f"[tracker] {message}", file=sys.stderr)


def setting(env: Mapping[str, str], name: str, default: str) -> str:
    return env.get(name, "").strip() or default


def repository_key(value: str, source: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[^/#\s]+/[^/#\s]+", value):
        raise TrackerError(f"{source} contains invalid repository {value!r}; expected owner/repo")
    return value.casefold()


def repository_list(raw: str, source: str) -> frozenset[str]:
    return frozenset(
        repository_key(value, source) for value in raw.split(",") if value.strip()
    )


def item_list(raw: str, source: str) -> frozenset[str]:
    items: set[str] = set()
    for value in filter(None, (part.strip() for part in raw.split(","))):
        match = re.fullmatch(r"([^/#\s]+/[^/#\s]+)#([1-9]\d*)", value)
        if not match:
            raise TrackerError(
                f"{source} contains invalid value {value!r}; expected owner/repo#number"
            )
        items.add(f"{match.group(1).casefold()}#{match.group(2)}")
    return frozenset(items)


def incorporated_prs(raw: str) -> dict[str, str]:
    return {key: "Adopted" for key in item_list(raw, "INCORPORATED_PRS")}


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    username = setting(env, "GITHUB_USERNAME", DEFAULT_USERNAME)
    if not re.fullmatch(r"[A-Za-z0-9-]+", username):
        raise TrackerError(f"GITHUB_USERNAME is invalid: {username!r}")

    try:
        min_stars = int(setting(env, "MIN_STARS", str(DEFAULT_MIN_STARS)))
    except ValueError as error:
        raise TrackerError("MIN_STARS must be a non-negative integer") from error
    if min_stars < 0:
        raise TrackerError("MIN_STARS must be a non-negative integer")

    return Config(
        username=username,
        title=setting(env, "TITLE", DEFAULT_TITLE),
        min_stars=min_stars,
        include_repos=repository_list(env.get("INCLUDE_REPOS", ""), "INCLUDE_REPOS"),
        exclude_repos=repository_list(env.get("EXCLUDE_REPOS", ""), "EXCLUDE_REPOS"),
        show_self_closed_repos=repository_list(
            env.get("SHOW_SELF_CLOSED_REPOS", ""), "SHOW_SELF_CLOSED_REPOS"
        ),
        show_self_closed_items=item_list(
            env.get("SHOW_SELF_CLOSED_ITEMS", ""), "SHOW_SELF_CLOSED_ITEMS"
        ),
        status_overrides=incorporated_prs(env.get("INCORPORATED_PRS", "")),
    )


class GitHub:
    def __init__(self, token: str) -> None:
        if not token:
            raise TrackerError("GITHUB_TOKEN is required")
        self.token = token

    def graphql(self, variables: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = json.dumps({"query": SEARCH_QUERY, "variables": variables}).encode()
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "my-oss-contributions",
            "X-GitHub-Api-Version": API_VERSION,
        }

        for attempt in range(3):
            try:
                request = Request(API_URL, data=payload, headers=headers, method="POST")
                with urlopen(request, timeout=30) as response:
                    result = json.load(response)
                break
            except HTTPError as error:
                body = error.read().decode(errors="replace")[:500]
                if error.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise TrackerError(f"GitHub API failed with HTTP {error.code}: {body}") from error
            except URLError as error:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise TrackerError(f"GitHub API request failed: {error.reason}") from error
            except json.JSONDecodeError as error:
                raise TrackerError("GitHub API returned invalid JSON") from error
        else:
            raise TrackerError("GitHub API request failed after retries")

        if not isinstance(result, dict):
            raise TrackerError("GitHub API returned an unexpected response")
        if result.get("errors"):
            messages = "; ".join(
                str(item.get("message", item)) if isinstance(item, dict) else str(item)
                for item in result["errors"]
            )
            raise TrackerError(f"GitHub API failed: {messages}")
        data = result.get("data")
        if not isinstance(data, dict):
            raise TrackerError("GitHub API response is missing data")
        return data


def search_expression(username: str, start: date | None, end: date | None) -> str:
    expression = f"author:{username}"
    if start and end:
        expression += f" created:{start.isoformat()}..{end.isoformat()}"
    return expression


def search_page(client: GitHub, expression: str, cursor: str | None) -> Mapping[str, Any]:
    search = client.graphql({"query": expression, "cursor": cursor}).get("search")
    if not isinstance(search, dict):
        raise TrackerError(f"GitHub search returned invalid data for {expression!r}")
    return search


def collect_pages(
    client: GitHub, expression: str, first_page: Mapping[str, Any]
) -> list[dict[str, Any]]:
    page = first_page
    items: list[dict[str, Any]] = []
    seen_cursors: set[str] = set()

    while True:
        nodes, page_info = page.get("nodes"), page.get("pageInfo")
        if not isinstance(nodes, list) or not isinstance(page_info, dict):
            raise TrackerError(f"GitHub search pagination is invalid for {expression!r}")
        items.extend(node for node in nodes if isinstance(node, dict))
        if not page_info.get("hasNextPage"):
            return items

        cursor = page_info.get("endCursor")
        if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
            raise TrackerError(f"GitHub search returned an invalid cursor for {expression!r}")
        seen_cursors.add(cursor)
        page = search_page(client, expression, cursor)


def search_range(
    client: GitHub,
    username: str,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    expression = search_expression(username, start, end)
    first_page = search_page(client, expression, None)
    count = first_page.get("issueCount")
    if not isinstance(count, int):
        raise TrackerError(f"GitHub search count is invalid for {expression!r}")
    if count <= SEARCH_LIMIT:
        return collect_pages(client, expression, first_page)

    if start is None or end is None:
        return search_range(client, username, GITHUB_START, datetime.now(timezone.utc).date())
    if start >= end:
        raise TrackerError(f"More than {SEARCH_LIMIT} contributions were created on {start}")

    midpoint = start + (end - start) // 2
    return search_range(client, username, start, midpoint) + search_range(
        client, username, midpoint + timedelta(days=1), end
    )


def fetch_authored_items(client: GitHub, username: str) -> list[dict[str, Any]]:
    log(f"Fetching contributions authored by {username}")
    unique: dict[str, dict[str, Any]] = {}
    for item in search_range(client, username):
        url = item.get("url")
        if not isinstance(url, str):
            raise TrackerError("GitHub search result is missing a URL")
        unique[url] = item
    return list(unique.values())


def repository_metadata(
    item: Mapping[str, Any], cache: dict[str, Repository]
) -> Repository:
    raw = item.get("repository")
    if not isinstance(raw, dict):
        raise TrackerError(f"{item.get('url', 'GitHub item')} is missing repository data")
    full_name, stars = raw.get("nameWithOwner"), raw.get("stargazerCount")
    if not isinstance(full_name, str) or not isinstance(stars, int):
        raise TrackerError(f"{item.get('url', 'GitHub item')} has invalid repository data")
    key = full_name.casefold()
    cache.setdefault(key, Repository(full_name, stars))
    return cache[key]


def should_include(repository: Repository, config: Config) -> bool:
    key = repository.full_name.casefold()
    if key in config.exclude_repos:
        return False
    if key in config.include_repos:
        return True
    return repository.stars >= config.min_stars


def is_authored_and_closed_by(item: Mapping[str, Any], username: str) -> bool:
    state = item.get("state")
    if not isinstance(state, str):
        raise TrackerError(f"{item.get('url', 'GitHub item')} is missing state")
    if state.upper() != "CLOSED":
        return False

    author = item.get("author")
    author_login = author.get("login") if isinstance(author, dict) else None
    if not isinstance(author_login, str) or author_login.casefold() != username.casefold():
        return False

    last_close = item.get("lastClose")
    if not isinstance(last_close, dict) or not isinstance(last_close.get("nodes"), list):
        raise TrackerError(
            f"{item.get('url', 'GitHub item')} has invalid close event data"
        )
    nodes = last_close["nodes"]
    if not nodes:
        return False

    event = nodes[-1]
    actor = event.get("actor") if isinstance(event, dict) else None
    login = actor.get("login") if isinstance(actor, dict) else None
    return isinstance(login, str) and login.casefold() == username.casefold()


def contribution_key(item: Mapping[str, Any], repository: Repository) -> str:
    number = item.get("number")
    if not isinstance(number, int):
        raise TrackerError(f"{item.get('url', 'GitHub item')} is missing number")
    return f"{repository.full_name.casefold()}#{number}"


def parse_time(value: Any, field: str, url: str) -> datetime:
    if not isinstance(value, str):
        raise TrackerError(f"{url} is missing {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TrackerError(f"{url} contains invalid {field}: {value!r}") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def pr_status(
    repository: str,
    number: int,
    state: str,
    merged_at: Any,
    overrides: Mapping[str, str],
) -> str:
    key = f"{repository.casefold()}#{number}"
    if key in overrides:
        return overrides[key]
    if merged_at is not None or state.upper() == "MERGED":
        return "Merged"
    return "Open" if state.upper() == "OPEN" else "Closed"


def normalize_item(
    item: Mapping[str, Any], repository: Repository, config: Config
) -> Contribution:
    kind = item.get("__typename")
    title, url, state, number = (
        item.get("title"),
        item.get("url"),
        item.get("state"),
        item.get("number"),
    )
    if kind not in {"Issue", "PullRequest"}:
        raise TrackerError(f"GitHub returned unsupported item type {kind!r}")
    if not isinstance(title, str) or not isinstance(url, str):
        raise TrackerError("GitHub item is missing title or URL")
    if not isinstance(state, str) or not isinstance(number, int):
        raise TrackerError(f"{url} is missing state or number")

    merged_at = (
        parse_time(item.get("mergedAt"), "mergedAt", url)
        if item.get("mergedAt") is not None
        else None
    )
    if kind == "PullRequest":
        item_type = "PR"
        output_state = pr_status(
            repository.full_name,
            number,
            state,
            merged_at,
            config.status_overrides,
        )
    else:
        item_type = "Issue"
        output_state = "Open" if state.upper() == "OPEN" else "Closed"

    return Contribution(
        title=title,
        url=url,
        repository=repository.full_name,
        stars=repository.stars,
        created_at=parse_time(item.get("createdAt"), "createdAt", url),
        item_type=item_type,
        state=output_state,
        merged_at=merged_at,
    )


def contributions(client: GitHub, config: Config) -> list[Contribution]:
    cache: dict[str, Repository] = {}
    result: list[Contribution] = []
    hidden_self_closed = 0
    for item in fetch_authored_items(client, config.username):
        repository = repository_metadata(item, cache)
        owner = repository.full_name.partition("/")[0]
        if owner.casefold() == config.username.casefold() or not should_include(repository, config):
            continue
        if (
            repository.full_name.casefold() not in config.show_self_closed_repos
            and contribution_key(item, repository) not in config.show_self_closed_items
            and is_authored_and_closed_by(item, config.username)
        ):
            hidden_self_closed += 1
            continue
        result.append(normalize_item(item, repository, config))
    log(
        f"Rendering {len(result)} contributions from {len(cache)} repositories; "
        f"hid {hidden_self_closed} items authored and closed by {config.username}"
    )
    return sorted(result, key=lambda item: item.created_at, reverse=True)


def is_variation_selector(character: str) -> bool:
    codepoint = ord(character)
    return 0xFE00 <= codepoint <= 0xFE0F or 0xE0100 <= codepoint <= 0xE01EF


def is_regional_indicator(character: str) -> bool:
    return 0x1F1E6 <= ord(character) <= 0x1F1FF


def display_units(value: str) -> list[tuple[str, int]]:
    units: list[tuple[str, int]] = []
    index = 0
    while index < len(value):
        start = index
        character = value[index]

        if is_regional_indicator(character):
            index += 1
            if index < len(value) and is_regional_indicator(value[index]):
                index += 1
            units.append((value[start:index], 2))
            continue

        codepoint = ord(character)
        width = 0 if category(character).startswith(("M", "C")) else (
            2 if east_asian_width(character) in {"W", "F"} else 1
        )
        emoji = 0x1F3FB <= codepoint <= 0x1F3FF
        index += 1

        while index < len(value):
            character = value[index]
            codepoint = ord(character)
            if is_variation_selector(character):
                emoji = emoji or character == VS16
                index += 1
            elif category(character).startswith("M"):
                emoji = emoji or character == KEYCAP
                index += 1
            elif 0x1F3FB <= codepoint <= 0x1F3FF or 0xE0020 <= codepoint <= 0xE007F:
                emoji = True
                index += 1
            elif character == ZWJ and index + 1 < len(value):
                emoji = True
                index += 2
            else:
                break

        units.append((value[start:index], max(width, 2) if emoji else width))
    return units


def display_width(value: str) -> int:
    return sum(width for _, width in display_units(value))


def clip(value: str, width: int) -> str:
    output: list[str] = []
    used = 0
    for unit, unit_width in display_units(value):
        if used + unit_width > width:
            break
        output.append(unit)
        used += unit_width
    return "".join(output)


def shorten(value: str, width: int, ellipsis: str = "…") -> str:
    if display_width(value) <= width:
        return value
    return f"{clip(value, width - display_width(ellipsis)).rstrip()}{ellipsis}"


def shorten_title(value: str) -> str:
    if display_width(value) < TITLE_CLIP_AT:
        return value
    shortened = f"{clip(value, TITLE_CLIP_AT).rstrip()}..."
    if display_width(shortened) > TITLE_MAX_WIDTH:
        raise TrackerError("Internal title width calculation failed")
    return shortened


def fixed(value: str, width: int, centered: bool = False) -> str:
    value = shorten(value, width)
    padding = width - display_width(value)
    left = padding // 2 if centered else 0
    return f"{NBSP * left}{value}{NBSP * (padding - left)}"


def markdown_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def link_title(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def repository_link(repository: str) -> str:
    label = repository
    if display_width(label) > REPOSITORY_WIDTH:
        label = repository.rsplit("/", 1)[-1]
    label = shorten(label, REPOSITORY_WIDTH)
    hover = f' "{link_title(repository)}"' if label != repository else ""
    return f"[`{fixed(label, REPOSITORY_WIDTH, True)}`](https://github.com/{repository}{hover})"


def render_contributions(items: list[Contribution]) -> str:
    if not items:
        return "_No matching contributions found._"

    lines: list[str] = []
    for item in items:
        title = shorten_title(item.title)
        hover = f' "{link_title(item.title)}"' if title != item.title else ""
        lines.append(
            f"<sub>`{fixed(item.created_at.strftime('%Y-%m'), DATE_WIDTH)}` | "
            f"`{fixed(item.item_type, TYPE_WIDTH, True)}` | "
            f"`{fixed(item.state, STATE_WIDTH, True)}` | "
            f"{repository_link(item.repository)} | "
            f"[{markdown_text(title)}]({item.url}{hover})</sub>"
        )
    return "  \n".join(lines)


def render_preview(items: list[Contribution], username: str) -> str:
    rows = items[:PREVIEW_COUNT]
    height = 78 + 32 * len(rows)
    groups: list[str] = []

    for index, item in enumerate(rows):
        repository = item.repository
        if display_width(repository) > REPOSITORY_WIDTH:
            repository = repository.rsplit("/", 1)[-1]
        repository = shorten(repository, REPOSITORY_WIDTH)
        title = shorten(item.title, PREVIEW_TITLE_WIDTH, "...")
        groups.append(
            f'''  <g transform="translate(22 {56 + index * 32})">
    <rect class="cell" x="0" y="0" width="66" height="24" rx="6"/>
    <text class="mono" x="33" y="16" text-anchor="middle">{item.created_at:%Y-%m}</text>
    <rect class="cell" x="76" y="0" width="52" height="24" rx="6"/>
    <text class="mono" x="102" y="16" text-anchor="middle">{escape(item.item_type)}</text>
    <rect class="cell" x="138" y="0" width="70" height="24" rx="6"/>
    <text class="mono" x="173" y="16" text-anchor="middle">{escape(item.state)}</text>
    <text class="repo" x="224" y="17">{escape(repository)}</text>
    <text class="item" x="425" y="17">{escape(title)}</text>
  </g>'''
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{PREVIEW_WIDTH}" height="{height}" viewBox="0 0 {PREVIEW_WIDTH} {height}" role="img" aria-labelledby="title description">
  <title id="title">Open-source contributions</title>
  <desc id="description">Contribution records for {escape(username)}</desc>
  <style>
    .background {{ fill: #ffffff; }}
    .border {{ fill: none; stroke: #d0d7de; }}
    .divider {{ stroke: #d8dee4; }}
    .heading {{ fill: #1f2328; font: 600 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .cell {{ fill: #f6f8fa; stroke: #d0d7de; }}
    .mono {{ fill: #1f2328; font: 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    .repo {{ fill: #0969da; font: 600 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .item {{ fill: #0969da; font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .more {{ fill: #0969da; font: 600 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    @media (prefers-color-scheme: dark) {{
      .background {{ fill: #0d1117; }}
      .border, .divider {{ stroke: #30363d; }}
      .heading, .mono {{ fill: #f0f6fc; }}
      .cell {{ fill: #161b22; stroke: #30363d; }}
      .repo, .item, .more {{ fill: #58a6ff; }}
    }}
  </style>

  <rect class="background" x="0.5" y="0.5" width="959" height="{height - 1}" rx="10"/>
  <rect class="border" x="0.5" y="0.5" width="959" height="{height - 1}" rx="10"/>
  <text class="heading" x="22" y="31">Open-Source Contributions</text>
  <line class="divider" x1="0" y1="45.5" x2="960" y2="45.5"/>

{chr(10).join(groups)}

  <text class="more" x="938" y="{height - 12}" text-anchor="end">View all contributions →</text>
</svg>
'''


def read_template(path: Path) -> str:
    try:
        template = path.read_text(encoding="utf-8")
    except OSError as error:
        raise TrackerError(f"Cannot read {path}: {error}") from error
    for placeholder in PLACEHOLDERS:
        if placeholder not in template:
            raise TrackerError(f"README.template.md does not contain {placeholder}")
    return template


def render_template(template: str, title: str, records: str) -> str:
    rendered = template.replace("{{TITLE}}", title).replace("{{CONTRIBUTIONS}}", records)
    return rendered.rstrip() + "\n"


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        log(f"{path.name} is already up to date")
        return False
    path.write_text(content, encoding="utf-8")
    log(f"Updated {path.name}")
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update the OSS contribution README")
    parser.add_argument("--dry-run", action="store_true", help="print without writing README.md")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parent
    try:
        template = read_template(root / "README.template.md")
        config = load_config()
        client = GitHub(os.environ.get("GITHUB_TOKEN", "").strip())
        items = contributions(client, config)
        rendered = render_template(
            template,
            config.title,
            render_contributions(items),
        )
        if args.dry_run:
            print(rendered, end="")
        else:
            write_if_changed(root / "README.md", rendered)
            write_if_changed(root / "preview-5.svg", render_preview(items, config.username))
        return 0
    except (OSError, TrackerError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
