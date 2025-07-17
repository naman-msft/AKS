import os
import json
import requests
from typing import Dict, List, Optional
from openai import AzureOpenAI
import re
import urllib.parse
from urllib.parse import quote

class WikiAssistant:
    def __init__(self):
        """Initialize with existing vector store and assistant"""
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-12-01-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        self.deployment_name = 'gpt-4'
        
        # Load existing vector store and assistant IDs
        self.vector_store_id = self._load_resource_id("vector_store_id.json")
        self.assistant_id = self._load_resource_id("assistant_id.json")
        
        # Load URL mapping
        self.url_mapping = {}
        if os.path.exists('wiki_url_mapping.json'):
            try:
                with open('wiki_url_mapping.json', 'r') as f:
                    raw_mapping = json.load(f)
                    
                    # Clean URLs from markdown format
                    for filename, url in raw_mapping.items():
                        if url.startswith('[') and '](' in url and url.endswith(')'):
                            # Extract URL from markdown format [text](url)
                            start = url.find('](') + 2
                            end = url.rfind(')')
                            cleaned_url = url[start:end]
                            self.url_mapping[filename] = cleaned_url
                        else:
                            self.url_mapping[filename] = url
                    
                    print(f"✓ Loaded and cleaned URL mapping for {len(self.url_mapping)} files")
            except Exception as e:
                print(f"✗ Error loading URL mapping: {e}")
        else:
            print("⚠️  No URL mapping file found")
        
        if not self.vector_store_id or not self.assistant_id:
            raise ValueError("Vector store and assistant must be set up first")
    def _load_resource_id(self, filename: str) -> Optional[str]:
        """Load resource ID from file"""
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                data = json.load(f)
                return data.get(filename.replace('.json', ''))
        return None
    
    def _validate_wiki_url(self, url: str, timeout: int = 5) -> bool:
        """Validate if a wiki URL is accessible"""
        # For Azure DevOps wiki URLs, they require authentication
        # HTTP 401 means the URL is valid but requires auth
        # HTTP 404 means the URL structure might be wrong
        if "dev.azure.com" in url and "_wiki/wikis" in url:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
                
                # For ADO wiki URLs:
                # - 401 = Valid URL but requires authentication (GOOD)
                # - 404 = Invalid URL structure (BAD)
                # - 2xx/3xx = Public access (GOOD)
                if response.status_code == 401:
                    return True  # URL is valid, just needs auth
                elif response.status_code == 404:
                    return False  # URL structure is wrong
                else:
                    return response.status_code < 400
                    
            except Exception as e:
                print(f"URL validation failed for {url}: {e}")
                return False
        
        # For other URLs, use normal validation
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
            return response.status_code < 400
            
        except Exception as e:
            print(f"URL validation failed for {url}: {e}")
            return False
    
    def _construct_wiki_url(self, file_name: str) -> str:
        """Get wiki URL from mapping or construct fallback"""
        # First check if we have the URL in our mapping (already cleaned)
        if file_name in self.url_mapping:
            return self.url_mapping[file_name]
        
        # If not found, try without .md extension
        base_name = file_name.replace('.md', '')
        for stored_name, url in self.url_mapping.items():
            if stored_name.replace('.md', '') == base_name:
                return url
        
        # Last resort: construct a basic URL
        print(f"⚠️  Warning: No URL mapping found for {file_name}")
        clean_name = file_name.replace('.md', '')
        wiki_path = f"/AKS/{clean_name}"
        encoded_path = urllib.parse.quote(wiki_path, safe='/')
        
        return f"https://dev.azure.com/msazure/CloudNativeCompute/_wiki/wikis/CloudNativeCompute.wiki/?pagePath={encoded_path}"
    # def _process_citations(self, message_content: str, annotations: List) -> str:
    #     """Process citations with link validation"""
    #     if not annotations:
    #         return message_content
        
    #     valid_citations = []
    #     invalid_count = 0
        
    #     # Remove inline citation markers from the message
    #     message_content = re.sub(r'【\d+:\d+†[^】]+】', '', message_content)
        
    #     for index, annotation in enumerate(annotations):
    #         if hasattr(annotation, "file_citation"):
    #             file_citation = annotation.file_citation
                
    #             try:
    #                 cited_file = self.client.files.retrieve(file_citation.file_id)
    #                 file_name = cited_file.filename
    #                 display_name = file_name.replace('.md', '')
                    
    #                 # Try to get the URL from file content first, then construct
    #                 wiki_url = self._construct_wiki_url(file_name)
                    
    #                 # Validate the URL
    #                 if self._validate_wiki_url(wiki_url):
    #                     valid_citations.append(f"[{len(valid_citations) + 1}] [{display_name}]({wiki_url})")
    #                 else:
    #                     invalid_count += 1
    #                     print(f"Invalid wiki URL skipped: {wiki_url}")
                        
    #             except Exception as e:
    #                 print(f"Error processing citation {index}: {e}")
    #                 invalid_count += 1
        
    #     # Add valid citations to message
    #     if valid_citations:
    #         message_content += "\n\n### 📚 Documentation References:\n" + "\n".join(valid_citations)
            
    #         if invalid_count > 0:
    #             message_content += f"\n\n*Note: {invalid_count} additional reference(s) were found but the links could not be validated.*"
    #     elif invalid_count > 0:
    #         message_content += f"\n\n*Note: {invalid_count} documentation reference(s) were found but could not be validated for accessibility.*"
        
    #     return message_content

    def _process_citations(self, message_content: str, annotations: List) -> str:
        """Process citations with link validation (internal links hidden for public repo)"""
        if not annotations:
            return message_content
        
        valid_citations = []
        invalid_count = 0
        
        # Remove inline citation markers from the message
        message_content = re.sub(r'【\d+:\d+†[^】]+】', '', message_content)
        
        for index, annotation in enumerate(annotations):
            if hasattr(annotation, "file_citation"):
                file_citation = annotation.file_citation
                
                try:
                    cited_file = self.client.files.retrieve(file_citation.file_id)
                    file_name = cited_file.filename
                    display_name = file_name.replace('.md', '')
                    
                    # Get the URL from mapping (for internal functionality)
                    wiki_url = self._construct_wiki_url(file_name)
                    
                    # Validate the URL (keeping validation logic)
                    if self._validate_wiki_url(wiki_url):
                        # For public repo: Show document names without internal links
                        valid_citations.append(f"[{len(valid_citations) + 1}] {display_name}")
                        
                        # For internal use: Uncomment the line below to show full links
                        # valid_citations.append(f"[{len(valid_citations) + 1}] [{display_name}]({wiki_url})")
                    else:
                        invalid_count += 1
                        print(f"Invalid wiki URL skipped: {wiki_url}")
                        
                except Exception as e:
                    print(f"Error processing citation {index}: {e}")
                    invalid_count += 1
        
        # Add valid citations to message
        if valid_citations:
            message_content += "\n\n### 📚 Documentation References:\n" + "\n".join(valid_citations)
            
            if invalid_count > 0:
                message_content += f"\n\n*Note: {invalid_count} additional reference(s) were found but could not be validated.*"
        elif invalid_count > 0:
            message_content += f"\n\n*Note: {invalid_count} documentation reference(s) were found but could not be validated for accessibility.*"
        
        return message_content

    def search_and_answer(self, issue_title: str, issue_body: str) -> Dict:
        """Search wiki for relevant info and generate response"""
        
        # First, always generate an AI response based on the issue
        ai_prompt = f"""
    As an Azure Kubernetes Service (AKS) expert, provide helpful guidance for this issue:

    Issue Title: {issue_title}
    Issue Description: {issue_body}

    Provide:
    1. Root cause analysis - What's likely causing this issue
    2. Immediate troubleshooting steps - What to check/try first
    3. Potential solutions - Specific fixes with commands/configurations
    4. Best practices - How to prevent this in the future

    Be technical, specific, and include actual commands or configurations where relevant.
    """
        
        base_response = ""
        try:
            # Generate AI response first
            ai_response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an Azure Kubernetes Service (AKS) expert. Provide detailed, technical troubleshooting guidance with specific commands and configurations."},
                    {"role": "user", "content": ai_prompt}
                ],
                max_tokens=1500
            )
            
            base_response = ai_response.choices[0].message.content
            
        except Exception as e:
            print(f"Error generating AI response: {e}")
            base_response = "I encountered an error generating a response. Please ensure your issue includes specific error messages and cluster configuration details."
        
        # Now try to enhance with wiki search
        wiki_response = ""
        found_docs = False
        citations_count = 0
        
        try:
            # Create a thread for wiki search
            thread = self.client.beta.threads.create(
                tool_resources={
                    "file_search": {
                        "vector_store_ids": [self.vector_store_id]
                    }
                }
            )
            
            # Add the issue as a message
            self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=f"""Find relevant AKS documentation for this issue:
    Title: {issue_title}
    Body: {issue_body}

    Search for documentation about error messages, configurations, or features mentioned."""
            )
            
            # Run the assistant
            run = self.client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=self.assistant_id,
                instructions="Search the AKS documentation for relevant information. Focus on finding specific documentation pages that address the issue.",
                tools=[{"type": "file_search"}],
                tool_choice={"type": "file_search"}
            )
            
            if run.status == 'completed':
                messages = self.client.beta.threads.messages.list(thread_id=thread.id)
                
                for message in messages:
                    if message.role == "assistant":
                        for content in message.content:
                            if hasattr(content, 'text'):
                                annotations = getattr(content.text, 'annotations', [])
                                
                                if annotations:
                                    # Process citations
                                    wiki_response = self._process_citations("", annotations)
                                    citations_count = len([ann for ann in annotations if hasattr(ann, 'file_citation')])
                                    found_docs = citations_count > 0
                                break
                        break
                        
        except Exception as e:
            print(f"Wiki search error (non-critical): {e}")
        
        # Combine AI response with wiki citations
        final_response = base_response
        if wiki_response and "📚 Documentation References:" in wiki_response:
            final_response = base_response + "\n" + wiki_response
        
        return {
            "found_relevant_docs": found_docs,
            "response": final_response,
            "citations_count": citations_count,
            "has_valid_links": found_docs
        }