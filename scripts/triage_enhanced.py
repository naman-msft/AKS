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
        azure_key=os.getenv('AZURE_OPENAI_API_KEY'),
        deployment_name=os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
    )

    # Check if AI should process this issue
    existing_labels = [label.name for label in issue.labels]
    if not classifier.should_ai_classify(existing_labels):
        print(f"⚠️  Issue already classified by human, skipping AI classification")
        return
    
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
        
        # Show AI-detected area labels that will trigger assignments
        area_labels = [label for label in result.suggested_labels if 
                      label.startswith('addon/') or label.startswith('azure/') or 
                      label.startswith('extension/') or label.startswith('upstream/') or 
                      label.startswith('client/') or 
                      label in ['Security', 'networking', 'storage', 'windows', 'upgrade', 'docs', 
                               'fleet', 'keda', 'nodepools', 'resiliency', 'Scale and Performance', 
                               'Cilium', 'mesh', 'service-mesh', 'AzGov', 'AzChina', 
                               'app-gateway-for-containers', 'advanced-container-networking-services', 
                               'pod-identity', 'control-plane']]
        
        if area_labels:
            print(f"🎯 AI-detected area labels (will trigger auto-assignment): {', '.join(area_labels)}")
        
        # Post classification comment with wiki integration
        comment = f"🤖 **AI Issue Analysis**\n\n"
        comment += f"**Classification**: {result.classification}\n"
        comment += f"**Confidence**: {result.confidence:.2%}\n"
        comment += f"**Area**: {', '.join(result.suggested_areas) if result.suggested_areas else 'general'}\n"

        # Add wiki response if available
        if hasattr(result, 'wiki_response') and result.wiki_response and result.wiki_response.get('found_relevant_docs'):
            comment += "\n---\n\n"
            comment += "## 📖 Relevant Documentation Found\n\n"
            comment += result.wiki_response['response']
            comment += f"\n\n*Found {result.wiki_response['citations_count']} relevant documentation pages*"
        elif result.classification in ['BUG', 'SUPPORT']:
            comment += "\n---\n\n"
            comment += "## 📖 Documentation Search\n\n"
            comment += "I searched our documentation but couldn't find specific information about this issue. "
            comment += "This might be a new issue or require further investigation.\n"

        # Add specific guidance based on classification
        if result.classification == 'SUPPORT':
            comment += "\n\n### 🎫 Next Steps\n"
            comment += "Since this appears to be a support request, please:\n"
            comment += "1. Review the documentation links above (if any)\n"
            comment += "2. If the issue persists, [create a support ticket](https://azure.microsoft.com/support/create-ticket/)\n"
        elif result.classification == 'BUG':
            comment += "\n\n### 🐛 Bug Report Received\n"
            comment += "Thank you for reporting this issue. Our team will investigate and provide updates.\n"

        # Post the enhanced comment
        issue.create_comment(comment)
        print("✓ Posted enhanced response with wiki integration")
        
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