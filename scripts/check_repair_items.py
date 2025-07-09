import os
from github import Github
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

class RepairItemChecker:
    def __init__(self):
        self.github = Github(os.getenv('GITHUB_TOKEN'))
        self.repo = self.github.get_repo('naman-msft/AKS')
        
    def check_missing_repair_items(self):
        """Check bugs that need repair items"""
        seven_days_ago = datetime.now() - timedelta(days=7)
        
        # Get all bug issues
        bug_issues = self.repo.get_issues(labels=['bug'], state='open')
        
        for issue in bug_issues:
            if issue.created_at < seven_days_ago:
                # Check if repair item exists (look for specific comment pattern)
                has_repair_item = False
                for comment in issue.get_comments():
                    if "Repair Item:" in comment.body or "ADO Link:" in comment.body:
                        has_repair_item = True
                        break
                
                if not has_repair_item:
                    print(f"Issue #{issue.number} needs repair item")
                    self.create_repair_item_reminder(issue)
    
    def create_repair_item_reminder(self, issue):
        """Post reminder to create repair item"""
        assignees = ' '.join([f"@{a.login}" for a in issue.assignees])
        
        issue.create_comment(
            f"{assignees} This bug issue has been open for 7+ days without a repair item. "
            f"Please create a repair item in Azure DevOps and link it here.\n\n"
            f"To link a repair item, comment with:\n"
            f"```\n"
            f"Repair Item: [ADO-12345](https://dev.azure.com/...)\n"
            f"```"
        )
        issue.add_to_labels('needs-repair-item')

def main():
    checker = RepairItemChecker()
    checker.check_missing_repair_items()

if __name__ == "__main__":
    main()