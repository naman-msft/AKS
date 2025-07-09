import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from openai import AzureOpenAI

@dataclass
class ClassificationResult:
    classification: str
    confidence: float
    reasoning: str
    suggested_area: str
    missing_info: List[str]
    suggested_assignees: List[str]
    suggested_labels: List[str]
    suggested_response: str

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
    
    def classify_issue(self, issue: Dict) -> ClassificationResult:
        """Classify a single issue using AI"""
        
        # Create the classification prompt
        prompt = self._create_classification_prompt(issue)
        
        # Call Azure OpenAI API (or use a mock response for testing)
        if self.azure_key == "mock-api-key":
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
        
        return ClassificationResult(
            classification=classification,
            confidence=response['confidence'],
            reasoning=response['reasoning'],
            suggested_area=area,
            missing_info=response.get('missing_info', []),
            suggested_assignees=suggested_assignees,
            suggested_labels=suggested_labels,
            suggested_response=suggested_response
        )