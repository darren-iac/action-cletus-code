"""Extract JSON from Claude's execution output file.

This module extracts JSON from markdown code blocks in Claude's output,
which is the standard way Claude returns structured data.
"""

import json
import re
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        print("Usage: extract_json.py <execution_file> <output_file>", file=sys.stderr)
        sys.exit(1)

    execution_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2])

    if not execution_file.exists():
        print(f"Error: Execution file not found: {execution_file}", file=sys.stderr)
        sys.exit(1)

    content = execution_file.read_text()

    # Try to find a JSON object in the content
    # Look for content between ```json and ``` markers
    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find a raw JSON object
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            print("Error: Could not find JSON in Claude output", file=sys.stderr)
            sys.exit(1)

    try:
        data = json.loads(json_str)
        output_file.write_text(json.dumps(data, indent=2))
        print(f"Successfully wrote review.json")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        print(f"JSON string was: {json_str[:500]}...", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
