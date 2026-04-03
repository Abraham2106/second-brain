from dotenv import load_dotenv

from src.gemini_balancer import (
    load_gemini_api_keys_from_env,
    load_gemini_models_from_env,
)
from src.base_agent import GEMINI_MODELS


def main() -> None:
    load_dotenv()

    keys = load_gemini_api_keys_from_env()
    models = load_gemini_models_from_env(GEMINI_MODELS)

    print("Gemini key/model balancer config")
    print(f"- keys detected: {len(keys)}")
    if keys:
        lens = [len(k) for k in keys]
        print(f"- key lengths: {lens}")
    print(f"- models: {models}")


if __name__ == "__main__":
    main()

