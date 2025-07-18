import os
import sys
from github import Github
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.issue_classifier import IssueClassifier

load_dotenv()

def main(issue_number):
    # Initialize GitHub client
    g = Github(os.getenv('GITHUB_TOKEN'))
    repo = g.get_repo('naman-msft/AKS')  # Change to your repo
    
    # Get the issue
    issue = repo.get_issue(int(issue_number))
    
    print(f"Processing issue #{issue.number}: {issue.title}")
    
    # Initialize classifier
    classifier = IssueClassifier(
        config_path=".github/triage-config.json",
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
        azure_key=os.getenv('AZURE_OPENAI_API_KEY'),
        deployment_name=os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
    )
    
    # Classify the issue
    issue_data = {
        'id': issue.number,
        'title': issue.title,
        'body': issue.body or '',
        'author': issue.user.login,
        'created_at': issue.created_at.isoformat()
    }
    
    result = classifier.classify_issue(issue_data)
    
    print(f"Classification: {result.classification} (confidence: {result.confidence:.2f})")
    print(f"Suggested labels: {result.suggested_labels}")
    
    # Apply labels
    if result.confidence > 0.7:  # Only apply if confident
        issue.add_to_labels(*result.suggested_labels)
        print(f"✓ Applied labels: {', '.join(result.suggested_labels)}")
        
        # Post response
        issue.create_comment(result.suggested_response)
        print("✓ Posted response")
        
        # Assign if it's a bug
        if result.suggested_assignees:
            # Remove @ from usernames
            assignees = [a.replace('@', '') for a in result.suggested_assignees]
            try:
                issue.add_to_assignees(*assignees)
                print(f"✓ Assigned to: {', '.join(assignees)}")
            except Exception as e:
                print(f"⚠️  Could not assign to {', '.join(assignees)}: {str(e)}")
                print("   (This is normal if the users don't have access to your fork)")
    else:
        print("⚠️  Low confidence - manual review needed")
        issue.add_to_labels("needs-human-review")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python triage_github_issue.py <issue_number>")
        sys.exit(1)
    
    main(sys.argv[1])