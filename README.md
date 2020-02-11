# discord-history-bot
A Discord bot that will fetch 'Today in History' blurbs, as well as random quotes from historical figures.

## Roadmap
- [x] Implement a fetch functionality for today's events.
- [x] Cache recently-fetched data.
- [ ] Implement configuration from both JSON file and command line.
- [ ] Clear the cache and re-fetch if it ages to a certain point.
- [ ] Implement quote-fetching functionality.
- [ ] Make Discord permissions better.
- [ ] Come up with a better name.

## Requirements
- Python 3
- ``discord.py`` Package

## Usage
``python discord-history-bot --debug_log=False``

**Arguments:**
- (Optional) ``debug_log``: Whether or not to log debug-level messages. Default: ``False``
