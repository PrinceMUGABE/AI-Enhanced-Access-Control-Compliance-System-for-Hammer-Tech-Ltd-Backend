# list_models.py
import google.genai as genai

API_KEY = "AIzaSyDO6B57aYqmGrBc3NDto42JTWaeoVXi9e0"

try:
    client = genai.Client(api_key=API_KEY)
    
    # List available models
    models = client.models.list()
    
    print("✅ Available Models:")
    for model in models:
        print(f"- {model.name}")
        print(f"  Supported methods: {model.supported_generation_methods}")
        print()
        
except Exception as e:
    print(f"❌ Error: {e}")