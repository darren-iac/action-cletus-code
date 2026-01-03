# Process Review Scripts

This directory contains scripts for processing and publishing pull request reviews with enhanced error handling.

## Features

- Robust error handling with comprehensive logging
- GitHub API retry logic with exponential backoff
- File validation and fallback mechanisms
- Timeout support for network operations
- Graceful degradation for non-critical failures

## Usage

The script is automatically triggered by GitHub Actions when processing Renovate PRs.

## Repo Review Config

You can control auto-merge behavior with a repo-level config file at `.github/claude-review.yaml`.

Example:

```yaml
auto_merge:
  enabled: true
  branch_prefixes:
    - renovate/
```

When auto-merge is disabled or a PR does not match the allowlist, the workflow
still posts the review and includes the verdict it would have made.

## Repo Label Config

Label colors and descriptions can be customized per repo via
`.github/process_review/config.yaml` (or by setting `REVIEW_LABEL_CONFIG_PATH`).
