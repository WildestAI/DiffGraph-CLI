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
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}
        .mermaid {{
            background: #f8f9fa;
            padding: 1rem;
            border-radius: 0.5rem;
            margin: 1rem 0;
        }}
        .summary {{
            background: white;
            padding: 1.5rem;
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }}
        h1 {{
            color: #1a202c;
            font-size: 2rem;
            margin-bottom: 1.5rem;
        }}
        pre {{
            background: #f8f9fa;
            padding: 1rem;
            border-radius: 0.5rem;
            overflow-x: auto;
        }}
        code {{
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
        }}
    </style>
</head>
<body>
    <h1>DiffGraph Report</h1>

    <div class="summary">
        <h2>Analysis Summary</h2>
        <div class="markdown-content">
            {summary}
        </div>
    </div>

    <div class="mermaid">
        {mermaid_diagram}
    </div>

    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true
            }}
        }});
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