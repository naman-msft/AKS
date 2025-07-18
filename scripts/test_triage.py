import json
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.issue_classifier import IssueClassifier
from datetime import datetime, timezone

def load_test_issues(file_path: str):
    """Load mock issues from JSON file"""
    with open(file_path, 'r') as f:
        return json.load(f)['issues']

def print_classification_result(issue, result):
    """Pretty print the classification result"""
    print(f"\n{'='*60}")
    print(f"Issue #{issue['id']}: {issue['title']}")
    print(f"{'='*60}")
    print(f"Classification: {result.classification} (confidence: {result.confidence:.2f})")
    print(f"Area: {result.suggested_area}")
    print(f"Reasoning: {result.reasoning}")
    
    if result.suggested_assignees:
        print(f"Assignees: {', '.join(result.suggested_assignees)}")
    
    print(f"Labels: {', '.join(result.suggested_labels)}")
    
    if result.missing_info:
        print(f"Missing Info: {', '.join(result.missing_info)}")
    
    print(f"\nSuggested Response:")
    print(f"{'-'*40}")
    print(result.suggested_response[:200] + "..." if len(result.suggested_response) > 200 else result.suggested_response)
    
    # Check if classification matches expected
    if 'expected_classification' in issue:
        match = "✓" if issue['expected_classification'] == result.classification else "✗"
        print(f"\nExpected: {issue['expected_classification']} {match}")

def simulate_time_based_actions(issue, created_date):
    """Simulate what would happen to this issue over time"""
    print(f"\nTime-based actions simulation:")
    
    # Fix: Use timezone-aware datetime
    created_dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    days_old = (now - created_dt).days
    
    if days_old > 7:
        print("  - Day 7: Would check for author response")
    if days_old > 14:
        print("  - Day 14: Would mark as stale if no response")
    if days_old > 21:
        print("  - Day 21: Would auto-close if still stale")

def main():
    # Check if using mock or real API
    use_mock = os.getenv('USE_MOCK_API', 'true').lower() == 'true'
    
    if use_mock:
        print("🧪 Running in MOCK mode (no API calls will be made)")
        azure_endpoint = "mock"
        azure_key = "mock-api-key"
        deployment_name = "mock"
    else:
        print("🚀 Running with Azure OpenAI")
        azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        azure_key = os.getenv('AZURE_OPENAI_API_KEY')
        deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
        
        if not all([azure_endpoint, azure_key, deployment_name]):
            print("❌ Error: Azure OpenAI credentials not found in .env file")
            return
    
    # Initialize classifier
    classifier = IssueClassifier(
        config_path=".github/triage-config.json",
        azure_endpoint=azure_endpoint,
        azure_key=azure_key,
        deployment_name=deployment_name
    )
    
    # Load test issues
    test_issues = load_test_issues("test-data/mock-issues.json")
    
    print(f"\nTesting {len(test_issues)} mock issues\n")
    
    # Process each issue
    results = []
    for issue in test_issues:
        result = classifier.classify_issue(issue)
        results.append(result)
        print_classification_result(issue, result)
        simulate_time_based_actions(issue, issue['created_at'])
    
    # Summary statistics
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    classifications = {}
    for result in results:
        classifications[result.classification] = classifications.get(result.classification, 0) + 1
    
    for class_type, count in classifications.items():
        print(f"{class_type}: {count} issues")
    
    print(f"\nAverage confidence: {sum(r.confidence for r in results) / len(results):.2f}")

if __name__ == "__main__":
    main()