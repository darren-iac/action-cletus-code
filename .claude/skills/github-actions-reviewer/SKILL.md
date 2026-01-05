---
name: github-actions-reviewer
description: Reviews GitHub Actions workflow files for best practices, security issues, performance optimizations, and common pitfalls. Use when reviewing .yml or .yaml files in .github/workflows/ directory, or when the user mentions GitHub Actions, workflows, or CI/CD configuration.
allowed-tools: Read, Grep, Glob, Bash
---

# GitHub Actions Reviewer

Reviews GitHub Actions workflow files for best practices, security, and optimization opportunities.

## Review Focus Areas

### 1. Security
- **Secrets management**: Ensure secrets aren't logged or exposed in error messages
- **Token permissions**: Verify `permissions` are set to minimum required scope
- **Third-party actions**: Check for unpinned or suspicious action references
- **Code injection**: Look for unsafe use of `eval` or untrusted input

### 2. Performance
- **Caching**: Verify dependencies and build outputs are properly cached
- **Matrix strategy**: Check for inefficient matrix configurations
- **Concurrency**: Ensure workflows use `concurrency` to cancel duplicate runs
- **Conditional execution**: Verify `if` conditions are optimized

### 3. Best Practices
- **Action pinning**: Actions should use full SHAs or specific tags (not `@main`)
- **Reusable workflows**: Identify opportunities for reusable workflow extraction
- **Job dependencies**: Check for parallelization opportunities
- **Artifact handling**: Verify artifacts are uploaded/downloaded efficiently

### 4. Error Handling
- **Continue-on-error**: Verify it's only used where appropriate
- **Retry logic**: Check for operations that should retry on failure
- **Timeout handling**: Ensure jobs have reasonable `timeout-minutes`

## Common Issues to Flag

### Critical
- Actions using `@main` or `@master` without commit SHA
- Missing `permissions` block (defaults to write-all)
- Secrets printed to logs (echo, ::debug, ::notice)
- Hardcoded credentials or tokens
- Missing `timeout-minutes` on long-running jobs

### High Priority
- Inefficient matrix strategies (could be simplified)
- Missing caching for npm, pip, cargo, etc.
- Jobs that could run in parallel but are serialized
- Large action.yml files that could be reusable workflows

### Medium Priority
- Unused environment variables or inputs
- Inconsistent indentation or formatting
- Missing documentation comments for complex workflows

## Quick Checks

Run these checks for any workflow file:

```bash
# Check for unpinned actions
grep -n "uses.*@" workflow.yml | grep -v "@[a-f0-9]\{40\}" | grep -E "@(main|master|v[0-9]|develop)"

# Check for exposed secrets
grep -i "secret" workflow.yml | grep -E "(echo|::debug|::notice|::warning)"

# Check permissions
grep -A5 "^permissions:" workflow.yml

# Check for timeout
grep -n "timeout-minutes" workflow.yml
```

## Review Template

When reviewing a workflow, provide:

1. **Security Assessment**: Any critical security concerns
2. **Performance**: Opportunities for speed/efficiency gains
3. **Best Practices**: Deviations from recommended patterns
4. **Specific Issues**: Line-by-line feedback with suggestions

## References

- [GitHub Actions Security](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [Workflow Syntax](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions)
- [Reusable Workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
