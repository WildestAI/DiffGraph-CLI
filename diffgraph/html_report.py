import os
from pathlib import Path
from typing import NamedTuple

class AnalysisResult(NamedTuple):
    summary: str
    mermaid_diagram: str

def generate_html_report(analysis: AnalysisResult, output_path: str = "diffgraph.html") -> str:
    """
    Generate an HTML report with the analysis summary and Mermaid diagram.

    Args:
        analysis: AnalysisResult containing summary and mermaid diagram
        output_path: Path where the HTML file should be saved

    Returns:
        Path to the generated HTML file
    """
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DiffGraph Report</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/marked/11.1.1/marked.min.js"></script>
    <style>
        :root {{
            --bg-primary: #ffffff;
            --text-primary: #1a202c;
            --bg-secondary: #f8f9fa;
            --border-color: #e2e8f0;
        }}

        [data-theme="dark"] {{
            --bg-primary: #1a202c;
            --text-primary: #f7fafc;
            --bg-secondary: #2d3748;
            --border-color: #4a5568;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: var(--text-primary);
            background-color: var(--bg-primary);
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            transition: background-color 0.3s, color 0.3s;
        }}

        .mermaid {{
            background: var(--bg-secondary);
            padding: 1.5rem;
            border-radius: 0.75rem;
            margin: 1.5rem 0;
            border: 1px solid var(--border-color);
        }}

        .summary {{
            background: var(--bg-secondary);
            padding: 1.5rem;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
            border: 1px solid var(--border-color);
        }}

        h1 {{
            color: var(--text-primary);
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        h2 {{
            color: var(--text-primary);
            font-size: 1.8rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }}

        pre {{
            background: var(--bg-secondary);
            padding: 1rem;
            border-radius: 0.75rem;
            overflow-x: auto;
            border: 1px solid var(--border-color);
        }}

        code {{
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
        }}

        .theme-toggle {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            cursor: pointer;
            font-size: 0.875rem;
            transition: all 0.2s;
        }}

        .theme-toggle:hover {{
            background: var(--border-color);
        }}

        .markdown-content {{
            color: var(--text-primary);
        }}

        .markdown-content p {{
            margin-bottom: 1rem;
        }}

        .markdown-content ul {{
            list-style-type: disc;
            margin-left: 1.5rem;
            margin-bottom: 1rem;
        }}

        .markdown-content li {{
            margin-bottom: 0.5rem;
        }}

        .markdown-content code {{
            background: var(--bg-secondary);
            padding: 0.2rem 0.4rem;
            border-radius: 0.25rem;
            font-size: 0.875em;
        }}
    </style>
</head>
<body>
    <h1>
        DiffGraph Report
        <button class="theme-toggle" onclick="toggleTheme()">Toggle Dark Mode</button>
    </h1>

    <div class="summary">
        <h2>Analysis Summary</h2>
        <div class="markdown-content" id="summary-content">
            {summary}
        </div>
    </div>

    <div class="mermaid">
        {mermaid_diagram}
    </div>

    <script>
        // Initialize Mermaid
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true
            }}
        }});

        // Initialize syntax highlighting
        document.addEventListener('DOMContentLoaded', (event) => {{
            document.querySelectorAll('pre code').forEach((block) => {{
                hljs.highlightBlock(block);
            }});
        }});

        // Convert markdown to HTML
        document.addEventListener('DOMContentLoaded', (event) => {{
            const summaryContent = document.getElementById('summary-content');
            summaryContent.innerHTML = marked.parse(summaryContent.textContent);
        }});

        // Theme toggle functionality
        function toggleTheme() {{
            const body = document.body;
            const currentTheme = body.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            body.setAttribute('data-theme', newTheme);

            // Update Mermaid theme
            mermaid.initialize({{
                theme: newTheme === 'dark' ? 'dark' : 'default'
            }});

            // Re-render Mermaid diagrams
            document.querySelectorAll('.mermaid').forEach((el) => {{
                const content = el.textContent;
                el.textContent = content;
                mermaid.init(undefined, el);
            }});
        }}
    </script>
</body>
</html>
"""

    # Format the template with the analysis results
    html_content = html_template.format(
        summary=analysis.summary,
        mermaid_diagram=analysis.mermaid_diagram
    )

    # Write the HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return os.path.abspath(output_path)