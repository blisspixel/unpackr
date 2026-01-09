"""
Setup script for Unpackr.
Install with: pip install -e .
"""

from setuptools import setup, find_packages
from pathlib import Path

readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding='utf-8') if readme_file.exists() else ""

setup(
    name="unpackr",
    version="1.3.0",
    description="Turn messy folders of archives into clean, working videos",
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=">=3.7",
    packages=find_packages(exclude=['tests', 'docs', 'archive']),
    include_package_data=True,
    package_data={
        'config_files': ['*.json'],
    },
    install_requires=[
        "tqdm>=4.62.0",
        "psutil>=5.8.0",
        "colorama>=0.4.4",
    ],
    entry_points={
        'console_scripts': [
            'unpackr=unpackr:main',
            'unpackr-doctor=doctor:main',
            'vhealth=vhealth:main',
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Utilities",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
