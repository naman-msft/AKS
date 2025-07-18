import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.issue_classifier import IssueClassifier

def test_ai_area_detection():
    """Test AI-powered area label detection"""
    
    test_cases = [
        {
            "id": 2001,
            "title": "Container insights dashboard not showing metrics",
            "body": "I'm not seeing any Prometheus metrics in the Container Insights dashboard. The Grafana charts are empty and log analytics workspace shows no data.",
            "author": "user1",
            "created_at": "2024-01-01T00:00:00Z",
            "expected_areas": ["addon/container-insights"]
        },
        {
            "id": 2002,
            "title": "Windows pods crashing on startup",
            "body": "Windows Server 2022 containers are failing to start. Getting exit code 1 errors. This happens on all Windows node pools in our cluster.",
            "author": "user2",
            "created_at": "2024-01-01T00:00:00Z",
            "expected_areas": ["windows"]
        },
        {
            "id": 2003,
            "title": "PVC mount failure with Azure Disk CSI",
            "body": "Persistent Volume Claims using Azure Disk are failing to mount. The CSI driver shows errors and pods are stuck in pending state.",
            "author": "user3",
            "created_at": "2024-01-01T00:00:00Z",
            "expected_areas": ["storage"]
        },
        {
            "id": 2004,
            "title": "NGINX ingress controller not routing traffic",
            "body": "The app routing addon with NGINX ingress controller is not working. Traffic is not being routed to backend services.",
            "author": "user4",
            "created_at": "2024-01-01T00:00:00Z",
            "expected_areas": ["addon/app-routing"]
        }
    ]
    
    print("🤖 TESTING AI-POWERED AREA LABEL DETECTION")
    print("=" * 60)
    
    # Force mock mode to avoid API calls
    os.environ['USE_MOCK_API'] = 'true'
    
    # Initialize classifier in mock mode
    classifier = IssueClassifier(
        config_path=".github/triage-config.json",
        azure_endpoint="mock",
        azure_key="mock-api-key",
        deployment_name="mock"
    )
    
    passed = 0
    total = len(test_cases)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🔍 Test {i}/{total}: {test_case['title']}")
        print(f"Body: {test_case['body'][:100]}...")
        
        try:
            result = classifier.classify_issue(test_case)
            
            print(f"📊 Classification: {result.classification} (confidence: {result.confidence:.2f})")
            print(f"🏷️  All labels: {result.suggested_labels}")
            
            # Extract area labels
            area_labels = [label for label in result.suggested_labels if 
                          label.startswith('addon/') or label.startswith('azure/') or 
                          label.startswith('extension/') or label.startswith('upstream/') or 
                          label.startswith('client/') or 
                          label in ['Security', 'networking', 'storage', 'windows', 'upgrade', 'docs', 
                                   'fleet', 'keda', 'nodepools', 'resiliency', 'Scale and Performance', 
                                   'Cilium', 'mesh', 'service-mesh', 'AzGov', 'AzChina', 
                                   'app-gateway-for-containers', 'advanced-container-networking-services', 
                                   'pod-identity', 'control-plane']]
            
            print(f"🎯 AI-detected area labels: {area_labels}")
            
            # Check if we got expected areas
            expected = test_case.get('expected_areas', [])
            found_expected = any(exp in area_labels for exp in expected)
            
            if found_expected:
                print(f"✅ PASS - Found expected area(s): {expected}")
                passed += 1
            else:
                print(f"❌ FAIL - Expected: {expected}, Got: {area_labels}")
            
            # Show what assignments would be triggered
            if area_labels:
                print(f"🔔 Will trigger auto-assignment for: {', '.join(area_labels)}")
                
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
    
    print(f"\n📊 FINAL RESULTS: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    return passed == total

if __name__ == "__main__":
    success = test_ai_area_detection()
    sys.exit(0 if success else 1)