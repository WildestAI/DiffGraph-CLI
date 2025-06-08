# 📅 Roadmap: Modular Multi-Agent Architecture for diffgraph-ai

This roadmap introduces a modular re-architecture of `diffgraph-ai`, aimed at improving the accuracy, extensibility, and quality of visual diff representations. The goal is to break up the existing monolithic agent prompt into smaller, specialized AI agents using the OpenAI Agents SDK.

Each step is:

* ✅ Independently testable
* 🔁 Minimal, logical step in the pipeline
* 📗 Documented with clarity for even junior developers or AI assistants to follow

---

## ✅ Step 1: Introduce Component-Level Visualization

### 🌟 Objective:

Update the `GraphManager` and Mermaid generation to render function- and class-level nodes instead of only file-level nodes.

### 🔹 Definition of Done:

The output HTML graph should show component nodes (e.g., `validateUser()`, `AuthService`) with their change type (added/modified/deleted).

### ⚡ Implementation Plan:

* Update `GraphManager.add_component` to always record components
* Modify `get_mermaid_diagram()` to include and render component-level nodes with styles
* Use stub data if needed (before real extraction logic works)

### 🔧 Implementation Details:

* Use unique node IDs: `file_path::component_name`
* Use the `ChangeType` color scheme already defined
* Show 1–2 lines of the component summary (if available)
* Link dependencies using edges (even hardcoded for now)

### 📌 Status: `Not Started`

---

## ✅ Step 2: Split Agent Prompts into Two Specialized Roles

### 🌟 Objective:

Replace the monolithic analysis prompt with two focused prompts:

1. **Component Extractor**
2. **Dependency Mapper**

### 🔹 Definition of Done:

You should be able to call each of these prompts independently and get JSON output conforming to a shared schema.

### ⚡ Implementation Plan:

* Create prompt templates (can live as Python strings or YAML files)
* Use `openai.ChatCompletion.create` to run each prompt manually first
* Define a shared `Component` schema with:

  * `name`, `type`, `summary`, `dependencies`, `dependents`, `file_path`, `change_type`

### 🔧 Implementation Details:

* Component Extractor receives: file path + content + change type
* Dependency Mapper receives: file path + list of components + code snippets
* Each tool returns JSON with a list of `Component` objects
* Validate that outputs can round-trip through `pydantic.BaseModel`

### 📌 Status: `Not Started`

---

## ✅ Step 3: Add Chunking System for Large Files

### 🌟 Objective:

Break large files into chunks so component extraction doesn’t fail due to context limits.

### 🔹 Definition of Done:

The system should:

* Automatically detect long files (>1000 lines or >10KB)
* Split by top-level class or function boundaries
* Pass each chunk individually to the Extractor agent

### ⚡ Implementation Plan:

* Use `tree-sitter` or regex to identify safe split points
* Assign each chunk a metadata block:

  * `chunk_id`, `start_line`, `end_line`, `file_path`, `text`
* Feed each chunk separately into agent and recombine component outputs

### 🔧 Implementation Details:

* Store `ChunkResult` structs with raw outputs + parsed `Component` list
* Keep a map of chunk → original file for traceability
* If any chunk fails, include fallback: "Chunk X could not be parsed."

### 📌 Status: `Not Started`

---

## ✅ Step 4: Set Up OpenAI Agents SDK Planner and Tools

### 🌟 Objective:

Create an orchestrator agent using the OpenAI Agents SDK that delegates to tools:

* `extract_components`
* `map_dependencies`
* `visualize_graph`

### 🔹 Definition of Done:

A single `Runner.run()` call should:

* Take the file list
* Call tools in correct order
* Generate a final graph and return it

### ⚡ Implementation Plan:

* Define 3 `Tool` subclasses
* Define their input/output JSON schemas
* Register these tools inside a `Planner` agent

### 🔧 Implementation Details:

* Use [`openai_agents.Tool`](https://openai.github.io/openai-agents-python/agents/#tools) class
* Each tool’s `call()` should be fully stateless and log input/output
* Store intermediate results in a `Workspace` or memory dict
* Use the built-in `Planner` or implement a `ToolPicker`

### 📌 Status: `Not Started`

---

## ✅ Step 5: Refactor Agent-Calling Logic in `ai_analysis.py`

### 🌟 Objective:

Replace direct prompt + parsing logic with calls to the OpenAI Agents SDK planner + tools.

### 🔹 Definition of Done:

`CodeAnalysisAgent.analyze_changes()` should:

* Initialize planner
* Submit file info + diffs to planner
* Collect final graph (or summary)

### ⚡ Implementation Plan:

* Replace `_run_agent_analysis` with SDK planner call
* Move all hardcoded prompt strings into reusable tools
* Add detailed logging so developers can trace step-by-step agent execution

### 🔧 Implementation Details:

* Prepare `ToolContext` or `ToolMemory` between agent steps if needed
* Use JSON logs for prompt/output snapshots to aid debugging
* Ensure fallback mode (manual single-agent) works with `--legacy` flag

### 📌 Status: `Not Started`

---

## ✅ Step 6: Plan for Future Multi-LLM Abstraction

### 🌟 Objective:

Lay the foundation for future support of Anthropic, Perplexity, Google Gemini, and OSS models.

### 🔹 Definition of Done:

Abstract out all LLM calls behind an `LLMProvider` interface.

### ⚡ Implementation Plan:

* Create `providers/` module
* Start with `OpenAIProvider` (wraps OpenAI SDK + Agents SDK)
* Define common interface: `.chat()`, `.tool_call()`, `.get_capabilities()`

### 🔧 Implementation Details:

* Use Python `ABC` or `Protocol`
* Later: add `AnthropicProvider`, `OllamaProvider`, etc.
* Allow tool definitions to work with different backends based on config or CLI flag

### 📌 Status: `Not Started`

---

## 🏁 Final Deliverables Checklist

* [ ] Component-level Mermaid output
* [ ] Modular tool + planner agent pipeline
* [ ] Chunked file handling with metadata
* [ ] JSON-based schemas and round-trippable outputs
* [ ] SDK-based execution with full logging
* [ ] Abstracted backend for future multi-LLM provider support
