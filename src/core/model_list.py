"""Helper script to list available Gemini foundation models.

Queries the Google GenAI API to fetch and display model identifiers
and their supported actions.
"""

from dotenv import load_dotenv
from google import genai

# Load environment variables from .env file
load_dotenv()

# Ensure your local authentication or application credentials match your GCP project
# We explicitly set vertexai=True to use Google Cloud Application Default Credentials (ADC)
client = genai.Client(vertexai=True)

if __name__ == "__main__":
    print("Listing accessible Gemini foundation model identifiers:")
    for model in client.models.list():
        print(f"-> Model ID: {model.name} (Supported Actions: {model.supported_actions})")
