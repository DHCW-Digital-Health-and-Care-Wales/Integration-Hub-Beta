from setuptools import find_packages, setup

setup(
    name="event-logger-lib",
    version="0.1.0",
    author="DHCW",
    description="Azure Monitor Insights event logging library",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.13",
)
