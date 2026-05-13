from google.adk import Agent
from google.adk.tools.google_search_tool import google_search
from dotenv import load_dotenv
import os

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description="""an agent whose job it is to perform Google search queries and answer questions about the results.""",
    instruction="""You are an agent whose job is to perform Google search queries and answer questions about the results.
""",
    tools=[google_search],
)