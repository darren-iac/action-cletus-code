# Fix for Issue #16: review.json Output Not Being Created

## Problem Summary

The review orchestrator was successfully loading skills and generating prompts, but Claude Code was not producing the expected `review.json` file output. The workflow failed with:

```
ERROR - Review file not found in workspace: output/review.json
ERROR - Unexpected error in main: review file not found: output/review.json
```

## Root Cause

The original implementation relied on Claude Code **manually writing** a `review.json` file to the workspace output directory. This approach had several issues:

1. **No explicit instruction**: The prompt didn't explicitly tell Claude to write a JSON file
2. **No schema guarantee**: Without a schema, the output format was unreliable
3. **File writing uncertainty**: Claude may not consistently write files to the expected location
4. **Model behavior variance**: Different model versions may handle file output differently

## Solution: Use Claude Code Action's Structured Output Feature

The fix leverages the **structured output** capability of the `anthropics/claude-code-action`, which provides:

- **JSON Schema validation**: Output is validated against a schema before being returned
- **Guaranteed output format**: The action ensures the output matches the schema
- **Direct access via outputs**: The structured JSON is available via `steps.<step-id>.outputs.structured_output`
- **No file writing needed**: The action handles structured output internally

### Implementation Changes

#### 1. Created JSON Schema (`src/cletus_code/templates/review-schema.json`)

Defines the expected structure:
```json
{
  "type": "object",
  "required": ["approved", "overallRisk", "summary", "findings"],
  "properties": {
    "approved": { "type": "boolean" },
    "overallRisk": { "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NEGLIGIBLE"] },
    "summary": { "type": "string" },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "title", "summary", "risk"],
        "properties": {
          "type": { "enum": ["finding", "version", "resource"] },
          "title": { "type": "string" },
          "summary": { "type": "string" },
          "risk": { "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NEGLIGIBLE"] },
          ...
        }
      }
    }
  }
}
```

#### 2. Updated `action.yml`

Changed the Claude Code invocation to use `--json-schema`:

```yaml
- name: Run Claude Code
  id: claude-review
  uses: anthropics/claude-code-action/base-action@v1.0.27
  with:
    prompt_file: ${{ github.action_path }}/${{ inputs.output-dir }}/claude-prompt.md
    anthropic_api_key: ${{ inputs.anthropic-api-key }}
    claude_args: |
      ${{ inputs.claude-args }} --json-schema '${{ github.action_path }}/${{ inputs.output-dir }}/review-schema.json'
    settings: ${{ inputs.settings }}
    show_full_output: 'true'
```

Added a step to extract the structured output:

```yaml
- name: Write review.json from structured output
  run: |
    OUTPUT='${{ steps.claude-review.outputs.structured_output }}'
    if [ -n "$OUTPUT" ] && [ "$OUTPUT" != "null" ]; then
      echo "$OUTPUT" > "${{ github.action_path }}/${{ inputs.output-dir }}/review.json"
    else
      # Fallback to workspace check for backward compatibility
      ...
    fi
```

#### 3. Updated `run_review.py`

**Modified `_invoke_claude_code`** to copy the schema file:

```python
def _invoke_claude_code(self, prompt: str) -> None:
    # Write prompt to file
    prompt_file = self.output_dir / "claude-prompt.md"
    self.output_dir.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt)

    # Copy JSON schema file for structured output
    import shutil
    schema_source = Path(__file__).parent / "templates" / "review-schema.json"
    schema_dest = self.output_dir / "review-schema.json"

    if schema_source.exists():
        shutil.copy(schema_source, schema_dest)
        logger.info(f"Review schema copied to {schema_dest}")
```

**Modified `_build_claude_prompt`** to include output format instructions:

```python
# Add instructions for structured output
sections.append("""

## Output Format

Your review will be captured using a **structured JSON output** system. Provide a comprehensive review following this structure:

1. **approved** (boolean): Should this PR be merged?
2. **overallRisk** (string): CRITICAL, HIGH, MEDIUM, LOW, or NEGLIGIBLE
3. **summary** (string): 1-3 sentence overview of the review
4. **findings** (array): List of specific findings...

The structured output system will automatically format your response according to the JSON schema provided.

""")
```

## Benefits of This Approach

1. **Reliability**: The action guarantees structured output that matches the schema
2. **Validation**: Output is validated before being returned
3. **Backward compatible**: Falls back to checking workspace if structured output is unavailable
4. **Clear contract**: The schema serves as documentation for expected output format
5. **Better DX**: Easier to debug when output doesn't match expectations

## Testing

To test this fix:

1. Run the workflow with a sample PR
2. Check that `review.json` is created in the output directory
3. Verify the JSON matches the schema structure
4. Confirm downstream processing works correctly

## References

- [Claude Code Action Structured Outputs Documentation](https://github.com/anthropics/claude-code-action/blob/main/docs/usage.md)
- [Structured outputs on the Claude Developer Platform](https://claude.com/blog/structured-outputs-on-the-claude-developer-platform)
- [JSON Schema Draft 7](https://json-schema.org/specification-links.html)

---

**Status**: ✅ Implemented

**Files Modified**:
- `action.yml` - Updated Claude Code invocation and added structured output extraction
- `src/cletus_code/run_review.py` - Added schema copy and updated prompt instructions
- `src/cletus_code/templates/review-schema.json` - New JSON schema file

**Issue**: #16
