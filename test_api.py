import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ Error: No se encontró GEMINI_API_KEY en el archivo .env")
else:
    api_key = api_key.strip('"').strip("'")
    client = genai.Client(api_key=api_key)

    print(f"Checking models (using google-genai)...")
    try:
        # Probando una iteración simple y ver qué atributos tiene el primer objeto
        models = list(client.models.list())
        if models:
            first_model = models[0]
            print(f"Model keys: {dir(first_model)}")
            
            for m in models:
                # El nuevo SDK suele usar m.name
                print(f"Model: {m.name}")
    except Exception as e:
        print(f"Error: {e}")
