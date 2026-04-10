from setuptools import setup, find_packages

setup(
    name="qullamaggie-scanner",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pandas>=2.0",
        "numpy>=1.24",
        "yfinance>=0.2.36",
        "tqdm>=4.65",
        "jinja2>=3.1",
        "pyarrow>=14.0",
    ],
    entry_points={
        "console_scripts": [
            "scanner=scanner.__main__:main",
        ],
    },
)
