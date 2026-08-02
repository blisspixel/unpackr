"""
Setup script for Unpackr.
Install with: python -m pip install .
"""

from pathlib import Path

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py


class BuildPyWithoutLocalState(build_py):
    """Remove ignored local customization files from staged package data."""

    def run(self):
        super().run()
        (Path(self.build_lib) / "config_files" / "comments.json").unlink(missing_ok=True)


readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="unpackr",
    version="1.3.1",
    description="Turn messy folders of archives into clean, working videos",
    url="https://github.com/blisspixel/unpackr",
    project_urls={
        "Issues": "https://github.com/blisspixel/unpackr/issues",
        "Source": "https://github.com/blisspixel/unpackr",
    },
    license="Apache 2.0 with Commons Clause",
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=">=3.11",
    packages=find_packages(exclude=["tests", "docs", "archive"]),
    py_modules=["doctor", "unpackr", "vhealth"],
    include_package_data=True,
    package_data={
        "config_files": ["comments.sample.json", "config.json"],
    },
    exclude_package_data={"config_files": ["comments.json"]},
    cmdclass={"build_py": BuildPyWithoutLocalState},
    install_requires=[
        "tqdm>=4.62.0",
        "psutil>=5.8.0",
        "colorama>=0.4.4",
    ],
    extras_require={
        "dev": [
            "bandit>=1.7.8",
            "mypy>=1.11",
            "pre-commit>=4.0",
            "pyright>=1.1.390",
            "pytest>=8.3",
            "pytest-cov>=5.0",
            "ruff>=0.8.0",
            "setuptools>=68",
        ],
    },
    entry_points={
        "console_scripts": [
            "unpackr=unpackr:main",
            "unpackr-doctor=doctor:main",
            "vhealth=vhealth:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Topic :: Utilities",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "License :: Other/Proprietary License",
    ],
)
