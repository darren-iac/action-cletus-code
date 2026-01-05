import pytest
import os

def test_local_test_job(run_act):
    """Refactored version of act-test.sh -j test-local"""
    
    # We need to mock the inputs/secrets that test-local expects
    # In act-test.sh, it used .secrets file. Here we try to use env or skip
    
    required_secrets = ["GITHUB_TOKEN", "ANTHROPIC_API_KEY"]
    available_secrets = [s for s in required_secrets if os.environ.get(s)]
    
    if len(available_secrets) < len(required_secrets):
        # If we don't have secrets in env, check if we want to fail or skip
        # For local dev, maybe checking .secrets file is better?
        # But this is a "test", so it should fit into pytest patterns.
        pytest.skip(f"Missing required secrets in environment: {set(required_secrets) - set(available_secrets)}")

    result = run_act(
        job="test-local",
        secrets=available_secrets,
        # workflow is implicitly .github/workflows for job lookup usually, 
        # but specifying the file is safer if we know it
        # workflow=".github/workflows/test-local.yml" 
        env={
            "REVIEW_PR_NUMBER": "630",
            "GITHUB_REPOSITORY": "darren-iac/k8s",
            "GITHUB_EVENT_NAME": "workflow_dispatch"  # Set event type for workflow_dispatch workflow
        }
    )
    
    # Assertions
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        
    assert result.returncode == 0
    assert "Success" in result.stdout or "Job succeeded" in result.stdout

def test_unit_test_job(run_act):
    """Refactored version of act-test.sh -j test-unit"""
    
    # Unit tests shouldn't strictly require secrets for logic, 
    # BUT actions/checkout needs GITHUB_TOKEN if the repo is private.
    required_secrets = ["GITHUB_TOKEN"]
    # Provide available secrets, but test should pass even if empty
    # due to skipped checkout logic in workflow
    available_secrets = [s for s in required_secrets if os.environ.get(s)]

    result = run_act(
        job="test-unit",
        secrets=available_secrets
    )
    
    if result.returncode != 0:
        print("Act failed with code:", result.returncode)
#        print("STDOUT:", result.stdout) # Commented out to reduce noise if verified
        print("STDERR:", result.stderr)

    assert result.returncode == 0
