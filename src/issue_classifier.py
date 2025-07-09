import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from openai import AzureOpenAI
from difflib import SequenceMatcher
import re

@dataclass
class ClassificationResult:
    classification: str
    confidence: float
    reasoning: str
    suggested_labels: List[str]
    suggested_response: str
    suggested_assignees: List[str]
    suggested_areas: List[str] = None
    primary_area: str = None
    is_cri: bool = False
    duplicate_of: Optional[int] = None  # Add this field
    similar_issues: List[Dict] = None 

class IssueClassifier:
    def __init__(self, config_path: str, azure_endpoint: str, azure_key: str, deployment_name: str):
        self.config_path = config_path
        self.azure_endpoint = azure_endpoint
        self.azure_key = azure_key
        self.deployment_name = deployment_name
        
        # Initialize Azure OpenAI client only if not in mock mode
        if azure_key != "mock-api-key":
            self.client = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=azure_key,
                api_version="2024-02-15-preview"
            )
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
    
    # Around line 47-49, update the classify_issue method:
    def classify_issue(self, issue: Dict) -> ClassificationResult:
        """Classify a single issue using AI"""
        
        # Create the classification prompt
        prompt = self._create_classification_prompt(issue)
        
        # Call Azure OpenAI API (or use a mock response for testing)
        if os.getenv('USE_MOCK_API', 'false').lower() == 'true' or self.azure_key == "mock-api-key":
            response = self._mock_classify(issue)
        else:
            response = self._call_azure_openai(prompt)
        
        # Parse response and determine actions
        result = self._parse_classification_response(response, issue)
        
        return result
    
    def _create_classification_prompt(self, issue: Dict) -> str:
        return f"""You are an AKS (Azure Kubernetes Service) issue classifier. Analyze the following issue and classify it.

Issue Title: {issue['title']}
Issue Body: {issue['body']}

Classify as one of:
1. BUG - Clear product defect with reproducible steps
2. SUPPORT - Customer-specific issue needing investigation  
3. INFO_NEEDED - Insufficient information to classify
4. DUPLICATE - Similar to existing issue
5. FEATURE - Feature request, not a bug

Also identify the area from: {', '.join(self.config['keywords'].keys())}

Respond with JSON:
{{
  "classification": "BUG|SUPPORT|INFO_NEEDED|DUPLICATE|FEATURE",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "suggested_area": "area name",
  "missing_info": ["list of missing details if applicable"]
}}"""

    def _mock_classify(self, issue: Dict) -> Dict:
        """Mock classification for testing without API calls"""
        title_lower = issue['title'].lower()
        body_lower = issue['body'].lower()
        
        if 'feature' in title_lower or 'add support' in title_lower:
            classification = "FEATURE"
        elif len(issue['body']) < 50:
            classification = "INFO_NEEDED"
        elif 'reproducible steps' in body_lower or 'happens consistently' in body_lower:
            classification = "BUG"
        else:
            classification = "SUPPORT"
        
        # Determine area based on keywords
        suggested_area = "other"
        for area, keywords in self.config['keywords'].items():
            if any(keyword in title_lower or keyword in body_lower for keyword in keywords):
                suggested_area = area
                break
        
        return {
            "classification": classification,
            "confidence": 0.85,
            "reasoning": "Classified based on keywords and content analysis",
            "suggested_area": suggested_area,
            "missing_info": ["cluster version", "region"] if classification == "INFO_NEEDED" else []
        }
    
    def _call_azure_openai(self, prompt: str) -> Dict:
        """Call Azure OpenAI API for classification"""
        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=[
                {"role": "system", "content": "You are an expert at classifying AKS GitHub issues."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        return json.loads(response.choices[0].message.content)
    
    def _parse_classification_response(self, response: Dict, issue: Dict) -> ClassificationResult:
        """Parse AI response and determine all actions"""
        
        classification = response['classification']
        area = response['suggested_area']
        
        # Determine assignees
        suggested_assignees = []
        if classification == "BUG" and area in self.config['engineers']:
            suggested_assignees = self.config['engineers'][area][:1]
        
        # Determine labels
        suggested_labels = [classification.lower()]
        if classification == "SUPPORT":
            suggested_labels.append("SR-Support Request")
        elif classification == "INFO_NEEDED":
            suggested_labels.append("Needs Author Information")
        elif classification == "BUG":
            suggested_labels.extend(["bug", "needs-triage"])
        
        # Determine response template
        template_key = {
            "SUPPORT": "support_request",
            "BUG": "bug_acknowledged",
            "INFO_NEEDED": "need_more_info",
            "FEATURE": "bug_acknowledged",
            "DUPLICATE": "duplicate_issue"
        }.get(classification, "bug_acknowledged")
        
        suggested_response = self.config['templates'][template_key]
        
        # Around line 155, update the return statement in _parse_classification_response:

        return ClassificationResult(
            classification=classification,
            confidence=response['confidence'],
            reasoning=response['reasoning'],
            suggested_labels=suggested_labels,
            suggested_response=suggested_response,
            suggested_assignees=suggested_assignees,
            suggested_areas=[area],  # Make it a list
            primary_area=area,       # Add primary_area
            is_cri=False,           # Add is_cri
            duplicate_of=None,      # Add duplicate_of
            similar_issues=None     # Add similar_issues
        )
    
    def find_similar_issues(self, new_issue: Dict, existing_issues: List[Dict]) -> List[Dict]:
        """Find potentially duplicate issues"""
        similar_issues = []
        new_title_lower = new_issue['title'].lower()
        new_body_lower = new_issue.get('body', '').lower()
        
        for issue in existing_issues:
            if issue['id'] == new_issue['id']:
                continue
                
            title_similarity = SequenceMatcher(None, new_title_lower, issue['title'].lower()).ratio()
            body_similarity = SequenceMatcher(None, new_body_lower, issue.get('body', '').lower()).ratio()
            
            # Check for similar error messages
            new_errors = re.findall(r'error[:\s]+([^\n]+)', new_body_lower)
            existing_errors = re.findall(r'error[:\s]+([^\n]+)', issue.get('body', '').lower())
            error_match = any(error in existing_errors for error in new_errors)
            
            if title_similarity > 0.8 or (title_similarity > 0.6 and body_similarity > 0.7) or error_match:
                similar_issues.append({
                    'issue_number': issue['id'],
                    'title': issue['title'],
                    'similarity_score': max(title_similarity, body_similarity),
                    'is_error_match': error_match
                })
        
        return sorted(similar_issues, key=lambda x: x['similarity_score'], reverse=True)[:3]

    def is_cri_issue(self, issue: Dict) -> bool:
        """Detect if issue is a Customer Reported Incident (CRI)"""
        cri_keywords = [
            'production down', 'urgent', 'critical', 'emergency',
            'outage', 'all clusters affected', 'business impact',
            'severity 1', 'sev1', 'p0', 'blocker'
        ]
        
        text = f"{issue['title']} {issue.get('body', '')}".lower()
        return any(keyword in text for keyword in cri_keywords)

    def is_security_issue(self, issue: Dict) -> bool:
        """Detect if issue is security-related"""
        security_keywords = [
            'security', 'vulnerability', 'cve', 'exploit',
            'privilege escalation', 'unauthorized access',
            'data breach', 'exposure', 'injection'
        ]
        
        text = f"{issue['title']} {issue.get('body', '')}".lower()
        return any(keyword in text for keyword in security_keywords)

    def classify_issue_enhanced(self, issue: Dict, existing_issues: List[Dict] = None) -> ClassificationResult:
        """Enhanced classification with duplicate, CRI, and security detection"""
        # First check for duplicates
        if existing_issues:
            similar_issues = self.find_similar_issues(issue, existing_issues)
            # Around line 224, update the duplicate ClassificationResult creation:

            if similar_issues and similar_issues[0]['similarity_score'] > 0.85:
                return ClassificationResult(
                    classification="DUPLICATE",
                    confidence=similar_issues[0]['similarity_score'],
                    reasoning=f"Duplicate of issue #{similar_issues[0]['issue_number']}",
                    suggested_labels=["duplicate"],
                    suggested_response=f"This issue appears to be a duplicate of #{similar_issues[0]['issue_number']}. Please check that issue for updates.",
                    suggested_assignees=[],
                    suggested_areas=["other"],  # Changed from suggested_area to suggested_areas
                    primary_area="other",       # Add primary_area
                    is_cri=False,
                    duplicate_of=similar_issues[0]['issue_number'],
                    similar_issues=similar_issues
                )
        
        # Get base classification
        result = self.classify_issue(issue)
        
        # Check for CRI
        if self.is_cri_issue(issue):
            result.suggested_labels.extend(["CRI", "P0", "needs-immediate-attention"])
            result.suggested_response = "🚨 This issue has been identified as a critical customer-reported incident. Our on-call engineer has been notified and will respond shortly.\n\n" + result.suggested_response
        
        # Check for security
        if self.is_security_issue(issue):
            result.suggested_labels.extend(["security", "needs-security-review"])
            result.suggested_assignees = ["@security-team"]
            result.suggested_response = "🔒 This issue may have security implications. Our security team has been notified for review.\n\n" + result.suggested_response
        
        return result