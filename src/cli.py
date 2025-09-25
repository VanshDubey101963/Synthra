import time
import os
from src.speech.speech import speech_to_text
from src.agents.supervisor_agent.supervisor import create_orchestrator_with_agents
# === Function to read ASCII art from a file ===
def load_ascii_art(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "ASCII Art file not found.\n"

# === Main CLI Entry ===
def main():
    # Load and print the ASCII art
    ascii_art_path = os.path.join(os.path.dirname(__file__), "ascii_art.txt")
    ascii_art = load_ascii_art(ascii_art_path)
    print("\n\n\n\n"+ascii_art)
    
    print("\n\n\n\nStarting the CLI assistant...\n")
    
    # Infinite loop
    while True:
        try:
            print("🎙️ Listening for user input...")
            user_prompt = speech_to_text()
            
            print(f"User said: {user_prompt}\n\n")
            print("Passing input to Supervisor agent...\n\n")

            # Call the Supervisor agent with the user prompt
            agent_response = create_orchestrator_with_agents(user_prompt)

            print("Agent response / Intermediate steps:")
            print("--------------------------------------\n\n")
            print(agent_response)
            print("--------------------------------------\n\n\n\n")

            time.sleep(3)

        except KeyboardInterrupt:
            print("\nExiting the CLI. Goodbye!")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            continue

if __name__ == "__main__":
    main()
