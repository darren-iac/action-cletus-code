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

    # Read the execution file content
    content = execution_file.read_text()

    # The execution file might be:
    # 1. A JSON object with conversation history
    # 2. A JSON array of messages
    # 3. Raw text with markdown

    json_str = None

    # Try to parse as JSON first
    try:
        execution_data = json.loads(content)

        # If it's a list, look through each item
        if isinstance(execution_data, list):
            for item in reversed(execution_data):
                json_str = _extract_from_item(item)
                if json_str:
                    break
        # If it's a dict with messages
        elif isinstance(execution_data, dict):
            if "messages" in execution_data:
                messages = execution_data["messages"]
                for msg in reversed(messages):
                    if msg.get("role") == "assistant":
                        json_str = _extract_from_item(msg)
                        if json_str:
                            break
            # Check for result field
            if not json_str and "result" in execution_data:
                result = execution_data["result"]
                if isinstance(result, str):
                    match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
                    if match:
                        json_str = match.group(1)

    except json.JSONDecodeError:
        # Not JSON, treat as raw text
        match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if match:
            json_str = match.group(1)

    if not json_str:
        print("Error: Could not find JSON in Claude execution output", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(json_str)
        output_file.write_text(json.dumps(data, indent=2))
        print(f"Successfully wrote review.json")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        print(f"JSON string was: {json_str[:500]}...", file=sys.stderr)
        sys.exit(1)


def _extract_from_item(item):
    """Extract JSON from a message/item structure.

    Args:
        item: A dict representing a message or content item.

    Returns:
        JSON string if found, None otherwise.
    """
    if not isinstance(item, dict):
        return None

    # Check if this has content array
    if "content" in item:
        content = item["content"]
        if isinstance(content, list):
            for content_item in content:
                if content_item.get("type") == "text":
                    text = content_item.get("text", "")
                    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
                    if match:
                        return match.group(1)
        elif isinstance(content, str):
            match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match:
                return match.group(1)

    # Check for direct message field
    if "message" in item:
        message = item["message"]
        return _extract_from_item(message)

    return None


if __name__ == "__main__":
    main()

