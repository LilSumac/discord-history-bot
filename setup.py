import setuptools

with open("README.md", "r") as readme:
    long_description = readme.read()

setuptools.setup(
    name="discord-history-bot",
    version="0.0.2",
    author="LilSumac",
    author_email="lilsumac@gmail.com",
    description="Go back in time.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/LilSumac/discord-history-bot",
    packages=setuptools.find_packages(),
    install_requires=[
        "discord.py",
        "requests",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
