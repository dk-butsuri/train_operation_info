from setuptools import setup, find_packages

NAME = "train_operation_info"
DESCRIPTION = "Typed railway service alerts from 38 official sources, without guessing"
AUTHOR = "dk-butsuri"
VERSION = "1.0.0"
INSTALL_REQUIRES = [
    "pydantic >= 2",
    "httpx",
    "tabulate",
    "tzdata",
    "beautifulsoup4"    
    ]

LICENSE = "MIT License"
CLASSIFIERS = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Intended Audience :: Developers",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Topic :: Internet :: WWW/HTTP",
]

with open("README.md", encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()

setup(name=NAME,
      author=AUTHOR,
      maintainer=AUTHOR,
      description=DESCRIPTION,
      long_description=LONG_DESCRIPTION,
      long_description_content_type="text/markdown",
      url="https://github.com/dk-butsuri/train_operation_info",
      project_urls={
          "Source": "https://github.com/dk-butsuri/train_operation_info",
          "Issues": "https://github.com/dk-butsuri/train_operation_info/issues",
          "Providers": "https://github.com/dk-butsuri/train_operation_info/blob/main/docs/PROVIDERS.md",
      },
      version=VERSION,
      package_dir={"": "src"},
      packages=find_packages(where="src", include=["train_operation_info", "train_operation_info.*"]),
      package_data={"train_operation_info": ["py.typed"]},
      python_requires=">=3.10",
      install_requires=INSTALL_REQUIRES,
      extras_require={
          "dev": ["pytest>=8", "mypy>=1.10", "types-beautifulsoup4", "wheel"],
          "visualizer": ["truststore>=0.10,<0.11"],
      },
      license=LICENSE,
      classifiers=CLASSIFIERS
    )
