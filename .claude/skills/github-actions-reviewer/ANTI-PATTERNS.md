# GitHub Actions Anti-Patterns

Common mistakes to avoid when writing GitHub Actions workflows.

## 1. Unpinned Action References

**Bad:**
```yaml
- uses: actions/checkout@main
- uses: actions/checkout@v2
```

**Good:**
```yaml
- uses: actions/checkout@11bd71901bb5b1739b1e4a4e4b5b5c2f0b9b4b4b
```

**Why:** Branch refs can change unexpectedly. Tags are mutable. Only commit SHAs guarantee the same code runs.

## 2. Missing Permissions Block

**Bad:**
```yaml
jobs:
  build:
    runs-on: ubuntu-latest
```

**Good:**
```yaml
permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
```

**Why:** Without permissions, workflows get write-all token access. PR workflows should only have read access.

## 3. Logging Secrets

**Bad:**
```yaml
- name: Debug
  run: |
    echo "API Key: ${{ secrets.API_KEY }}"
    echo "::debug::Token is ${{ secrets.TOKEN }}"
```

**Good:**
```yaml
- name: Debug
  run: |
    echo "API Key length: ${#API_KEY}"
  env:
    API_KEY: ${{ secrets.API_KEY }}
```

**Why:** Secrets in logs are security vulnerabilities. GitHub redacts some but not all formats.

## 4. No Concurrency Control

**Bad:**
```yaml
name: CI
on: [push, pull_request]
```

**Good:**
```yaml
name: CI
on: [push, pull_request]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**Why:** Without concurrency, every push creates a new workflow run. Old runs waste resources.

## 5. Missing Timeouts

**Bad:**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm test
```

**Good:**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: npm test
```

**Why:** Jobs can hang indefinitely. Timeouts prevent resource exhaustion.

## 6. Conditional Logic in Steps

**Bad:**
```yaml
- name: Deploy
  if: github.ref == 'refs/heads/main' && github.event_name == 'push'
  run: deploy.sh
```

**Good:**
```yaml
- name: Deploy
  if: ${{ github.ref == 'refs/heads/main' && github.event_name == 'push' }}
  run: deploy.sh
```

**Why:** Mixing YAML if with expressions can have unexpected behavior. Use expression syntax consistently.

## 7. Hardcoded Values

**Bad:**
```yaml
- name: Build
  run: docker build -t myapp:1.2.3 .
```

**Good:**
```yaml
- name: Build
  run: docker build -t myapp:${{ github.sha }} .
```

**Why:** Hardcoded values become stale. Use GitHub context for dynamic values.

## 8. Large Composite Actions

**Bad:**
```yaml
# 200-line action.yml with inline scripts
```

**Good:**
```yaml
# action.yml references external scripts
runs:
  using: composite
  steps:
    - run: ${{ github.action_path }}/scripts/setup.sh
      shell: bash
```

**Why:** Large inline scripts are hard to maintain and test.

## 9. Duplicate Job Definitions

**Bad:**
```yaml
jobs:
  test-node16:
    runs-on: ubuntu-latest
    steps: *test_steps
  test-node18:
    runs-on: ubuntu-latest
    steps: *test_steps
```

**Good:**
```yaml
jobs:
  test:
    strategy:
      matrix:
        node: [16, 18]
    runs-on: ubuntu-latest
    steps: *test_steps
```

**Why:** Matrix strategy is cleaner and easier to extend.

## 10. Ignoring Caching

**Bad:**
```yaml
- name: Install dependencies
  run: npm install
```

**Good:**
```yaml
- uses: actions/setup-node@v4
  with:
    cache: 'npm'
- run: npm ci
```

**Why:** Caching reduces install time from minutes to seconds.
