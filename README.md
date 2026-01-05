# Cletus Code Review

A GitHub Action that provides AI-powered pull request reviews with plugin support and auto-merge capabilities.

## Features

- **AI-Powered Reviews**: Leverages Claude AI to analyze pull requests
- **Plugin System**: Extensible plugins for pre-processing (kustomize, terraform, etc.)
- **Skill-Based Reviews**: Repo-specific or general review guidance via skills
- **Auto-Merge**: Automatically merge approved PRs based on configurable rules
- **Label Management**: Automatically applies labels based on review results
- **Rich Markdown Comments**: Publishes beautifully formatted review comments

## Architecture

```
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

## Usage

### Basic Example

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

### With Custom Skill

```yaml
      - uses: your-org/action-cletus-code@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          changed-files: ${{ steps.changed-files.outputs.all_changed_files }}
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          skill: python-review  # Use specific skill instead of auto-detect
```

### K8s/Kustomize Workflow

The kustomize plugin automatically detects `kustomization.yaml` files and generates diffs:

```yaml
name: K8s Review

on:
  pull_request:
    branches: [main]

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

The action will:
1. Detect kustomize files in changed directories
2. Render manifests for both base and PR
3. Post a diff comment
4. Include the diff in the Claude review context

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github-token` | Yes | `${{ github.token }}` | GitHub token for API access |
| `changed-files` | Yes | | JSON array of changed file paths from changed-files action |
| `anthropic-api-key` | Yes | | Anthropic API key for Claude Code |
| `skill` | No | (auto-detect) | Specific review skill to use |
| `output-dir` | No | `output` | Directory for output files |
| `claude-args` | No | `--dangerously-skip-permissions` | Additional arguments for Claude Code |
| `schema-file` | No | | Path to schema file for review validation |

## Skills

Skills define how Claude should review your code. The action looks for skills in this order:

1. **Explicit skill** from `skill` input
2. **Repo-specific skill** from central `.github` repo (e.g., `.claude/skills/k8s-argocd-review.md`)
3. **Default general skill** (built-in)

### Creating a Custom Skill

Add a skill file to your central `.github` repository:

```
.github/
└── .claude/
    └── skills/
        └── my-service-review.md
```

Then use it:

```yaml
      - uses: your-org/action-cletus-code@v1
        with:
          skill: my-service-review
          # ...
```

## Plugins

Plugins extend the action with pre-processing capabilities.

### Available Plugins

- **kustomize**: Detects `kustomization.yaml` files, renders manifests, and generates diffs

### Plugin Auto-Detection

Plugins run automatically when their conditions are met:
- Kustomize plugin runs when any `kustomization.yaml` is in changed files

## Configuration

### Auto-Merge

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

### Label Colors

Labels are automatically derived from review findings. Configure colors in `.github/process_review/config.yaml`:

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

## Permissions

```yaml
permissions:
  contents: read       # For fetching files and checking out refs
  pull-requests: write # For posting reviews, comments, and merging
```

## Outputs

The action produces:
- **Review comment**: Formatted markdown comment on the PR
- **Labels**: Applied based on review findings
- **Auto-merge**: PR is merged if approved and conditions are met
- **review.md**: Markdown review file in output directory
- **review.json**: Structured review data in output directory

## Local Testing with act

You can test this action locally using [act](https://github.com/nektos/act) before pushing changes to GitHub. This is especially useful for catching errors early without committing to git.

### Prerequisites

1. **Install act**:
   ```bash
   brew install act
   ```

2. **Start Colima** (or your Docker runtime):
   ```bash
   colima start
   ```

3. **Configure secrets** (for full integration test):
   ```bash
   cp .secrets.example .secrets
   # Edit .secrets with your actual tokens
   ```

### Running Tests

The project includes two test workflows for local testing:

#### Unit Test (No API Keys Required)

Tests basic functionality without external API calls:

```bash
./scripts/act-test.sh
```

Or directly with act:
```bash
act -j test-unit
```

This validates:
- Python and uv installation
- Project structure
- Python imports
- CLI entry point

#### Full Integration Test (Requires API Keys)

Tests the complete action including external API calls:

```bash
# First configure .secrets with your tokens
./scripts/act-test.sh -j test-local
```

Or directly with act:
```bash
act -j test-local --secret-file .secrets
```

### Configuration

The `.actrc` file configures act for local development:

- **Platform**: `catthehacker/ubuntu:act-latest` image with pre-installed tools
- **Architecture**: `linux/amd64` for Apple M-series compatibility
- **No force pull**: Uses cached images for faster testing

You can override these settings temporarily:
```bash
act -j test-unit --pull  # Force pull latest image
```

### Troubleshooting

**Docker connection issues**:
```bash
# Check Colima is running
colima status

# Restart if needed
colima restart
```

**Container architecture issues on Apple Silicon**:
The `.actrc` already includes `--container-architecture linux/amd64` for compatibility.

**View act logs in verbose mode**:
```bash
./scripts/act-test.sh -v
```

## License

MIT
