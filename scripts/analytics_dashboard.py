import os
from datetime import datetime, timedelta
from collections import defaultdict
from github import Github
from dotenv import load_dotenv
import json

load_dotenv()

class AnalyticsDashboard:
    def __init__(self):
        self.github = Github(os.getenv('GITHUB_TOKEN'))
        self.repo = self.github.get_repo('naman-msft/AKS')
    
    def generate_weekly_metrics(self):
        """Generate comprehensive weekly metrics"""
        one_week_ago = datetime.now() - timedelta(days=7)
        
        metrics = {
            'period': f"{one_week_ago.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}",
            'issues_created': 0,
            'issues_closed': 0,
            'ai_classifications': defaultdict(int),
            'human_overrides': 0,
            'average_time_to_first_response': [],
            'issues_by_area': defaultdict(int),
            'cri_issues': 0,
            'duplicate_issues': 0,
            'stale_closures': 0,
            'repair_items_created': 0
        }
        
        # Analyze issues created in the last week
        recent_issues = self.repo.get_issues(state='all', since=one_week_ago)
        
        for issue in recent_issues:
            if issue.created_at >= one_week_ago:
                metrics['issues_created'] += 1
                
                # Check AI classification
                for label in issue.labels:
                    if label.name in ['bug', 'support', 'feature', 'info_needed']:
                        metrics['ai_classifications'][label.name] += 1
                    if label.name == 'CRI':
                        metrics['cri_issues'] += 1
                    if label.name == 'duplicate':
                        metrics['duplicate_issues'] += 1
                
                # Calculate time to first response
                first_comment = None
                for comment in issue.get_comments():
                    if comment.user.login != issue.user.login:
                        first_comment = comment
                        break
                
                if first_comment:
                    response_time = (first_comment.created_at - issue.created_at).total_seconds() / 60
                    metrics['average_time_to_first_response'].append(response_time)
                
                # Check for overrides
                for comment in issue.get_comments():
                    if '/override-classification' in comment.body:
                        metrics['human_overrides'] += 1
            
            if issue.closed_at and issue.closed_at >= one_week_ago:
                metrics['issues_closed'] += 1
                if 'auto-closed' in [l.name for l in issue.labels]:
                    metrics['stale_closures'] += 1
        
        # Calculate averages
        if metrics['average_time_to_first_response']:
            avg_response = sum(metrics['average_time_to_first_response']) / len(metrics['average_time_to_first_response'])
            metrics['average_time_to_first_response'] = f"{avg_response:.1f} minutes"
        else:
            metrics['average_time_to_first_response'] = "No data"
        
        return metrics
    
    def generate_report(self):
        """Generate markdown report"""
        metrics = self.generate_weekly_metrics()
        
        report = f"""# AKS AI Triage Bot - Weekly Analytics Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary for {metrics['period']}

### Issue Volume
- **New Issues:** {metrics['issues_created']}
- **Closed Issues:** {metrics['issues_closed']}
- **CRI Issues:** {metrics['cri_issues']}
- **Duplicates Detected:** {metrics['duplicate_issues']}

### AI Performance
- **Total Classifications:** {sum(metrics['ai_classifications'].values())}
- **Human Overrides:** {metrics['human_overrides']}
- **Accuracy Rate:** {((sum(metrics['ai_classifications'].values()) - metrics['human_overrides']) / max(sum(metrics['ai_classifications'].values()), 1) * 100):.1f}%

### Response Times
- **Average Time to First Response:** {metrics['average_time_to_first_response']}
- **Manual Triage Time Saved:** ~{metrics['issues_created'] * 15} minutes

### Classification Breakdown
"""
        for classification, count in metrics['ai_classifications'].items():
            percentage = (count / max(sum(metrics['ai_classifications'].values()), 1)) * 100
            report += f"- **{classification.title()}:** {count} ({percentage:.1f}%)\n"
        
        report += f"""
### Automation Actions
- **Stale Issues Closed:** {metrics['stale_closures']}
- **Repair Items Requested:** {metrics['repair_items_created']}

## Recommendations
"""
        
        if metrics['human_overrides'] > sum(metrics['ai_classifications'].values()) * 0.1:
            report += "- ⚠️ High override rate detected. Consider retraining the classification model.\n"
        
        if metrics['cri_issues'] > 0:
            report += f"- 🚨 {metrics['cri_issues']} critical issues detected this week. Ensure proper escalation.\n"
        
        if metrics['duplicate_issues'] > metrics['issues_created'] * 0.2:
            report += "- 📋 High duplicate rate. Consider improving issue templates.\n"
        
        return report
    
    def save_metrics_history(self, metrics):
        """Save metrics for historical tracking"""
        history_file = 'triage_metrics_history.json'
        
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
        except:
            history = []
        
        history.append({
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics
        })
        
        # Keep last 52 weeks
        history = history[-52:]
        
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)

def main():
    dashboard = AnalyticsDashboard()
    report = dashboard.generate_report()
    print(report)
    
    # Save to file
    with open('weekly_triage_report.md', 'w') as f:
        f.write(report)
    
    # Save metrics history
    metrics = dashboard.generate_weekly_metrics()
    dashboard.save_metrics_history(metrics)

if __name__ == "__main__":
    main()