# Usage

This tool collects Issues and Pull Requests authored by a configured GitHub user and automatically maintains a contribution timeline in `README.md`. By default, it focuses on external open-source repositories.

Rather than listing every activity, it filters personal repositories and work that may be noise, such as items the tracked user created and later closed. Most filtering rules can be adjusted with explicit exceptions.

## Default behavior

The defaults are designed to preserve meaningful external contributions while reducing unnecessary records.

- Repositories owned by the tracked user are treated as personal work and excluded.
- Repositories with fewer stars than `MIN_STARS` are excluded.
- Issues and unmerged Pull Requests created and closed by the tracked user are excluded.
- A self-closed Issue is retained when it was resolved by a merged Pull Request from the tracked user.
- An unmerged Pull Request closed by a maintainer is retained as `Closed`.

These rules reduce noise; they do not judge whether a contribution succeeded or failed.

Use the following settings when an explicit exception is needed:

- `INCLUDE_REPOS`: include repositories regardless of star count.
- `EXCLUDE_REPOS`: exclude selected repositories unless an item is explicitly included.
- `INCLUDE_ITEMS`: include selected Issues or Pull Requests despite repository and default filters.
- `EXCLUDE_ITEMS`: always exclude selected Issues or Pull Requests.
- `SHOW_SELF_CLOSED_REPOS`: retain self-closed items from selected repositories.
- `INCORPORATED_PRS`: mark Pull Requests applied through a maintainer's separate commit as `Adopted`.

## Configuration

Add Repository Variables under **Settings → Secrets and variables → Actions → Variables**. Only `TRACKED_GITHUB_USERNAME` is required; every other variable has a default.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRACKED_GITHUB_USERNAME` | None (required) | GitHub user whose contributions are collected |
| `TITLE` | `Open Source Contributions` | Generated README title |
| `MIN_STARS` | `100` | Minimum current repository star count |
| `INCLUDE_REPOS` | Empty | Repositories included regardless of star count |
| `EXCLUDE_REPOS` | Empty | Repositories excluded unless overridden by `INCLUDE_ITEMS` |
| `INCLUDE_ITEMS` | Empty | Issues or Pull Requests included unless listed in `EXCLUDE_ITEMS` |
| `EXCLUDE_ITEMS` | Empty | Issues or Pull Requests always excluded |
| `SHOW_SELF_CLOSED_REPOS` | Empty | Repositories whose self-closed items remain visible |
| `INCORPORATED_PRS` | Empty | Pull Requests displayed as `Adopted` |

GitHub reserves Repository Variable names beginning with `GITHUB_`, so the workflow maps `TRACKED_GITHUB_USERNAME` to the script's required `GITHUB_USERNAME` environment variable. If the value is missing or blank, the script exits with:

```text
Error: GITHUB_USERNAME is required
```

Comma-separated values are trimmed and compared case-insensitively.

```text
TRACKED_GITHUB_USERNAME=YangSiJun528
INCLUDE_REPOS=owner1/repo1,owner2/repo2
EXCLUDE_REPOS=owner3/repo3
INCLUDE_ITEMS=owner3/repo3#789
EXCLUDE_ITEMS=owner1/repo1#123,owner2/repo2#456
SHOW_SELF_CLOSED_REPOS=owner1/repo1
INCORPORATED_PRS=spring-projects/spring-framework#12345,owner/repo#456
```

## Filtering rules

More specific rules take priority. At the same scope, exclusion takes priority over inclusion. Item rules apply to both Issues and Pull Requests, using comma-separated `owner/repo#number` values.

1. An item in `EXCLUDE_ITEMS` is excluded, even if it is also in `INCLUDE_ITEMS`.
2. An item in `INCLUDE_ITEMS` is included without applying repository exclusion, ownership, star, or self-close filters.
3. Items without an item-level rule follow the existing repository and default filters below.

| Conflicting settings | Result |
| --- | --- |
| `INCLUDE_ITEMS` and `EXCLUDE_REPOS` | Include the item |
| `EXCLUDE_ITEMS` and `INCLUDE_REPOS` | Exclude the item |
| `INCLUDE_ITEMS` and `EXCLUDE_ITEMS` | Exclude the item |
| `INCLUDE_REPOS` and `EXCLUDE_REPOS` | Exclude the repository |

