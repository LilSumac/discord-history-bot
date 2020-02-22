# discord-history-bot
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A Discord bot that will fetch 'Today in History' blurbs, as well as random quotes from historical
figures.

## Roadmap
- [x] Implement a fetch functionality for today's events.
- [x] Cache recently-fetched data.
- [x] Make Discord permissions better.
- [ ] Allow refreshing of embed with reactions.
- [ ] Implement configuration from both JSON file and command line.
- [ ] Clear the cache and re-fetch if it ages to a certain point.
- [ ] Implement quote-fetching functionality.
- [ ] Come up with a better name.

## Requirements
- Python 3
- ``discord.py`` Package

## Usage
If one doesn't already exist, create a ``config`` folder in your repo and create a ``token.txt``
file inside. This is where you'll put your bot token to authenticate with Discord.

If you don't know what a bot token is or how to get one, refer to the many guides online for
[creating a Discord bot](https://discordpy.readthedocs.io/en/latest/discord.html).

The bot can be launched on your own machine/server for manual hosting by starting up the Python
script:

```shell script
python discord-history-bot --debug_log=False
```

**Arguments:**
- (Optional) ``debug_log``: Whether or not to log debug-level messages. Default: ``False``
