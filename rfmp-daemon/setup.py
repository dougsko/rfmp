#!/usr/bin/env python3
"""Setup script for RFMP Daemon."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="rfmpd",
    version="0.3.0",
    author="RFMP Contributors",
    description="RF Microblog Protocol Daemon",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/rfmp-daemon",
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=[
        "fastapi>=0.104.1",
        "uvicorn[standard]>=0.24.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "pyserial-asyncio>=0.6",
        "aiosqlite>=0.19.0",
        "mmh3>=4.0.1",
        "python-dateutil>=2.8.2",
        "pyyaml>=6.0.1",
        "structlog>=23.2.0",
    ],
    entry_points={
        "console_scripts": [
            "rfmpd=rfmpd.main:main",
        ],
    },
)