Only items authored by the tracked user are collected; `INCLUDE_ITEMS` does not fetch another user's work. Inclusion does not change an item's status: an included closed, unmerged PR stays `Closed` unless a status override applies.

For items without an item-level rule, repositories are selected in this order:

1. Repositories owned by `TRACKED_GITHUB_USERNAME` are excluded.
2. Repositories in `EXCLUDE_REPOS` are excluded.
3. Repositories in `INCLUDE_REPOS` pass the star filter.
4. Every other repository must have at least `MIN_STARS` stars.

After a repository is selected, an Issue or unmerged Pull Request created and closed by `TRACKED_GITHUB_USERNAME` is hidden by default. `SHOW_SELF_CLOSED_REPOS` disables only this self-close filter; it does not override ownership, `EXCLUDE_REPOS`, `EXCLUDE_ITEMS`, or the star filter. A low-star repository may therefore need to appear in both `INCLUDE_REPOS` and `SHOW_SELF_CLOSED_REPOS`. `INCLUDE_REPOS` still bypasses only the star filter.

A self-closed Issue that passes repository filtering remains visible when a merged Pull Request authored by `TRACKED_GITHUB_USERNAME` is linked to it. A Pull Request listed in `INCORPORATED_PRS` also bypasses the self-close filter and is displayed as `Adopted`. Neither exception overrides `EXCLUDE_ITEMS` or `EXCLUDE_REPOS`.

The self-close filter hides an item only when both its author and its latest closing actor match `TRACKED_GITHUB_USERNAME`. If either actor differs or cannot be verified, this filter keeps the item.

For example, `EXCLUDE_ITEMS=RustPython/RustPython#8763` excludes just that Issue while preserving other contributions to `RustPython/RustPython`.

## Pull Request statuses

Pull Request status is resolved in this order:

1. Listed in `INCORPORATED_PRS` → `Adopted`
2. Merged by GitHub → `Merged`
3. Currently open → `Open`
4. Otherwise → `Closed`

An unmerged `Closed` Pull Request is not automatically interpreted as rejected, failed, or unused.

## Running with GitHub Actions

Run the workflow manually from **Actions → Update Open Source Contributions → Run workflow**.

The scheduled workflow uses `0 15 * * *`, which corresponds to 00:00 KST every day. GitHub queueing may delay the actual start time.

The workflow uses the repository's default `GITHUB_TOKEN` with only `contents: write`. No Personal Access Token is required. It commits as `github-actions[bot]` only when `README.md` or `preview-5.svg` changes.

## Preview

The workflow also maintains `preview-5.svg` with the five latest contributions. Embed it in another README with:

```markdown
[![Open-Source Contributions](https://raw.githubusercontent.com/YangSiJun528/my-oss-contributions/main/preview-5.svg)](https://github.com/YangSiJun528/my-oss-contributions)
```

The entire image links to this repository. The workflow does not modify any other repository or profile README.

## Template

Edit `README.template.md` to control the generated document. Both placeholders are required:

```text
{{TITLE}}
{{CONTRIBUTIONS}}
```

`{{TITLE}}` is replaced with `TITLE`, and `{{CONTRIBUTIONS}}` is replaced with the generated timeline. The script exits with a clear error if either placeholder is missing.

## Local dry run

Python 3.11 or later and a GitHub token are required. The implementation uses only the Python standard library and the GitHub GraphQL API.

```bash
GITHUB_USERNAME=YangSiJun528 \
GITHUB_TOKEN="$(gh auth token)" \
python update_contributions.py --dry-run
```

`--dry-run` performs the API query, filtering, Markdown generation, and template rendering without changing `README.md` or `preview-5.svg`. It prints the complete generated README to stdout. Do not store the token in a file or commit it to Git.

## Implementation details

- Items are sorted by their full `created_at` timestamp in descending order and display only `YYYY-MM`.
- GitHub Search pagination and its 1,000-result limit are handled by splitting oversized date ranges.
- Repository metadata and linked Pull Request lookups are cached during each run.
- Linked work is detected through GitHub closing-Pull-Request relationships and verified Pull Request references in the Issue body or comments by the tracked user.
- Contribution rows use fixed display widths: 27 columns for repositories and up to 84 columns for titles. Titles are shortened from 81 columns with `...`.
- ASCII letters and numbers count as one display column; CJK, full-width characters, and emoji count as two.

## License

[MIT License](LICENSE)
