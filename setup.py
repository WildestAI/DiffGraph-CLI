from setuptools import setup, find_packages

setup(
    name="diffgraph-ai",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.7",
    ],
    entry_points={
        "console_scripts": [
            "diffgraph-ai=diffgraph.cli:main",
        ],
    },
    python_requires=">=3.7",
    author="DiffGraph Team",
    description="A CLI tool for visualizing code changes with AI",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)