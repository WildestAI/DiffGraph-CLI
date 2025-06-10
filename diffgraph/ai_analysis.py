from typing import List, Dict, Optional, Tuple
from agents import Agent, Runner
import os
from pydantic import BaseModel
from .graph_manager import GraphManager, FileStatus, ChangeType, ComponentNode
import time
import random
import openai
import re

class FileChange(BaseModel):
    """Model representing a file change."""
    path: str
    status: str
    content: str

class DiffAnalysis(BaseModel):
    """Model representing the analysis of code changes."""
    summary: str
    mermaid_diagram: str

def exponential_backoff_retry(func):
    """Decorator to implement exponential backoff retry logic using API rate limit information."""
    def wrapper(*args, **kwargs):
        max_retries = 5
        base_delay = 1  # Start with 1 second
        max_delay = 60  # Maximum delay of 60 seconds

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except openai.RateLimitError as e:
                if attempt == max_retries - 1:  # Last attempt
                    raise  # Re-raise the exception if all retries failed

                # Try to get the retry delay from the error response
                try:
                    # The error response usually contains a 'retry_after' field
                    retry_after = getattr(e, 'retry_after', None)
                    if retry_after:
                        delay = float(retry_after)
                    else:
                        # Fallback to exponential backoff if retry_after is not available
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                except (ValueError, TypeError):
                    # If we can't parse the retry_after, fallback to exponential backoff
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)

                print(f"Rate limit hit. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            except Exception as e:
                raise  # Re-raise other exceptions immediately
    return wrapper

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
            1. Analyze the given code changes
            2. Identify all components (functions, classes, methods) that were:
               - Added (new code)
               - Deleted (removed code)
               - Modified (changed code)
            3. For each component, identify:
               - Its dependencies (what it uses)
               - Its dependents (what uses it)
            4. Generate a clear summary of the changes

            Format your response as:
            SUMMARY:
            [Your analysis summary]

            COMPONENTS:
            [List of components with their change type and summary]
            - name: [component name]
              type: [added/deleted/modified]
              summary: [brief description of changes]
              dependencies: [list of component names this depends on]
              dependents: [list of component names that depend on this]

            IMPACT:
            [Analysis of potential impact of these changes]""",
            model="gpt-4o"
        )

        self.graph_manager = GraphManager()

    def _determine_change_type(self, status: str) -> ChangeType:
        """Convert git status to ChangeType."""
        if status == "untracked":
            return ChangeType.ADDED
        elif status == "deleted":
            return ChangeType.DELETED
        else:
            return ChangeType.MODIFIED

    @exponential_backoff_retry
    def _run_agent_analysis(self, prompt: str) -> str:
        """Run the agent analysis with retry logic."""
        result = Runner.run_sync(self.agent, prompt)
        return result.final_output

    def analyze_changes(self, files_with_content: List[Dict[str, str]]) -> DiffAnalysis:
        """
        Analyze code changes using the OpenAI agent, processing files incrementally.

        Args:
            files_with_content: List of dictionaries containing file changes

        Returns:
            DiffAnalysis object containing summary and mermaid diagram
        """
        # Initialize the graph with all files
        for file_info in files_with_content:
            change_type = self._determine_change_type(file_info['status'])
            self.graph_manager.add_file(file_info['path'], change_type)

        # Process files in BFS order
        while True:
            current_file = self.graph_manager.get_next_file()
            if not current_file:
                break

            try:
                # Mark file as processing
                self.graph_manager.mark_processing(current_file)

                # Find the file content
                file_content = next(
                    (f['content'] for f in files_with_content if f['path'] == current_file),
                    None
                )

                if not file_content:
                    raise ValueError(f"Content not found for file: {current_file}")

                # Prepare the prompt for the agent
                prompt = f"Analyze the following code changes in {current_file}:\n\n"
                prompt += f"```\n{file_content}\n```\n\n"

                # Add context about already processed components
                processed_components = [
                    comp for comp in self.graph_manager.component_nodes.values()
                    if comp.file_path == current_file
                ]
                if processed_components:
                    prompt += "Already identified components in this file:\n"
                    for comp in processed_components:
                        prompt += f"- {comp.name}: {comp.summary}\n"

                # Run the agent with retry logic
                response_text = self._run_agent_analysis(prompt)

                print("--------------------------------")
                print(response_text)
                print("--------------------------------")
                # Parse the response
                summary = ""
                components = []

                if "SUMMARY:" in response_text:
                    summary = response_text.split("SUMMARY:")[1].split("COMPONENTS:")[0].strip()

                if "COMPONENTS:" in response_text:
                    components_section = response_text.split("COMPONENTS:")[1].split("IMPACT:")[0].strip()
                    current_component = {}
                    components = []  # Reset components list for each file

                    for line in components_section.split("\n"):
                        line = line.strip()
                        if not line:
                            if current_component and "name" in current_component:  # Only add if we have a name
                                components.append(current_component)
                                current_component = {}
                            continue

                        parts = line.split(":")
                        if len(parts) > 1:
                            field_name = re.sub(r'[^a-zA-Z0-9_]', '', parts[0].strip()).lower()
                            field_value = ":".join(parts[1:]).strip()
                            if field_name == "name":
                                if current_component and "name" in current_component:  # Only add if we have a name
                                    components.append(current_component)
                                current_component = {"name": field_value}
                            elif field_name == "type":
                                current_component["type"] = re.sub(r'[^a-zA-Z0-9_]', '', field_value.strip()).lower()
                            elif field_name == "summary":
                                current_component["summary"] = field_value
                            elif field_name == "dependencies":
                                current_component["dependencies"] = [d.strip() for d in field_value.split(",") if d.strip()]
                            elif field_name == "dependents":
                                current_component["dependents"] = [d.strip() for d in field_value.split(",") if d.strip()]

                    if current_component and "name" in current_component:  # Only add if we have a name
                        components.append(current_component)

                # Add components to the graph
                for comp in components:
                    if "name" not in comp or "type" not in comp:
                        print(f"Skipping invalid component: {comp}")
                        continue

                    try:
                        change_type = ChangeType[comp["type"].upper()]
                        self.graph_manager.add_component(
                            comp["name"],
                            current_file,
                            change_type,
                            summary=comp.get("summary"),
                            dependencies=comp.get("dependencies", []),
                            dependents=comp.get("dependents", [])
                        )

                        # Add dependencies
                        for dep in comp.get("dependencies", []):
                            if not dep:  # Skip empty dependencies
                                continue
                            # Try to find the dependency in other components
                            for other_comp in self.graph_manager.component_nodes.values():
                                if (dep.lower() in other_comp.name.lower() or
                                    other_comp.name.lower() in dep.lower()):
                                    self.graph_manager.add_component_dependency(
                                        f"{current_file}::{comp['name']}",
                                        f"{other_comp.file_path}::{other_comp.name}"
                                    )

                        # Add dependents
                        for dep in comp.get("dependents", []):
                            if not dep:  # Skip empty dependents
                                continue
                            # Try to find the dependent in other components
                            for other_comp in self.graph_manager.component_nodes.values():
                                if (dep.lower() in other_comp.name.lower() or
                                    other_comp.name.lower() in dep.lower()):
                                    self.graph_manager.add_component_dependency(
                                        f"{other_comp.file_path}::{other_comp.name}",
                                        f"{current_file}::{comp['name']}"
                                    )
                    except Exception as e:
                        print(f"Error processing component {comp.get('name', 'unknown')}: {str(e)}")
                        continue

                # Mark file as processed
                self.graph_manager.mark_processed(current_file, summary, components)

            except Exception as e:
                self.graph_manager.mark_error(current_file, str(e))

        # Generate the final Mermaid diagram
        mermaid_diagram = self.graph_manager.get_mermaid_diagram()

        # Generate overall summary
        overall_summary = "Analysis Summary:\n\n"
        for file_path, node in self.graph_manager.file_nodes.items():
            if node.status == FileStatus.PROCESSED:
                overall_summary += f"- {file_path}: {node.summary}\n"
            elif node.status == FileStatus.ERROR:
                overall_summary += f"- {file_path}: Error - {node.error}\n"

        return DiffAnalysis(
            summary=overall_summary,
            mermaid_diagram=mermaid_diagram
        )