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

    # Read and parse the execution file (which is in JSON format)
    execution_data = json.loads(execution_file.read_text())

    # The execution file contains the full conversation history
    # We need to find the last assistant message that contains our JSON
    # Look for messages with content type "text" that contain ```json blocks
    json_str = None

    # Navigate through the execution structure to find messages
    # The structure is typically: root -> messages -> content -> text
    if "messages" in execution_data:
        messages = execution_data["messages"]
        # Search in reverse to find the last assistant message with JSON
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                for content_item in msg.get("content", []):
                    if content_item.get("type") == "text":
                        text = content_item.get("text", "")
                        # Look for ```json code blocks
                        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
                        if match:
                            json_str = match.group(1)
                            break
                if json_str:
                    break

    # Also check the "result" field which might contain the final output
    if not json_str and "result" in execution_data:
        result = execution_data["result"]
        if isinstance(result, str):
            match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
            if match:
                json_str = match.group(1)

    if not json_str:
        print("Error: Could not find JSON in Claude execution output", file=sys.stderr)
        # Print some debug info
        print(f"Execution data keys: {list(execution_data.keys())}", file=sys.stderr)
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

