# Cletus Code Review

A GitHub Action that provides AI-powered pull request reviews with auto-merge capabilities.

## Features

- **AI-Powered Reviews**: Leverages Claude AI to analyze pull requests
- **Auto-Merge**: Automatically merge approved PRs based on configurable rules
- **Label Management**: Automatically applies labels based on review results
- **Rich Markdown Comments**: Publishes beautifully formatted review comments
- **GitHub Enterprise Support**: Works with both GitHub.com and GitHub Enterprise
- **Robust Error Handling**: Comprehensive retry logic and graceful degradation

## Usage

### Basic Example

```yaml
name: Code Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Cletus Code Review
        uses: your-org/action-cletus-code@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          review-file: review.json
```

### With Auto-Merge

```yaml
      - name: Run Cletus Code Review
        uses: your-org/action-cletus-code@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          review-file: review.json
          auto-merge: 'true'
          auto-merge-labels: 'renovate,dependencies'
```

### With Custom Config

Create a `.github/cletus-code.yaml` file in your repository:

```yaml
auto_merge:
  enabled: true
  branch_prefixes:
    - renovate/
    - dependabot/

labels:
  approved:
    name: 'cletus:approved'
    color: '0e8a16'
    description: 'Approved by Cletus'
  rejected:
    name: 'cletus:rejected'
    color: 'd93f0b'
    description: 'Rejected by Cletus'
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github-token` | Yes | `${{ github.token }}` | GitHub token for API access |
| `review-file` | Yes | `review.json` | Path to the review JSON file |
| `auto-merge` | No | `false` | Enable auto-merge for approved PRs |
| `auto-merge-labels` | No | `renovate,dependencies` | Labels that trigger auto-merge |
| `api-base-url` | No | | Custom GitHub API base URL (for GitHub Enterprise) |
| `claude-api-key` | No | | Claude API key for AI analysis |
| `config-path` | No | `.github/cletus-code.yaml` | Path to repo-specific config |

## Outputs

| Output | Description |
|--------|-------------|
| `review-posted` | Whether the review was successfully posted |
| `auto-merged` | Whether the PR was auto-merged |
| `verdict` | The review verdict (`approve`/`request_changes`/`comment`) |

## Review File Format

The action expects a JSON file with the following format:

```json
{
  "verdict": "approve",
  "summary": "LGTM! This looks good.",
  "details": [
    {
      "file": "src/main.py",
      "line": 42,
      "severity": "info",
      "message": "Consider adding type hints here."
    }
  ]
}
```

## Permissions

The action requires the following permissions:

```yaml
permissions:
  contents: write      # For auto-merge
  pull-requests: write # For posting reviews and comments
```

## Development

### Running Locally

```bash
# Install dependencies
pip install -e .

# Run the module
python -m cletus_code --help
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest
```

## License

MIT

## Support

For issues and questions, please [open an issue](https://github.com/your-org/action-cletus-code/issues).
