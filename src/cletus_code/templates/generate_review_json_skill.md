# Generate Final Review JSON

You are the final step in the code review process. Your task is to produce a **complete JSON review report**.

## Input

You will receive:
- The accumulated analysis and findings from the review
- Context about the PR being reviewed
- All code changes and their impacts

## Your Task

Generate your complete review as a **single JSON object** in a markdown code block. Your entire response should be the JSON - no additional commentary, no prose outside the JSON.

```json
{
  "approved": true,
  "overallRisk": "LOW",
  "summary": "Brief 1-3 sentence overview of the review",
  "findings": [
    {
      "type": "finding",
      "title": "Short descriptive title",
      "summary": "Detailed explanation",
      "risk": "MEDIUM",
      "tags": ["security"],
      "cosmetic": false,
      "location": {
        "resource": "file.ext",
        "path": "path/to/file.ext",
        "line": 123
      },
      "evidence": {
        "diff": "...",
        "snippet": "..."
      }
    }
  ]
}
```

## Critical Requirements

1. **Output ONLY the JSON** in a markdown code block - no other text
2. **All required fields must be present**:
   - `approved` (boolean)
   - `overallRisk` (string: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "NEGLIGIBLE")
   - `summary` (string, max 200 chars)
   - `findings` (array)
3. **Each finding must have**: `type`, `title`, `summary`, `risk`

This JSON will be automatically validated and parsed.
