import socket
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.llms import Ollama

def is_connected(host="8.8.8.8", port=53, timeout=3) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False



def get_llm():
    if is_connected():
        print("✅ Online: Using Google Gemini model")
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",   # Gemini 1.5 Pro → "gemini-1.5-pro-latest"
            temperature=0
        )
    else:
        print("❌ Offline: Using local Ollama model")
        return Ollama(model="llama2")

   

llm = get_llm()

prompt = "Explain quantum computing in simple terms."
response = llm.invoke(prompt)
print("\nAssistant:", response.content if hasattr(response, "content") else response)

