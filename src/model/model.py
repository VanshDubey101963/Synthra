import socket
# from langchain_community.llms import Ollama
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

def is_connected(host="8.8.8.8", port=53, timeout=3) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False

def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0
    )
    
llm = get_llm()