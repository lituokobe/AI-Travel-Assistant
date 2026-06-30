from langchain_tavily import TavilySearch
from agent.config import TAVILY_API_KEY

web_search = TavilySearch(
    max_results=5,
    topic="general",
    include_answer=True,
    include_raw_content=False,
    tavily_api_key=TAVILY_API_KEY
)