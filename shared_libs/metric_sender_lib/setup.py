from setuptools import setup, find_packages

setup(
    name="metric_sender_lib",
    version="0.1.0",
    author="DHCW",
    description="Azure Monitor Insights metric sender library",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.13",
)
