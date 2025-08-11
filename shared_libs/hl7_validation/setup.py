from setuptools import setup, find_packages

setup(
    name="hl7_validation_lib",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "hl7apy==1.3.5",
        "xmlschema==3.4.3",
    ],
    author="DHCW",
    description="HL7 v2 ER7 to XML conversion and XML Schema validation",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://example.com/mypackage",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.13",
)


