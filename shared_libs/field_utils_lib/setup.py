from setuptools import find_packages, setup

setup(
    name="field-utils-lib",
    version="0.1.0",
    description="Shared HL7 field utilities (bracket-aware)",
    packages=find_packages(include=["field_utils_lib*"]),
    install_requires=[
        "hl7apy==1.3.5",
    ],
)


