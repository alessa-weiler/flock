"""
Setup configuration for Flock application

This file allows the package to be installed in development mode:
    pip install -e .

Or for production installation:
    pip install .
"""

from setuptools import setup, find_packages
import os

# Read the long description from README
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read version from package
about = {}
with open("src/flock/__init__.py", "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("__version__"):
            exec(line, about)
            break

setup(
    name="flock",
    version=about.get("__version__", "1.0.0"),
    author="Flock Team",
    author_email="your-email@example.com",  # Update this
    description="AI-Powered Professional Networking Platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-username/flock",  # Update this
    project_urls={
        "Bug Tracker": "https://github.com/your-username/flock/issues",
        "Documentation": "https://github.com/your-username/flock/wiki",
        "Source Code": "https://github.com/your-username/flock",
    },
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Framework :: Flask",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=[
        "Flask>=2.3.3",
        "Flask-CORS>=4.0.0",
        "gunicorn>=21.2.0",
        "Werkzeug>=2.3.7",
        "cryptography>=41.0.4",
        "openai>=1.100.2",
        "tiktoken>=0.5.2",
        "psycopg2-binary>=2.9.9",
        "stripe>=5.0.0",
        "pinecone-client>=3.0.0",
        "boto3>=1.34.0",
        "PyPDF2>=3.0.1",
        "pytesseract>=0.3.10",
        "python-docx>=1.1.0",
        "Pillow>=10.2.0",
        "pdf2image>=1.17.0",
        "python-magic>=0.4.27",
        "celery>=5.3.4",
        "redis>=5.0.1",
        "google-auth>=2.27.0",
        "google-auth-oauthlib>=1.2.0",
        "google-auth-httplib2>=0.2.0",
        "google-api-python-client>=2.116.0",
        "requests>=2.31.0",
        "aiohttp>=3.9.1",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.7.0",
            "flake8>=6.1.0",
            "mypy>=1.5.0",
            "isort>=5.12.0",
        ],
        "docs": [
            "sphinx>=7.1.0",
            "sphinx-rtd-theme>=1.3.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "flock=flock.app:main",  # If you add a main() function
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
