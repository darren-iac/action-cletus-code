import pytest
import os

def test_re_review_remote_pr(run_act, tmp_path):
    """Refactored version of re-review.sh used for re-reviewing a remote PR."""
    
    required_secrets = ["GITHUB_TOKEN", "ANTHROPIC_API_KEY"]
    available_secrets = [s for s in required_secrets if os.environ.get(s)]
    
    if len(available_secrets) < len(required_secrets):
        pytest.skip("Missing required environment secrets for re-review test")

    # Setup event payload
    pr_url = "https://github.com/darren-iac/k8s/pull/630"
    payload = {
        "inputs": {
            "pr_url": pr_url
        }
    }
    
    # Run act
    result = run_act(
        workflow=".github/workflows/re-review-pr.yml",
        event_payload=payload,
        secrets=available_secrets,
        env={"DRY_RUN": "true"} # Ensure safety
    )
    
    # Debug output on failure
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        
    assert result.returncode == 0
    # Add specific assertions about the output if possible
    # e.g., checking that it found the PR, found files, etc.
    assert "re-review" in result.stdout # Job name
    assert "Found secrets in environment" not in result.stdout # That specific log was from the shell script, but good to note
