import os
from openai import OpenAI
from dotenv import load_dotenv

_client = None

def get_open_ai_client():
    """
    Get or create a singleton instance of the OpenAI client.
    This ensures we only create one client instance across the application.
    """
    global _client
    if _client is None:
        load_dotenv()
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client