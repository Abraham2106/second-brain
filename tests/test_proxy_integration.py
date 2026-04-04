import sys
from src.core.agent_protocols import AI_Agent
from src.core.errors import GeminiRequestFailed

def main():
    agent = AI_Agent(name="TestAgent", system_prompt="You are a helpful assistant.", require_json=False)
    print("Agent created. Executing prompt...")
    try:
        response = agent.execute("test-task-1", "Hello! Who are you?")
        print("\n=== RESPONSE ===")
        print(response)
        print("================\nSuccess!")
    except GeminiRequestFailed as e:
        print(f"Failed with proxy error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
