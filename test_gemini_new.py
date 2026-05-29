# test_gemini_new.py
import google.genai as genai

# Test with your API key
API_KEY = "AIzaSyDO6B57aYqmGrBc3NDto42JTWaeoVXi9e0"

try:
    client = genai.Client(api_key=API_KEY)
    
    response = client.models.generate_content(
        model="gemini-pro",
        contents="Hello! Who are you?"
    )
    
    print("✅ Success! New package works!")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"❌ Error: {e}")