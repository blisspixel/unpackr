"""
Setup script for Unpackr.
Allows installation via: pip install -e .
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README for the long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding='utf-8') if readme_file.exists() else ""

setup(
    name="unpackr",
    version="1.0.0",
    description="Automated tool for cleaning up download folders from Usenet/newsgroups",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    python_requires=">=3.7",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "colorama>=0.4.4",
        "psutil>=5.8.0",
    ],
    entry_points={
        'console_scripts': [
            'unpackr=unpackr:main',
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Utilities",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
