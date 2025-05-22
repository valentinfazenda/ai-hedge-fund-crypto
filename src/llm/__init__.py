import os
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI


openai_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-mini",  # or "gpt-4" if you have access
    timeout=30,           # timeout in seconds (set to your desired limit)
    max_retries=3
)

json_parser = JsonOutputParser()

__all__ = ["openai_llm", "json_parser"]