from typing import List, Dict, Optional, Tuple
from agents import Agent, Runner
import os
from pydantic import BaseModel
from .graph_manager import GraphManager, FileStatus, ChangeType, ComponentNode

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

                # Run the agent
                result = Runner.run_sync(self.agent, prompt)
                response_text = result.final_output

                # Parse the response
                summary = ""
                components = []

                if "SUMMARY:" in response_text:
                    summary = response_text.split("SUMMARY:")[1].split("COMPONENTS:")[0].strip()

                if "COMPONENTS:" in response_text:
                    components_section = response_text.split("COMPONENTS:")[1].split("IMPACT:")[0].strip()
                    current_component = {}

                    for line in components_section.split("\n"):
                        line = line.strip()
                        if not line:
                            if current_component:
                                components.append(current_component)
                                current_component = {}
                            continue

                        if line.startswith("- name:"):
                            if current_component:
                                components.append(current_component)
                            current_component = {"name": line[7:].strip()}
                        elif line.startswith("  type:"):
                            current_component["type"] = line[7:].strip()
                        elif line.startswith("  summary:"):
                            current_component["summary"] = line[10:].strip()
                        elif line.startswith("  dependencies:"):
                            current_component["dependencies"] = [d.strip() for d in line[15:].split(",")]
                        elif line.startswith("  dependents:"):
                            current_component["dependents"] = [d.strip() for d in line[12:].split(",")]

                    if current_component:
                        components.append(current_component)

                # Add components to the graph
                for comp in components:
                    change_type = ChangeType[comp["type"].upper()]
                    self.graph_manager.add_component(
                        comp["name"],
                        current_file,
                        change_type
                    )

                    # Add dependencies
                    for dep in comp.get("dependencies", []):
                        # Try to find the dependency in other components
                        for other_comp in self.graph_manager.component_nodes.values():
                            if other_comp.name == dep:
                                self.graph_manager.add_component_dependency(
                                    f"{current_file}::{comp['name']}",
                                    f"{other_comp.file_path}::{other_comp.name}"
                                )

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