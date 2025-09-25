import socket
from langchain_community.llms import Ollama
from langchain_google_genai import ChatGoogleGenerativeAI

def is_connected(host="8.8.8.8", port=53, timeout=3) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False

def get_llm():
    if is_connected():
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            temperature=0
        )
    else:
        print("❌ Offline: Using local Ollama model")
        return Ollama(model="stablelm2:1.1b")

llm = get_llm()