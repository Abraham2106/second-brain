from src.config import get_settings


def main() -> None:
    settings = get_settings()
    keys = settings.gemini_api_keys
    models = settings.gemini_models

    print("Gemini key/model balancer config")
    print(f"- keys detected: {len(keys)}")
    if keys:
        lens = [len(k) for k in keys]
        print(f"- key lengths: {lens}")
    print(f"- models: {models}")


if __name__ == "__main__":
    main()
