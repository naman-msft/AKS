import os
import re
from github import Github
from dotenv import load_dotenv

load_dotenv()

class CommentCommandProcessor:
    def __init__(self):
        self.github = Github(os.getenv('GITHUB_TOKEN'))
        self.repo = self.github.get_repo('naman-msft/AKS')
        
        self.commands = {
            '/override-classification': self.override_classification,
            '/assign': self.assign_user,
            '/mark-as-cri': self.mark_as_cri,
            '/create-repair-item': self.create_repair_item,
            '/mark-duplicate': self.mark_duplicate,
            '/request-info': self.request_info,
            '/add-label': self.add_label
        }
    
    def process_comment(self, issue_number: int, comment_id: int):
        """Process commands in a comment"""
        issue = self.repo.get_issue(issue_number)
        comment = issue.get_comment(comment_id)
        
        # # Only process comments from authorized users (maintainers)
        # if comment.author_association not in ['OWNER', 'MEMBER', 'COLLABORATOR']:
        #     print(f"User {comment.user.login} not authorized to use commands")
        #     return

        # Only process comments from authorized users (check if user is repo owner or has write access)
        if comment.user.login != self.repo.owner.login:
            # Check if user has write access
            try:
                self.repo.has_in_collaborators(comment.user.login)
            except:
                print(f"Unauthorized user: {comment.user.login}")
                return

        # Or simpler - for testing, just check if it's you:
        if comment.user.login not in ['aritraghosh', 'julia-yin', 'AllenWen-at-Azure', 'github-actions[bot]']:
            print(f"Unauthorized user: {comment.user.login}")
            return
        
        for line in comment.body.split('\n'):
            line = line.strip()
            for cmd, handler in self.commands.items():
                if line.startswith(cmd):
                    args = line[len(cmd):].strip()
                    handler(issue, args)
    
    def override_classification(self, issue, classification):
        """Override AI classification"""
        valid_classifications = ['BUG', 'SUPPORT', 'FEATURE', 'INFO_NEEDED']
        
        if classification.upper() in valid_classifications:
            # Remove existing classification labels
            for label in issue.labels:
                if label.name in ['bug', 'support', 'feature', 'info_needed']:
                    issue.remove_from_labels(label)
            
            # Add new classification
            label_map = {
                'BUG': 'bug',
                'SUPPORT': 'SR-Support Request', 
                'FEATURE': 'feature-request',  # Changed from 'feature'
                'INFO_NEEDED': 'Needs Author Feedback'  # Changed from 'Needs Author Information'
            }
                        
            issue.add_to_labels(label_map[classification.upper()])
            issue.create_comment(f"✅ Classification overridden to: {classification.upper()}")
    
    def assign_user(self, issue, username):
        """Assign issue to user"""
        username = username.strip('@')
        try:
            issue.add_to_assignees(username)
            issue.create_comment(f"✅ Assigned to @{username}")
        except Exception as e:
            issue.create_comment(f"❌ Could not assign to @{username}: {str(e)}")
    
    def mark_as_cri(self, issue, severity='P0'):
        """Mark issue as Customer Reported Incident"""
        # Get current labels to avoid duplicates
        current_labels = {label.name for label in issue.labels}
        
        # Add labels one by one if they don't exist
        labels_to_add = ['CRI', severity, 'needs-immediate-attention']
        for label in labels_to_add:
            if label not in current_labels:
                issue.add_to_labels(label)
                print(f"Added label: {label}")
            else:
                print(f"Label already exists: {label}")
        
        # Add comment
        issue.create_comment("🚨 This issue has been marked as a Customer Reported Incident (CRI) and requires immediate attention.")
    
    def mark_duplicate(self, issue, duplicate_number):
        """Mark as duplicate of another issue"""
        try:
            duplicate_issue = self.repo.get_issue(int(duplicate_number))
            issue.add_to_labels('duplicate')
            issue.create_comment(
                f"This issue has been marked as a duplicate of #{duplicate_number}\n"
                f"Original issue: {duplicate_issue.title}"
            )
            issue.edit(state='closed')
        except:
            issue.create_comment(f"❌ Could not find issue #{duplicate_number}")
    
    def create_repair_item(self, issue, args):
        """Remind to create repair item"""
        issue.create_comment(
            "📋 Please create a repair item in Azure DevOps using this template:\n"
            "https://aka.ms/aks/github-repair-item\n\n"
            "Once created, link it here with:\n"
            "```\nRepair Item: [ADO-12345](https://dev.azure.com/...)\n```"
        )
        issue.add_to_labels('needs-repair-item')

    def request_info(self, issue, info_type):
        """Request specific information"""
        templates = {
            'logs': "Please provide the pod logs using:\n```\nkubectl logs -n <namespace> <pod-name>\n```",
            'version': "Please provide your AKS version:\n```\naz aks show -g <resource-group> -n <cluster-name> --query kubernetesVersion\n```",
            'yaml': "Please share your deployment YAML files (remove any sensitive data)"
        }
        
        response = templates.get(info_type, self.config['templates']['need_more_info'])
        issue.create_comment(response)
        issue.add_to_labels('Needs Author Feedback')

    def add_label(self, issue, label_name):
        """Add a label to the issue"""
        if label_name:
            issue.add_to_labels(label_name)
            print(f"Added label: {label_name}")
            issue.create_comment(f"✅ Added label: `{label_name}`")

def main():
    # This would be called by a GitHub Action when comments are posted
    import sys
    if len(sys.argv) != 3:
        print("Usage: comment_commands.py <issue_number> <comment_id>")
        return
    
    processor = CommentCommandProcessor()
    processor.process_comment(int(sys.argv[1]), int(sys.argv[2]))

if __name__ == "__main__":
    main()