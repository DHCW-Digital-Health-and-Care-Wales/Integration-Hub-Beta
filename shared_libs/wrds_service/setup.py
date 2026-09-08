from setuptools import find_packages, setup

setup(
    name="wrds-service",
    version="0.1.0",
    description="SOAP client for the WRDS (Welsh Reference Data Service) GetResultSet operation",
    packages=find_packages(include=["wrds_service*"]),
    install_requires=[
        "requests>=2.32.0",
        "defusedxml==0.7.1",
    ],
)
