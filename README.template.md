# {{TITLE}}

My open-source contributions.

{{CONTRIBUTIONS}}

# About This Project

This project automatically maintains a Markdown record of my contributions to external open-source projects.

Sensible defaults keep the record focused by excluding repositories owned by the tracked user and items that user both opened and closed. These items may represent work that was withdrawn before adoption or created by mistake. Issues are still retained when a linked pull request by the tracked user was merged.

For example, exceptions can allow a low-star repository (`INCLUDE_REPOS`), retain self-closed items from a selected repository (`SHOW_SELF_CLOSED_REPOS`), or mark a pull request incorporated through a maintainer's separate commit as `Adopted` (`INCORPORATED_PRS`).

## Features

- Filter repositories by star count and explicit inclusion or exclusion rules.
- Exclude personal repositories and likely abandoned or accidental activity by default.
- Preserve resolved issues and support repository-level and PR-status exceptions.
- Run automatically with GitHub Actions and commit only when the generated README changes.

See the [usage guide](USAGE.md) for configuration and instructions.
