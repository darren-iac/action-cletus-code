# Cletus Code Review

[![CI](https://github.com/your-org/action-cletus-code/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/action-cletus-code/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/darren-iac/action-cletus-code?display_name=tag)](https://github.com/your-org/action-cletus-code/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

AI-powered pull request reviews using Claude, with an extensible plugin system, repo/skill-specific guidance, and optional auto-merge + label management.

> **What you get:** a rich PR review comment (Markdown), structured review artifacts (JSON/MD), optional labels, and optional auto-merge based on your rules.

---

## Table of contents

- [Quickstart](#quickstart)
- [Features](#features)
- [What it looks like](#what-it-looks-like)
- [How it works](#how-it-works)
- [Usage](#usage)
  - [Basic example](#basic-example)
  - [With a custom skill](#with-a-custom-skill)
  - [K8s/Kustomize workflow](#k8skustomize-workflow)
- [Inputs](#inputs)
- [Outputs](#outputs)
- [Skills](#skills)
- [Plugins](#plugins)
- [Configuration](#configuration)
  - [Auto-merge](#auto-merge)
  - [Label colors](#label-colors)
- [Permissions](#permissions)
- [Troubleshooting](#troubleshooting)
- [Local development & testing (act)](#local-development--testing-act)
- [Security & privacy](#security--privacy)
- [License](#license)

---

## Quickstart

Minimal workflow (fastest path to value):

```yaml
name: Cletus Code Review

on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: step-security/changed-files@v46
        id: changed-files
        with:
          dir_names: true

      - uses: your-org/action-cletus-code@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          changed-files: ${{ steps.changed-files.outputs.all_changed_files }}
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

---

## Features

- **AI-Powered Reviews**: Leverages Claude to analyze pull requests
- **Skill-Based Reviews**: Repo-specific or general review guidance via skills
- **Plugin System**: Extensible pre-processing plugins (kustomize, terraform, etc.)
- **Label Management**: Applies labels based on review results
- **Auto-Merge**: Optionally merges approved PRs based on configurable rules
- **Rich Markdown Comments**: Posts clean, information-dense PR review comments

---

## What it looks like

Add a screenshot or two so users can *see* the output immediately.

> **Recommended:** include one image of the PR comment and one image of labels applied.

```text
📌 Replace this block with screenshots:
- docs/images/review-comment.png
- docs/images/labels.png
```

Example (once you add images):

```md
![Cletus review comment](docs/images/review-comment.png)
![Labels applied](docs/images/labels.png)
```

---

## How it works

```text
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  changed-files  │────▶│  Cletus Action   │────▶│  Claude Code    │
│     Action      │     │                  │     │     Action      │
└─────────────────┘     │  ┌────────────┐  │     └─────────────────┘
                        │  │  Plugins   │  │
                        │  │  - kustomize││
                        │  │  - terraform││
                        │  └────────────┘  │
                        │  ┌────────────┐  │
                        │  │   Skills   │  │
                        │  │  - general │  │
                        │  │  - k8s     │  │
                        │  └────────────┘  │
                        └──────────────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │  Review Results  │
                        │  - Comment       │
                        │  - Labels        │
                        │  - Auto-merge    │
                        └──────────────────┘
```

High-level flow:

1. **changed-files** enumerates paths/dirs touched by the PR.
2. **Cletus** checks out context, runs plugin pre-processing when applicable (ex: kustomize diffs).
3. **Cletus** selects a **skill** (explicit or auto-detected) and assembles a review prompt/context.
4. **Claude Code** runs the review and returns structured findings.
5. **Cletus** posts a rich Markdown PR comment, writes artifacts, and optionally applies labels / auto-merges.

---

## Usage

### Basic example

```yaml
name: Code Review

on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: step-security/changed-files@v46
        id: changed-files
        with:
          dir_names: true

      - uses: your-org/action-cletus-code@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          changed-files: ${{ steps.changed-files.outputs.all_changed_files }}
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

### With a custom skill

```yaml
- uses: your-org/action-cletus-code@v1
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    changed-files: ${{ steps.changed-files.outputs.all_changed_files }}
    anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
    skill: python-review # Use specific skill instead of auto-detect
```

### K8s/Kustomize workflow

The kustomize plugin automatically detects `kustomization.yaml` files and generates diffs.

```yaml
name: K8s Review

on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: step-security/changed-files@v46
        id: changed-files
        with:
          dir_names: true
          dir_names_max_depth: 3

      - uses: your-org/action-cletus-code@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          changed-files: ${{ steps.changed-files.outputs.all_changed_files }}
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

What the action does:

1. Detect kustomize files in changed directories
2. Render manifests for both base and PR
3. Post a diff comment
4. Include the diff in the Claude review context

---

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github-token` | Yes | `${{ github.token }}` | GitHub token for API access (comments/labels/merge) |
| `changed-files` | Yes | — | JSON array of changed file paths from the changed-files action |
| `anthropic-api-key` | Yes | — | Anthropic API key for Claude/Claude Code |
| `skill` | No | auto-detect | Specific review skill to use |
| `output-dir` | No | `output` | Directory for output artifacts |
| `claude-args` | No | `--dangerously-skip-permissions` | Additional arguments for Claude Code |
| `schema-file` | No | — | Path to schema file for review validation |
| `settings` | No | — | JSON settings for Claude Code (for MCP servers, etc) |

---

## Outputs

If you set formal action outputs, list them here. If not, you can keep this as "Artifacts & side effects".

### Artifacts written to `output-dir`

| Path | Description |
|------|-------------|
| `review.md` | Markdown review comment content |
| `review.json` | Structured review data (machine-readable) |

### Side effects

- **PR comment** posted with findings and recommendations
- **Labels** applied based on findings (optional / configurable)
- **Auto-merge** triggered when rules match and the review is approved (optional / configurable)

---

## Skills

Skills define *how* Claude should review your code (tone, focus areas, risk tolerance, repo conventions, etc.).

Skill resolution order:

1. **Explicit skill** from `skill` input
2. **Repo-specific skill** from central `.github` repo (example: `.claude/skills/k8s-argocd-review.md`)
3. **Default general skill** (built-in)

### Creating a custom skill

Add a skill file to your central `.github` repository:

```text
.github/
└── .claude/
    └── skills/
        └── my-service-review.md
```

Then reference it:

```yaml
- uses: your-org/action-cletus-code@v1
  with:
    skill: my-service-review
    # ...
```

**Tip:** Keep skills short, opinionated, and testable. Include:
- coding standards and lint expectations
- risk scoring expectations
- "what not to comment on" (to reduce noise)
- required checks for your stack (Terraform/K8s/security/etc.)

---

## Plugins

Plugins extend the action with pre-processing capabilities (diff generation, domain-specific context, normalization).

### Available plugins

- **kustomize**: Detects `kustomization.yaml` files, renders manifests, and generates diffs

### Plugin auto-detection

Plugins run automatically when their conditions are met:

- Kustomize plugin runs when any `kustomization.yaml` is in changed files

> If you add more plugins, document each with: trigger condition → what it computes → how it affects the review.

---

## Configuration

Optional repo configuration files unlock additional behavior.

### Auto-merge

Create `.github/claude-review.yaml` in your repository:

```yaml
auto_merge:
  enabled: true
  branch_prefixes:
    - renovate/
    - dependabot/
  author_logins:
    - trusted-bot
```

### Label colors

Labels are derived from review findings. Configure colors in `.github/process_review/config.yaml`:

```yaml
labels:
  default_color: "6f42c1"
  risk_colors:
    HIGH: "d73a4a"
    MEDIUM: "fbca04"
    LOW: "2da44e"
  change_type_colors:
    create: "2da44e"
    update: "0e8a16"
    delete: "d73a4a"
```

---

## Permissions

Minimal recommended permissions:

```yaml
permissions:
  contents: read       # Read repo content for context/diffs
  pull-requests: write # Post comments, apply labels, merge PRs
```

Notes:
- If you see errors about "Resource not accessible by integration", your token likely lacks write permissions for PRs.
- On some repos/orgs, the default `GITHUB_TOKEN` may be more restricted; set explicit permissions as shown above.

---

## Troubleshooting

### No comment posted

- Confirm the workflow has `pull-requests: write`.
- Confirm the job actually ran on `pull_request` events (and not only on `push`).

### Claude/Anthropic auth errors

- Verify `ANTHROPIC_API_KEY` is set as a repository/org secret.
- If using environments, ensure the secret is available to that environment.

### Kustomize diff missing

- Ensure `kustomization.yaml` is in the changed set (or in directories included by `changed-files`).
- Increase `dir_names_max_depth` if needed.

---

## Local development & testing (act)

You can test the action locally with [act](https://github.com/nektos/act).

### Prerequisites

1. Install act:
   ```bash
   brew install act
   ```

2. Start Colima (or your Docker runtime):
   ```bash
   colima start
   ```

3. Configure secrets (for full integration test):
   ```bash
   cp .secrets.example .secrets
   # Edit .secrets with your actual tokens
   ```

### Running tests

#### Unit test (no API keys required)

```bash
act -j test-unit
```

Validates:
- Python + uv install
- project structure
- imports
- CLI entrypoint

#### Full integration test (requires API keys)

```bash
act -j test-local --secret-file .secrets
```

### act config

The `.actrc` file configures act for local development:

- Platform: `catthehacker/ubuntu:act-latest`
- Architecture: `linux/amd64` (helps on Apple Silicon)
- Uses cached images for faster testing

<details>
  <summary>Verbose logs</summary>

```bash
act -j test-unit -v
# or for integration test:
act -j test-local --secret-file .secrets -v
```

</details>

---

## Security & privacy

- **Secrets**: Never print API keys or tokens. Redact sensitive values in logs.
- **PR data**: This action sends PR context to the configured LLM provider (Anthropic). Treat it as a data egress path.
- **Recommended**: Limit usage to trusted repos, or restrict which file paths are included in the review context (future enhancement).

---

## License

MIT — see [LICENSE](./LICENSE).
