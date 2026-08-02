from setuptools import setup, find_packages

setup(
    name="wild",
    version="1.3.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.7",
        "tree-sitter-language-pack>=0.10.0",
    ],
    entry_points={
        "console_scripts": [
            "wild=diffgraph.cli:main",
        ],
    },
    python_requires=">=3.10",
    author="WildestAI Team",
    description="AI-powered git-wrapper CLI tool with visualizing diffs",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
    ],
)
