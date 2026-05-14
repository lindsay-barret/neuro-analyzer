from setuptools import setup, find_packages

setup(
    name="neuro-analyzer",
    version="0.1.0",
    description=(
        "Quantitative pediatric MRI re-analysis pipeline. "
        "Research and educational use only — not a medical device."
    ),
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "pydicom>=2.4.0",
        "nibabel>=5.0.0",
        "numpy>=1.24.0",
        "matplotlib>=3.7.0",
        "anthropic>=0.40.0",
        "Pillow>=10.0.0",
        "click>=8.1.0",
        "rich>=13.0.0",
        "python-dotenv>=1.0.0",
        "PyYAML>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "neuro-analyzer=neuro_analyzer.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Education",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
    ],
)
