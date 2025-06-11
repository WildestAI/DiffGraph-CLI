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

class ComponentAnalysis(BaseModel):
    """Model representing a single component's analysis."""
    name: str
    component_type: str  # container (class/interface/trait/module), function, method, etc.
    change_type: str    # added, deleted, modified
    summary: str
    parent: Optional[str] = None  # name of the parent component if this is a nested component
    dependencies: List[str] = []
    dependents: List[str] = []
    nested_components: List[str] = []  # names of components that are nested within this one

class CodeChangeAnalysis(BaseModel):
    """Model representing the analysis of code changes from the LLM."""
    summary: str
    components: List[ComponentAnalysis]
    impact: str

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
            2. For each component that was changed, identify:
               - Its name
               - Its type (container/function/method)
               - How it was changed (added, deleted, or modified)
               - Its parent component (if it's nested within another component)
               - Its dependencies (what it uses)
               - Its dependents (what uses it)
               - Any nested components within it (if it's a container)

            Important guidelines:
            - A 'container' is any component that can contain other components (classes, interfaces, traits, modules, namespaces)
            - A 'function' is any standalone function or procedure
            - A 'method' is any function that belongs to a container
            - Always include both container-level and nested component changes
            - For nested components, specify their parent container
            - For containers, list any nested components that were changed
            - Dependencies can be to both container-level and nested components
            - If a method/function is changed, it should be listed as a separate component with its parent specified

            3. Generate a clear summary of the changes

            Note: For each component, you must specify:
            - component_type: what kind of component it is (container/function/method)
            - change_type: how it was changed (added, deleted, modified)
            - parent: the name of its parent component if it's nested (e.g., a method within a class)
            - nested_components: list of any components nested within this one (if it's a container)""",
            model="gpt-4o",
            output_type=CodeChangeAnalysis
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
                response_data = self._run_agent_analysis(prompt)
                print("--------------------------------")
                print(response_data)
                print("--------------------------------")
                summary = response_data.summary
                components = response_data.components

                # Add components to the graph
                for comp in components:
                    try:
                        change_type = ChangeType[comp.change_type.upper()]
                        self.graph_manager.add_component(
                            comp.name,
                            current_file,
                            change_type,
                            component_type=comp.component_type,
                            parent=comp.parent,
                            summary=comp.summary,
                            dependencies=comp.dependencies,
                            dependents=comp.dependents
                        )

                        # Add dependencies
                        for dep in comp.dependencies:
                            if not dep:  # Skip empty dependencies
                                continue
                            # Try to find the dependency in other components
                            for other_comp in self.graph_manager.component_nodes.values():
                                if (dep.lower() in other_comp.name.lower() or
                                    other_comp.name.lower() in dep.lower()):
                                    self.graph_manager.add_component_dependency(
                                        f"{current_file}::{comp.name}",
                                        f"{other_comp.file_path}::{other_comp.name}"
                                    )

                        # Add dependents
                        for dep in comp.dependents:
                            if not dep:  # Skip empty dependents
                                continue
                            # Try to find the dependent in other components
                            for other_comp in self.graph_manager.component_nodes.values():
                                if (dep.lower() in other_comp.name.lower() or
                                    other_comp.name.lower() in dep.lower()):
                                    self.graph_manager.add_component_dependency(
                                        f"{other_comp.file_path}::{other_comp.name}",
                                        f"{current_file}::{comp.name}"
                                    )
                    except Exception as e:
                        print(f"Error processing component {comp.name}: {str(e)}")
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