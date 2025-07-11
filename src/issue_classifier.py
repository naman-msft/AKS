import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from openai import AzureOpenAI
from difflib import SequenceMatcher
import re
try:
    from .wiki_assistant import WikiAssistant
except ImportError:
    WikiAssistant = None

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
    duplicate_of: Optional[int] = None 
    similar_issues: List[Dict] = None 
    wiki_response: Optional[Dict] = None

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
        
        try:
            self.wiki_assistant = WikiAssistant()
            self.wiki_enabled = True
        except Exception as e:
            print(f"Wiki assistant not available: {e}")
            self.wiki_assistant = None
            self.wiki_enabled = False
    
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
        
        wiki_response = None
        if self.wiki_enabled and result.classification in ['BUG', 'SUPPORT', 'INFO_NEEDED']:
            try:
                wiki_response = self.wiki_assistant.search_and_answer(
                    issue['title'], 
                    issue['body']
                )
            except Exception as e:
                print(f"Wiki search failed: {e}")
        
        # Add wiki response to result
        result.wiki_response = wiki_response
        return result
    
    def _create_classification_prompt(self, issue: Dict) -> str:
        return f"""You are an AKS (Azure Kubernetes Service) issue classifier. Analyze the following issue and classify it according to official AKS triage guidelines.

    Issue Title: {issue['title']}
    Issue Body: {issue['body']}

    OFFICIAL AKS LABELING GUIDELINES:

    - **SR-Support Request**
    - During triage, add to issues that are customer issues or need more information.

    - **Needs Author Information**
    - Add to issues where we are asking the customer for more information. Automatically added to any issues needing a support request.

    - **Stale**
    - Do not manually add this label. It is used by the bot and has different wait times depending on the type of issue.

    - **Under Investigation**
    - Add this label when the issue is actively undergoing investigation from the PG (engineer assigned). No further action from the customer is needed.

    - **Needs Attention**
    - Added by the bot to issues which have been inactive and require attention from the GitHub v-team.

    - **resolution/fix-released**
    - Add once the issue-related bug fix has been merged into a release.

    - **resolution/sr-resolved**
    - Add this label once the customer's support ticket has been resolved and closed.

    CLASSIFICATION DECISION TREE:
    1. BUG - Product defects, reproducible errors, crashes, parsing issues, configuration problems
    → Gets: bug + triage labels (internal investigation)
    → Examples: "YAML parsing error", "Pod crashes with OOMKilled", "Service mesh not working", "API server timeout"
    
    2. SUPPORT - Customer-specific issues, how-to questions, configuration help, best practices, guidance needed
    → Gets: SR-Support Request label (customer opens support ticket)
    → Examples: "How to configure X", "Help with Y", "Best practices for Z", "Customer environment issue"
    
    3. INFO_NEEDED - Insufficient information, vague descriptions, missing critical details
    → Gets: Needs Author Feedback label (triggers stale process)
    → Examples: "Pod not starting" (no details), "Cluster broken" (no context), "Error occurred" (no error message)
    
    4. FEATURE - Feature requests, enhancements, new functionality
    → Gets: feature-request label
    → Examples: "Add support for X", "Enhancement: Y", "New feature: Z"
    
    5. DUPLICATE - Similar to existing issue
    → Gets: duplicate label

    CRITICAL DISTINCTIONS:
    - Technical errors/crashes = BUG (needs engineering investigation)
    - Customer questions/guidance = SUPPORT (needs support ticket)
    - Vague reports = INFO_NEEDED (needs more details from customer)

    Technical Area Classification from: {', '.join(self.config['keywords'].keys())}

    Respond with JSON:
    {{
    "classification": "BUG|SUPPORT|INFO_NEEDED|DUPLICATE|FEATURE",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of why this classification was chosen based on the guidelines above",
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
            "suggested_area": area,
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
        """Parse AI response and determine all actions based on official AKS bot behavior"""
        
        classification = response['classification']
        area = response.get('suggested_area', 'other')
        
        # Determine assignees
        suggested_assignees = []
        if classification == "BUG" and area in self.config['engineers']:
            suggested_assignees = self.config['engineers'][area][:1]
        
        # Determine labels based on official AKS bot documentation
        suggested_labels = []
        
        if classification == "BUG":
            # Clear product defects get bug + triage for internal investigation
            suggested_labels.extend(["bug", "triage"])
        elif classification == "SUPPORT":
            # Customer-specific issues and how-to questions get support request
            suggested_labels.extend(["SR-Support Request"])
        elif classification == "INFO_NEEDED":
            # Insufficient information gets author feedback (triggers 7-day stale process)
            suggested_labels.extend(["Needs Author Feedback"])
        elif classification == "FEATURE":
            suggested_labels.append("feature-request")
        elif classification == "DUPLICATE":
            suggested_labels.append("duplicate")
        
        # Determine response template
        template_key = {
            "SUPPORT": "support_request",
            "BUG": "bug_acknowledged", 
            "INFO_NEEDED": "need_more_info",
            "FEATURE": "feature_acknowledged",
            "DUPLICATE": "duplicate_issue"
        }.get(classification, "bug_acknowledged")
        
        suggested_response = self.config['templates'][template_key]
        
        return ClassificationResult(
            classification=classification,
            confidence=response['confidence'],
            reasoning=response['reasoning'],
            suggested_labels=suggested_labels,
            suggested_response=suggested_response,
            suggested_assignees=suggested_assignees,
            suggested_areas=[area],
            primary_area=area,
            is_cri=False,
            duplicate_of=None,
            similar_issues=None
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
    
    def should_ai_classify(self, issue_labels: List[str]) -> bool:
        """Check if AI should classify or defer to human labels"""
        # Don't override human classifications
        human_classification_labels = ['bug', 'feature-request', 'SR-Support Request', 
                                    'documentation', 'question', 'test-issue']
        if any(label in issue_labels for label in human_classification_labels):
            return False
        
        # Don't process if already being handled
        handling_labels = ['Under Investigation', 'fixing', 'resolution/fix-released']
        if any(label in issue_labels for label in handling_labels):
            return False
            
        return True
