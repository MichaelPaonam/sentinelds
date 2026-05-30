import os
from google import genai
from google.genai import types

def test_vertex_ai_connection():
    # 1. Grab the project ID from the environment
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") #optionally, you can set a default project here if you want
    location_id = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-south1")  # Default to asia-south1 if not set
    
    if not project_id:
        print("❌ Error: GOOGLE_CLOUD_PROJECT environment variable is not set.")
        print("Please run: export GOOGLE_CLOUD_PROJECT='your-project-id'")
        return

    print(f"🔄 Initializing GenAI client for project: {project_id}...")
    
    try:
        # 2. Initialize the client targeting Vertex AI
        # The client automatically uses your local Application Default Credentials (ADC)
        # client = genai.Client(vertexai=True, project=project_id, location=location_id)

        # values from .env will automatically configure the client for Vertex AI 
        # if GOOGLE_GENAI_USE_VERTEXAI is set to "true"
        client = genai.Client() 
        
        print("🚀 Sending smoke test prompt to gemini-2.5-flash...")
        
        # 3. Execute a single, low-latency call
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Respond with exactly three words: "Connection is successful."',
        )
        
        # 4. Print the result
        print("\n--- Vertex AI Response ---")
        print(response.text.strip())
        print("--------------------------\n")
        print("✅ Success! The LLM path is fully verified. You are ready to build agents.")

    except Exception as e:
        print(f"\n❌ Connection failed.")
        print(f"Error details: {e}")
        print("\nTroubleshooting Checklist:")
        print("1. Did you run 'gcloud auth application-default login'?")
        print("2. Is the AI Platform API (aiplatform.googleapis.com) enabled?")
        print("3. Does your account have 'Vertex AI User' permissions on this project?")

if __name__ == "__main__":
    test_vertex_ai_connection()