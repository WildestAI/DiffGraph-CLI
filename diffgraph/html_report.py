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
            color-scheme: light dark;
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-primary: #1a202c;
                --text-primary: #f7fafc;
                --bg-secondary: #2d3748;
                --border-color: #4a5568;
                --tooltip-bg: #2d3748;
                --tooltip-text: #f7fafc;
                --tooltip-border: #4a5568;
            }}
            body {{
                color-scheme: dark;
            }}
            .mermaid .node {{
                fill: var(--bg-secondary) !important;
            }}
            .mermaid .node text {{
                fill: var(--text-primary) !important;
            }}
            .mermaid .edgePath .path {{
                stroke: var(--border-color) !important;
            }}
            .mermaid .edgeLabel {{
                background-color: var(--bg-secondary) !important;
                color: var(--text-primary) !important;
            }}
            /* Apply dark mode classes */
            .mermaid .file_added {{
                fill: #2f855a !important;
                stroke: #276749 !important;
                color: #fff !important;
            }}
            .mermaid .file_deleted {{
                fill: #c53030 !important;
                stroke: #9b2c2c !important;
                color: #fff !important;
            }}
            .mermaid .file_modified {{
                fill: #2b6cb0 !important;
                stroke: #2c5282 !important;
                color: #fff !important;
            }}
            .mermaid .file_unchanged {{
                fill: #4a5568 !important;
                stroke: #2d3748 !important;
                color: #fff !important;
            }}
            .mermaid .component_added {{
                fill: #276749 !important;
                stroke: #22543d !important;
                color: #fff !important;
            }}
            .mermaid .component_deleted {{
                fill: #9b2c2c !important;
                stroke: #822727 !important;
                color: #fff !important;
            }}
            .mermaid .component_modified {{
                fill: #2c5282 !important;
                stroke: #2a4365 !important;
                color: #fff !important;
            }}
            .mermaid .component_unchanged {{
                fill: #2d3748 !important;
                stroke: #1a202c !important;
                color: #fff !important;
            }}
        }}

        @media (prefers-color-scheme: light) {{
            :root {{
                --bg-primary: #ffffff;
                --text-primary: #1a202c;
                --bg-secondary: #f8f9fa;
                --border-color: #e2e8f0;
                --mermaid-bg: #f8f9fa;
                --mermaid-text: #1a202c;
                --mermaid-node-bg: #ffffff;
                --mermaid-node-border: #e2e8f0;
                --mermaid-node-text: #1a202c;
                --mermaid-edge: #4a5568;
                --tooltip-bg: #ffffff;
                --tooltip-text: #1a202c;
                --tooltip-border: #e2e8f0;
            }}
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
            background: var(--mermaid-bg);
            padding: 1.5rem;
            border-radius: 0.75rem;
            margin: 1.5rem 0;
            border: 1px solid var(--border-color);

            .node, .cluster {{
                rect,
                circle,
                ellipse,
                polygon,
                path {{
                    fill: var(--mermaid-node-bg) !important;
                    stroke: var(--mermaid-node-border) !important;
                    rx: 12px !important;
                    ry: 12px !important;
                    filter: drop-shadow(0 2px 8px #0002);
                    stroke-width: 2.5px !important;
                }}
            }}
        }}

        .mermaid .node text {{
            fill: var(--mermaid-node-text) !important;
            font-weight: 600;
            font-size: 1.05em;
            letter-spacing: 0.01em;
        }}

        .mermaid .edgePath .path {{
            stroke: var(--mermaid-edge) !important;
            stroke-width: 2.2px !important;
            opacity: 0.92;
        }}

        .mermaid .edgeLabel {{
            background-color: var(--mermaid-bg) !important;
            color: var(--mermaid-text) !important;
            border-radius: 0.5em;
            padding: 0.1em 0.5em;
            font-size: 0.98em;
            box-shadow: 0 1px 4px #0001;
        }}

        .mermaid .node rect,
        .mermaid .node circle,
        .mermaid .node ellipse,
        .mermaid .node polygon,
        .mermaid .node path {{
            fill: var(--mermaid-node-bg) !important;
            stroke: var(--mermaid-node-border) !important;
        }}

        .mermaid .node text {{
            fill: var(--mermaid-node-text) !important;
        }}

        .mermaid .edgePath .path {{
            stroke: var(--mermaid-edge) !important;
        }}

        .mermaid .edgeLabel {{
            background-color: var(--mermaid-bg) !important;
            color: var(--mermaid-text) !important;
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

        /* Tooltip styles */
        .tooltip {{
            position: fixed;
            background: var(--tooltip-bg, #ffffff);
            border: 1px solid var(--tooltip-border, #e2e8f0);
            border-radius: 0.5rem;
            padding: 1rem;
            max-width: 400px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            z-index: 1000;
            display: none;
            color: var(--tooltip-text, #1a202c);
        }}

        .tooltip.visible {{
            display: block;
        }}

        .mermaidTooltip {{
            position: absolute;
            text-align: center;
            max-width: 200px;
            padding: 2px;
            font-family: 'trebuchet ms', verdana, arial;
            font-size: 12px;
            background: var(--tooltip-bg, #ffffff) !important;
            color: var(--tooltip-text, #1a202c) !important;
            border: 1px solid var(--tooltip-border, #e2e8f0) !important;
            border-radius: 2px;
            pointer-events: none;
            z-index: 100;
        }}
    </style>
</head>
<body>
    <h1>DiffGraph Report</h1>

    <div class="mermaid">
        {mermaid_diagram}
    </div>

    <div id="tooltip" class="tooltip"></div>

    <div class="summary">
        <h2>Analysis Summary</h2>
        <div class="markdown-content" id="summary-content">
            {summary}
        </div>
    </div>

    <script>
        // Initialize Mermaid with system theme
        const isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
        mermaid.initialize({{
            startOnLoad: true,
            theme: isDarkMode ? 'dark' : 'default',
            securityLevel: 'loose',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }},
            themeVariables: {{
                darkMode: isDarkMode,
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                fontSize: '16px',
                primaryColor: isDarkMode ? '#4a5568' : '#e2e8f0',
                primaryTextColor: isDarkMode ? '#f7fafc' : '#1a202c',
                primaryBorderColor: isDarkMode ? '#718096' : '#cbd5e0',
                lineColor: isDarkMode ? '#a0aec0' : '#4a5568',
                secondaryColor: isDarkMode ? '#2d3748' : '#f8f9fa',
                tertiaryColor: isDarkMode ? '#1a202c' : '#ffffff',
                mainBkg: isDarkMode ? '#2d3748' : '#ffffff',
                mainContrastColor: isDarkMode ? '#f7fafc' : '#1a202c',
                nodeBkg: isDarkMode ? '#2f855a' : '#9ae6b4',
                nodeTextColor: isDarkMode ? '#f7fafc' : '#1a202c',
                nodeBorder: isDarkMode ? '#c53030' : '#feb2b2',
                clusterBkg: isDarkMode ? '#2b6cb0' : '#90cdf4',
                clusterTextColor: isDarkMode ? '#f7fafc' : '#1a202c',
                defaultLinkColor: isDarkMode ? '#4a5568' : '#e2e8f0',
                titleColor: isDarkMode ? '#f7fafc' : '#1a202c',
                edgeLabelBackground: isDarkMode ? '#2d3748' : '#f8f9fa',
                edgeLabelColor: isDarkMode ? '#f7fafc' : '#1a202c'
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

        // Tooltip handling
        window.showTooltip = function(text) {{
            const tooltip = document.getElementById('tooltip');
            tooltip.innerHTML = marked.parse(text); // Parse markdown in tooltip
            tooltip.classList.add('visible');
        }}

        window.hideTooltip = function() {{
            const tooltip = document.getElementById('tooltip');
            tooltip.classList.remove('visible');
        }}

        // Mermaid click callback
        window.callback = function(text) {{
            showTooltip(text);
        }}

        // Add click handlers for component nodes
        document.addEventListener('DOMContentLoaded', (event) => {{
            // Hide tooltip when clicking outside
            document.addEventListener('click', (e) => {{
                if (!e.target.closest('.node')) {{
                    hideTooltip();
                }}
            }});
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