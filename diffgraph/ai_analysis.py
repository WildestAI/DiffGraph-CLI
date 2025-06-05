from typing import List, Dict, Optional
from agents import Agent, Runner
import os
from pydantic import BaseModel

class FileChange(BaseModel):
    """Model representing a file change."""
    path: str
    status: str
    content: str

class DiffAnalysis(BaseModel):
    """Model representing the analysis of code changes."""
    summary: str
    mermaid_diagram: str

class CodeAnalysisAgent:
    """Agent for analyzing code changes using OpenAI's Agents SDK."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the agent with OpenAI API key."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")

        # Initialize the agent with specific instructions for code analysis
        self.agent = Agent(
            name="Code Analysis Agent",
            instructions="""You are an expert code analyzer. Your task is to:
            1. Analyze code changes and understand their implications
            2. Generate a clear summary of the changes
            3. Create a Mermaid diagram showing the relationships between changed components
            4. Focus on identifying potential impacts and dependencies

            Format your response as:
            SUMMARY:
            [Your analysis summary]

            DIAGRAM:
            ```mermaid
            [Your mermaid diagram]
            ```""",
            model="gpt-4o"
        )

    def analyze_changes(self, files_with_content: List[Dict[str, str]]) -> DiffAnalysis:
        """
        Analyze code changes using the OpenAI agent.

        Args:
            files_with_content: List of dictionaries containing file changes

        Returns:
            DiffAnalysis object containing summary and mermaid diagram
        """
        # Convert to FileChange objects for better type safety
        changes = [FileChange(**file_info) for file_info in files_with_content]

        # Prepare the prompt for the agent
        prompt = "Analyze the following code changes:\n\n"
        for change in changes:
            prompt += f"File: {change.path} (Status: {change.status})\n"
            prompt += "Content:\n"
            prompt += f"```\n{change.content}\n```\n\n"

        # Run the agent
        result = Runner.run_sync(self.agent, prompt)

        # Parse the response
        response_text = result.final_output

        # Extract summary and diagram
        summary = ""
        mermaid_diagram = ""

        if "SUMMARY:" in response_text:
            summary = response_text.split("SUMMARY:")[1].split("DIAGRAM:")[0].strip()

        if "DIAGRAM:" in response_text:
            diagram_section = response_text.split("DIAGRAM:")[1].strip()
            if "```mermaid" in diagram_section:
                mermaid_diagram = diagram_section.split("```mermaid")[1].split("```")[0].strip()

        return DiffAnalysis(
            summary=summary,
            mermaid_diagram=mermaid_diagram
        )