from google import genai

# Ensure your local authentication or application credentials match your GCP project
client = genai.Client()

if __name__ == "__main__":
    print("Listing accessible Gemini foundation model identifiers:")
    for model in client.models.list():
        print(f"-> Model ID: {model.name} (Supported Actions: {model.supported_actions})")
