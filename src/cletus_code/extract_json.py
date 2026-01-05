"""Extract JSON from Claude's output file."""

import json
import re
import sys


def main():
    if len(sys.argv) != 3:
        print("Usage: extract_json.py <execution_file> <output_file>", file=sys.stderr)
        sys.exit(1)

    execution_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(execution_file, 'r') as f:
        content = f.read()

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
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print("Successfully wrote review.json")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        print(f"JSON string was: {json_str[:500]}...", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
