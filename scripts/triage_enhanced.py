import os
import sys
from github import Github
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.issue_classifier import IssueClassifier

load_dotenv()

def main(issue_number):
    g = Github(os.getenv('GITHUB_TOKEN'))
    repo = g.get_repo('naman-msft/AKS')
    issue = repo.get_issue(int(issue_number))
    
    print(f"Processing issue #{issue.number}: {issue.title}")
    
    # Get existing open issues for duplicate detection
    existing_issues = []
    for existing in repo.get_issues(state='open'):
        if existing.number != issue.number:
            existing_issues.append({
                'id': existing.number,
                'title': existing.title,
                'body': existing.body or ''
            })
    
    # Initialize classifier
    classifier = IssueClassifier(
        config_path=".github/triage-config.json",
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
        azure_key=os.getenv('AZURE_OPENAI_KEY'),
        deployment_name=os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
    )
    
    # Prepare issue data
    issue_data = {
        'id': issue.number,
        'title': issue.title,
        'body': issue.body or '',
        'author': issue.user.login,
        'created_at': issue.created_at.isoformat()
    }
    
    # Use enhanced classification
    result = classifier.classify_issue_enhanced(issue_data, existing_issues)
    
    print(f"Classification: {result.classification} (confidence: {result.confidence:.2f})")
    
    if result.confidence > 0.7:
        # Apply labels
        issue.add_to_labels(*result.suggested_labels)
        print(f"✓ Applied labels: {', '.join(result.suggested_labels)}")
        
        # Post response
        issue.create_comment(result.suggested_response)
        print("✓ Posted response")
        
        # Handle assignments
        if result.suggested_assignees:
            assignees = [a.replace('@', '') for a in result.suggested_assignees]
            try:
                issue.add_to_assignees(*assignees)
                print(f"✓ Assigned to: {', '.join(assignees)}")
            except Exception as e:
                print(f"⚠️  Could not assign: {e}")
        
        # Close if duplicate
        if result.classification == "DUPLICATE" and hasattr(result, 'duplicate_of'):
            issue.edit(state='closed')
            print(f"✓ Closed as duplicate of #{result.duplicate_of}")
    else:
        print("⚠️  Low confidence - manual review needed")
        issue.add_to_labels("needs-human-review")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python triage_enhanced.py <issue_number>")
        sys.exit(1)
    
    main(sys.argv[1])