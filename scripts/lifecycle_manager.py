import os
import sys
import argparse
from datetime import datetime, timedelta
from github import Github
from dotenv import load_dotenv

load_dotenv()

class LifecycleManager:
    def __init__(self):
        self.github = Github(os.getenv('GITHUB_TOKEN'))
        self.repo = self.github.get_repo('naman-msft/AKS')
    
    def check_needs_attention(self, days=5):
        """Check issues that need attention after X days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Check "Needs Author Information" labels
        needs_info_issues = self.repo.get_issues(labels=['Needs Author Information'], state='open')
        
        for issue in needs_info_issues:
            last_comment = None
            for comment in issue.get_comments().reversed:
                if comment.user.login == issue.user.login:
                    last_comment = comment
                    break
            
            if not last_comment or last_comment.created_at < cutoff_date:
                print(f"Issue #{issue.number} needs attention - no author response for {days} days")
                issue.add_to_labels('Stale')
                issue.create_comment(
                    f"This issue has been marked as stale because we haven't heard from you in {days} days. "
                    f"Please provide the requested information or this issue will be closed in 7 days."
                )
    
    def check_investigation_status(self, days=14):
        """Check issues under investigation for too long"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        investigation_issues = self.repo.get_issues(labels=['Under Investigation'], state='open')
        
        for issue in investigation_issues:
            if issue.created_at < cutoff_date:
                print(f"Issue #{issue.number} has been under investigation for {days}+ days")
                issue.add_to_labels('needs-attention', 'investigation-overdue')
                
                # Find assignees and mention them
                assignees = issue.assignees
                mentions = ' '.join([f"@{a.login}" for a in assignees])
                
                issue.create_comment(
                    f"{mentions} This issue has been under investigation for {days} days. "
                    f"Please provide an update on the investigation status."
                )
    
    def close_stale_issues(self, days=7):
        """Close issues that have been stale for X days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        stale_issues = self.repo.get_issues(labels=['Stale'], state='open')
        
        for issue in stale_issues:
            # Check when 'Stale' label was added
            stale_event = None
            for event in issue.get_events():
                if event.event == 'labeled' and event.label.name == 'Stale':
                    stale_event = event
                    break
            
            if stale_event and stale_event.created_at < cutoff_date:
                print(f"Closing stale issue #{issue.number}")
                issue.create_comment(
                    "This issue has been automatically closed due to inactivity. "
                    "If you still need assistance, please open a new issue with updated information."
                )
                issue.edit(state='closed')
                issue.add_to_labels('auto-closed')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, required=True)
    parser.add_argument('--action', choices=['needs-attention', 'escalate', 'close-stale'])
    args = parser.parse_args()
    
    manager = LifecycleManager()
    
    if args.action == 'needs-attention':
        manager.check_needs_attention(args.days)
    elif args.action == 'escalate':
        manager.check_investigation_status(args.days)
    elif args.action == 'close-stale':
        manager.close_stale_issues(args.days)

if __name__ == "__main__":
    main()