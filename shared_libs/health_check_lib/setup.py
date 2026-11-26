from pathlib import Path

from setuptools import find_packages, setup

readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="health_check_lib",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        # List your package dependencies here
    ],
    author="DHCW",
    description="Container App Health Check library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://example.com/mypackage",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.13",
)
