from setuptools import find_namespace_packages, setup

setup(
    name="cli-anything-claude-bak",
    version="0.1.0",
    description="Scheduled backups of Claude Code, Claude Desktop and claude.ai exports.",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    package_data={"cli_anything.claude_bak": ["skills/*.md"]},
    python_requires=">=3.10",
    install_requires=["click>=8.0.0"],
    extras_require={"dev": ["pytest>=7"]},
    entry_points={"console_scripts": [
        "cli-anything-claude-bak=cli_anything.claude_bak.claude_bak_cli:main",
    ]},
)
