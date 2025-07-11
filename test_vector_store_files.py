import os
import json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

# Initialize client
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-12-01-preview",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# Load vector store ID
with open('vector_store_id.json', 'r') as f:
    data = json.load(f)
    vector_store_id = data['vector_store_id']

print(f"Vector Store ID: {vector_store_id}")

# List files in vector store
vector_store_files = client.beta.vector_stores.files.list(
    vector_store_id=vector_store_id
)

print(f"\nFiles in vector store:")
for i, file in enumerate(vector_store_files.data[:5]):  # First 5 files
    print(f"{i+1}. File ID: {file.id}")
    print(f"   Status: {file.status}")
    
    # Try to get file details
    try:
        file_obj = client.files.retrieve(file.id)
        print(f"   Filename: {file_obj.filename}")
        print(f"   Purpose: {file_obj.purpose}")
        
        # Try to get file content
        try:
            content = client.files.content(file.id)
            content_text = content.read().decode('utf-8')
            first_line = content_text.split('\n')[0]
            print(f"   First line: {first_line[:100]}...")
            print(f"   ✓ Can read content!")
        except Exception as e:
            print(f"   ✗ Cannot read content: {e}")
            
    except Exception as e:
        print(f"   Error retrieving file: {e}")
    
    print()

# Try alternative methods
print("\nTrying alternative access methods...")

# Method 1: Try through vector store retrieve
try:
    vector_store = client.beta.vector_stores.retrieve(vector_store_id)
    print(f"Vector store name: {vector_store.name}")
    print(f"File counts: {vector_store.file_counts}")
except Exception as e:
    print(f"Error: {e}")

# Method 2: Try beta files API
if vector_store_files.data:
    test_file_id = vector_store_files.data[0].id
    print(f"\nTesting with file ID: {test_file_id}")
    
    # Try different approaches
    approaches = [
        ("files.content", lambda: client.files.content(test_file_id)),
        ("files.retrieve", lambda: client.files.retrieve(test_file_id)),
        ("beta.files.content", lambda: client.beta.files.content(test_file_id)) if hasattr(client.beta, 'files') else None,
    ]
    
    for name, func in approaches:
        if func:
            try:
                result = func()
                print(f"✓ {name} worked!")
                if hasattr(result, 'read'):
                    print(f"  Content preview: {result.read(100)}...")
            except Exception as e:
                print(f"✗ {name} failed: {e}")

