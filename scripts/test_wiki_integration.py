#!/usr/bin/env python3
"""
Test script for Wiki integration with issue triage
"""
import os
import sys
import json
import argparse
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.issue_classifier import IssueClassifier
from src.wiki_assistant import WikiAssistant

load_dotenv()

def test_wiki_assistant():
    """Test wiki assistant standalone"""
    print("Testing Wiki Assistant...")
    
    try:
        wiki = WikiAssistant()
        
        # Test with a sample issue
        result = wiki.search_and_answer(
            "AKS nodes failing to scale with error InvalidParameter",
            "When trying to scale my nodepool from 3 to 5 nodes, I get: Error: InvalidParameter"
        )
        
        print(f"✓ Wiki search completed")
        print(f"  Found docs: {result['found_relevant_docs']}")
        print(f"  Citations: {result['citations_count']}")
        print(f"  Valid links: {result['has_valid_links']}")
        print(f"\nResponse preview:")
        print(result['response'][:800] + "..." if len(result['response']) > 800 else result['response'])
        
        return True
    except Exception as e:
        print(f"✗ Wiki assistant test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_issue_classification(issue_title, issue_body):
    """Test full issue classification with wiki integration"""
    print(f"\nTesting Issue Classification...")
    
    try:
        classifier = IssueClassifier(
            config_path=".github/triage-config.json",
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
            azure_key=os.getenv('AZURE_OPENAI_KEY'),
            deployment_name=os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'gpt-4')
        )
        
        issue_data = {
            'id': 999,  # Test issue number
            'title': issue_title,
            'body': issue_body,
            'author': 'test-user',
            'created_at': '2024-01-01T00:00:00Z'
        }
        
        # Test classification
        result = classifier.classify_issue_enhanced(issue_data, [])
        
        print(f"✓ Classification: {result.classification} (confidence: {result.confidence:.2%})")
        print(f"✓ Area: {result.primary_area}")
        print(f"✓ Labels: {', '.join(result.suggested_labels)}")
        
        if result.wiki_response:
            print(f"✓ Wiki integration: Found {result.wiki_response['citations_count']} docs")
        else:
            print("✗ Wiki integration: No response")
            
        return result
        
    except Exception as e:
        print(f"✗ Classification test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def format_github_comment(result):
    """Format the result as it would appear in GitHub"""
    comment = "🤖 **AI Issue Analysis**\n\n"
    comment += f"**Classification**: {result.classification}\n"
    comment += f"**Confidence**: {result.confidence:.2%}\n"
    comment += f"**Area**: {result.primary_area}\n"
    
    if result.wiki_response and result.wiki_response.get('found_relevant_docs'):
        comment += "\n---\n\n"
        comment += "## 📖 Relevant Documentation Found\n\n"
        comment += result.wiki_response['response']
        comment += f"\n\n*Found {result.wiki_response['citations_count']} relevant documentation pages*"
    
    return comment

def main():
    parser = argparse.ArgumentParser(description='Test Wiki Integration')
    parser.add_argument('--issue-title', default="AKS nodes failing to scale with error InvalidParameter",
                        help='Issue title to test')
    parser.add_argument('--issue-body', default="When trying to scale my nodepool from 3 to 5 nodes, I get: Error: InvalidParameter - The value '5' is not valid for parameter 'maxCount'",
                        help='Issue body to test')
    parser.add_argument('--test-wiki-only', action='store_true',
                        help='Only test wiki assistant')
    args = parser.parse_args()
    
    print("=== AKS Issue Triage Wiki Integration Test ===\n")
    
    # Check environment
    required_vars = ['AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_KEY']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"✗ Missing environment variables: {', '.join(missing)}")
        return 1
    
    # Check for vector store files
    if not os.path.exists('vector_store_id.json') or not os.path.exists('assistant_id.json'):
        print("✗ Missing vector_store_id.json or assistant_id.json")
        print("  Copy these from your client-tools directory or run:")
        print("  cp ~/NamanCode/client-tools/vector_store_id.json .")
        print("  cp ~/NamanCode/client-tools/assistant_id.json .")
        return 1
    
    # Run tests
    if args.test_wiki_only:
        success = test_wiki_assistant()
    else:
        result = test_issue_classification(args.issue_title, args.issue_body)
        if result:
            print("\n=== GitHub Comment Preview ===")
            print(format_github_comment(result))
            success = True
        else:
            success = False
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())