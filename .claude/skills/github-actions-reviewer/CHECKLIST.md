# GitHub Actions Review Checklist

Use this checklist when reviewing workflow files systematically.

## Pre-Review
- [ ] Identify the workflow's purpose (CI, CD, scheduled job, etc.)
- [ ] Note the trigger events (push, pull_request, schedule, etc.)
- [ ] Check if this is a reusable workflow or called workflow

## Security Review
- [ ] `permissions` block exists and uses minimum required scopes
- [ ] No actions use `@main`, `@master`, or `@develop` branches
- [ ] Third-party actions are pinned to commit SHAs
- [ ] No secrets in environment variables or echo statements
- [ ] `contents: read` for PR workflows (no write access)
- [ ] Third-party actions from trusted sources

## Performance Review
- [ ] Dependencies cached (actions/cache or similar)
- [ ] `concurrency` set to cancel duplicate runs
- [ ] Jobs run in parallel where possible
- [ ] Matrix strategy is efficient (not unnecessarily complex)
- [ ] `timeout-minutes` set on all jobs
- [ ] Build artifacts only uploaded when needed

## Best Practices Review
- [ ] Action versions consistent across uses
- [ ] Reusable workflows for repeated patterns
- [ ] Environment variables defined at appropriate scope
- [ ] Step names are clear and descriptive
- [ ] Complex logic extracted to scripts or composite actions

## Error Handling Review
- [ ] `continue-on-error` only used where appropriate
- [ ] Failure conditions handled with `if` clauses
- [ ] Retry logic for flaky external operations
- [ ] Meaningful error messages in failure cases

## Code Quality Review
- [ ] Consistent YAML indentation (2 spaces)
- [ ] No duplicate steps or jobs
- [ ] Comments explain non-obvious logic
- [ ] File follows naming conventions
- [ ] No hardcoded values that should be config
