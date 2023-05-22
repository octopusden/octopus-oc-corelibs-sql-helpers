from setuptools import setup

__version="1.0.2"

spec = {
    "name": "oc-sql-helpers",
    "version": __version,
    "license": "LGPLv2",
    "description": "Helper classes for PL/SQL source code files",
    "long_description": "",
    "long_description_content_type": "text/plain",
    "packages": ["oc_sql_helpers"],
    "install_requires": [
        "chardet >= 2.3.0"],
    "package_data": {},
    "python_requires": ">=3.6",
}

setup(**spec)
