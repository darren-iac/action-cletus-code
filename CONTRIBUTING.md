# Contributing to Cletus Code Review

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/your-username/action-cletus-code.git
   cd action-cletus-code
   ```

2. **Set up a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

```bash
pytest
```

## Code Style

We follow PEP 8 style guidelines. Please run the formatter before submitting:

```bash
black src/
isort src/
```

## Submitting Changes

1. Create a new branch for your feature or bugfix
2. Make your changes and write tests
3. Ensure all tests pass
4. Submit a pull request with a clear description

## Pull Request Guidelines

- Include tests for new features
- Update documentation as needed
- Keep changes focused and minimal
- Follow the existing code style

Thank you for your contributions!
