# Process Review Tests

Comprehensive test suite for the Temu Claude code review workflow.

## Test Coverage

### `test_process_review.py` (Original Tests)
- Unit tests for individual functions
- Module stubs for dependencies
- Basic workflow tests

### `test_comprehensive.py` (New Tests)
- **New findings schema validation** - Tests for the `findings` structure
- **Config module tests** - Validates `config.yaml` loading and label colors
- **Utils module tests** - Tests `truncate()`, `normalize_risk()`, `risk_sort_key()`, `format_resource()`, etc.
- **Label derivation** - Tests for tag-based label generation
- **Markdown building** - Validates template rendering with findings
- **Integration tests** - End-to-end workflow scenarios
- **Error handling** - Missing files, invalid JSON, empty data

## Running Tests

### Run all tests:
```bash
cd /Users/darren/repos/.github/process_review
uv run pytest tests/ -v
```

### Run only comprehensive tests:
```bash
uv run pytest tests/test_comprehensive.py -v
```

### Run only unit tests (skip integration):
```bash
uv run pytest tests/ -m "not integration" -v
```

### Run with coverage:
```bash
uv run pytest tests/ --cov=. --cov-report=html
```

### Run specific test class:
```bash
uv run pytest tests/test_comprehensive.py::TestConfigModule -v
```

### Run specific test:
```bash
uv run pytest tests/test_comprehensive.py::TestUtilsModule::test_truncate_short_text_unchanged -v
```

## Test Fixtures

### Sample Review Data
- `sample_review_new_schema()` - New findings schema with `type`-based entries
- `minimal_valid_review()` - Minimal valid review (empty findings)

## Key Test Scenarios

### 1. Schema Validation
- Validates new findings schema structure
- Checks required fields
- Tests enum constraints (risk levels)
- Validates `$ref` references

### 2. Label Derivation
- Findings tags: `update:{image|chart}` → update labels
- Findings tags: `change:{type}` → change labels
- Colors loaded from `config.yaml`

### 3. Format Resource
- String input: `"Deployment/default/nginx"` → returned as-is
- Dict input: `{kind, namespace, name}` → `"Kind/namespace/name"`
- Cluster-scoped: Falls back to `"default"` namespace
- Invalid input: Returns `""`

### 4. Integration Workflows
- Approved review → Labels + Comment + Approve + Merge
- Rejected review → Labels + Comment (no merge)
- Mixed findings → Both version and resource labels applied

## Adding New Tests

When adding new functionality, add tests following this pattern:

```python
class TestNewFeature:
    """Tests for new feature."""

    def test_basic_functionality(self):
        """Test that basic functionality works."""
        result = process_review.new_function()
        assert result == expected

    def test_error_handling(self):
        """Test that errors are handled properly."""
        with pytest.raises(ValueError):
            process_review.new_function(invalid_input)
```

## Continuous Integration

These tests run automatically in the workflow when:
- Pull requests are opened
- Code is pushed to main branch
- Workflow is manually triggered

To ensure high confidence the workflow will work:
1. Tests validate against real schema file
2. Tests use actual config.yaml
3. Integration tests mock GitHub API realistically
