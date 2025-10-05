#!/usr/bin/env python3
"""Setup script for SnapRecon."""

from setuptools import setup, find_packages

setup(
    name="snaprecon",
    version="0.1.0",
    author="rabbyt3s",
    description="Authorized reconnaissance tool with screenshots and local analysis",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "pydantic>=2.0.0",
        "typer>=0.9.0",
        "rich>=13.0.0",
        "playwright>=1.40.0",
        "httpx>=0.25.0",
        "click>=8.0.0",
        "jinja2>=3.0.0",
        "pyyaml>=6.0",
        "toml>=0.10.0",
        "aiofiles>=23.0.0",
        "colorama>=0.4.6",
        "tqdm>=4.65.0",
    ],
    entry_points={
        "console_scripts": [
            "snaprecon=snaprecon.cli:app",
        ],
    },
)
