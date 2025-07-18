import os
import json
from typing import Dict, List, Optional
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import MessageRole, BingGroundingTool
from azure.identity import DefaultAzureCredential

class WikiAssistant:
    def __init__(self):
        """Initialize with Azure AI Projects and Bing Grounding"""
        self.project_client = AIProjectClient(
            endpoint=os.environ["PROJECT_ENDPOINT"],
            credential=DefaultAzureCredential(),
        )
        self.model_deployment = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4.1")
        self.bing_connection_id = os.getenv("AZURE_BING_CONNECTION_ID")
        
        if not self.bing_connection_id:
            print("⚠️  AZURE_BING_CONNECTION_ID not configured - web search will be disabled")
        else:
            print(f"✅ Using Bing connection: {self.bing_connection_id}")
    
    def search_and_answer(self, issue_title: str, issue_body: str) -> Dict:
        """Search using Bing Grounding and generate answer with Azure AI Projects"""
        try:
            # Create instructions for the AKS assistant
            instructions = """You are an expert Azure Kubernetes Service (AKS) support assistant. 

When helping with AKS issues:
1. Search the web for current, relevant information about the specific problem
2. Provide concise, actionable solutions with specific commands/configurations
3. Include relevant links and citations from your search results
4. Focus on recent documentation and known solutions
5. Format your response in markdown for readability

If you cannot find specific information, provide general AKS troubleshooting guidance based on your knowledge."""

            with self.project_client:
                agents_client = self.project_client.agents
                
                # Create agent with or without Bing grounding
                if self.bing_connection_id:
                    # Initialize Bing grounding tool - exactly like the working script
                    bing = BingGroundingTool(connection_id=self.bing_connection_id)
                    
                    agent = agents_client.create_agent(
                        model=self.model_deployment,
                        name="aks-assistant",
                        instructions=instructions,
                        tools=bing.definitions,
                    )
                    print("🔍 Created agent WITH Bing grounding")
                else:
                    agent = agents_client.create_agent(
                        model=self.model_deployment,
                        name="aks-assistant",
                        instructions=instructions
                    )
                    print("⚠️  Created agent WITHOUT Bing grounding")
                
                # Create thread for communication
                thread = agents_client.threads.create()
                
                # Create user message with the issue
                user_query = f"""Help me with this AKS issue:

**Issue Title:** {issue_title}

**Issue Description:** {issue_body}

Please search for current information and provide a comprehensive solution."""

                message = agents_client.messages.create(
                    thread_id=thread.id,
                    role=MessageRole.USER,
                    content=user_query,
                )
                
                # Create and process agent run
                run = agents_client.runs.create_and_process(
                    thread_id=thread.id, 
                    agent_id=agent.id
                )
                
                print(f"Run finished with status: {run.status}")
                
                # Check if run was successful
                if run.status == "failed":
                    print(f"Run failed: {run.last_error}")
                    # Don't return fallback here, continue with the client open
                
                # Check run steps to see if Bing was used - FIXED: iterate directly, no len()
                used_bing_search = False
                run_steps = agents_client.run_steps.list(thread_id=thread.id, run_id=run.id)
                
                step_count = 0
                for step in run_steps:
                    step_count += 1
                    print(f"Step {step.get('id')} status: {step.get('status')}")
                    step_details = step.get("step_details", {})
                    tool_calls = step_details.get("tool_calls", [])
                    
                    if tool_calls:
                        print("  Tool calls:")
                        for call in tool_calls:
                            print(f"    Tool Call ID: {call.get('id')}")
                            print(f"    Type: {call.get('type')}")
                            
                            if call.get('type') == 'bing_grounding':
                                used_bing_search = True
                                bing_details = call.get("bing_grounding", {})
                                if bing_details:
                                    print(f"    Bing Grounding ID: {bing_details.get('requesturl')}")
                    print()  # Extra newline like the working script
                
                print(f"Found {step_count} run steps total")
                
                # Get the agent's response
                response_message = agents_client.messages.get_last_message_by_role(
                    thread_id=thread.id, 
                    role=MessageRole.AGENT
                )
                
                # Extract response text
                response_text = ""
                citations = []
                
                if response_message:
                    for text_message in response_message.text_messages:
                        response_text += text_message.text.value
                    
                    # Extract URL citations
                    for annotation in response_message.url_citation_annotations:
                        citations.append({
                            'title': annotation.url_citation.title,
                            'url': annotation.url_citation.url
                        })
                        print(f"Found citation: {annotation.url_citation.title}")
                
                # Clean up
                agents_client.delete_agent(agent.id)
                print("Deleted agent")
                
                return {
                    'found_relevant_docs': used_bing_search,
                    'response': response_text,
                    'citations_count': len(citations),
                    'search_results': citations,
                    'used_bing_grounding': used_bing_search
                }
                
        except Exception as e:
            print(f"Azure AI Projects search failed: {e}")
            import traceback
            traceback.print_exc()
            # Generate fallback with a fresh client since the with block may be closed
            return self._generate_fallback_response_fresh(issue_title, issue_body)
    
    def _generate_fallback_response_fresh(self, title: str, body: str) -> Dict:
        """Generate fallback response with a fresh client connection"""
        try:
            # Create a fresh client for fallback
            fresh_client = AIProjectClient(
                endpoint=os.environ["PROJECT_ENDPOINT"],
                credential=DefaultAzureCredential(),
            )
            
            instructions = """You are an Azure Kubernetes Service (AKS) expert. Provide detailed, technical troubleshooting guidance based on your knowledge."""
            
            with fresh_client:
                agents_client = fresh_client.agents
                
                # Create basic agent without tools
                agent = agents_client.create_agent(
                    model=self.model_deployment,
                    name="aks-fallback-assistant",
                    instructions=instructions
                )
                
                # Create thread and message
                thread = agents_client.threads.create()
                
                fallback_query = f"""As an Azure Kubernetes Service (AKS) expert, provide helpful guidance for this issue:

Issue Title: {title}
Issue Description: {body}

Provide:
1. Root cause analysis - What's likely causing this issue
2. Immediate troubleshooting steps - What to check/try first  
3. Potential solutions - Specific fixes with commands/configurations
4. Best practices - How to prevent this in the future

Be technical, specific, and include actual commands or configurations where relevant."""

                message = agents_client.messages.create(
                    thread_id=thread.id,
                    role=MessageRole.USER,
                    content=fallback_query,
                )
                
                # Process the run
                run = agents_client.runs.create_and_process(
                    thread_id=thread.id, 
                    agent_id=agent.id
                )
                
                # Get response
                response_message = agents_client.messages.get_last_message_by_role(
                    thread_id=thread.id, 
                    role=MessageRole.AGENT
                )
                
                response_text = ""
                if response_message:
                    for text_message in response_message.text_messages:
                        response_text += text_message.text.value
                
                # Clean up
                agents_client.delete_agent(agent.id)
                
                return {
                    'found_relevant_docs': False,
                    'response': response_text,
                    'citations_count': 0,
                    'used_bing_grounding': False
                }
                
        except Exception as e:
            print(f"Error generating fallback response: {e}")
            return {
                'found_relevant_docs': False,
                'response': "I encountered an error generating a response. Please ensure your issue includes specific error messages and cluster configuration details.",
                'citations_count': 0,
                'used_bing_grounding': False
            }
    
    def _generate_fallback_response(self, title: str, body: str) -> Dict:
        """Legacy fallback method - kept for compatibility"""
        return self._generate_fallback_response_fresh(title, body)
    
    def close(self):
        """Close the project client"""
        if hasattr(self.project_client, 'close'):
            self.project_client.close()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Search AKS docs with Bing Grounding via Azure AI Projects"
    )
    parser.add_argument("-t", "--title", required=True, help="Issue title")
    parser.add_argument("-b", "--body",  required=True, help="Issue description")
    args = parser.parse_args()

    assistant = WikiAssistant()
    result = assistant.search_and_answer(args.title, args.body)
    print("\n=== Answer ===\n")
    print(result["response"])
    
    if result.get("used_bing_grounding"):
        print(f"\n✅ Used Bing web search with {result['citations_count']} citations")
    else:
        print("\n⚠️  Fallback mode - no web search used")
    
    if result.get("search_results"):
        print("\n=== Sources ===")
        for i, citation in enumerate(result["search_results"], 1):
            print(f"{i}. [{citation['title']}]({citation['url']})")