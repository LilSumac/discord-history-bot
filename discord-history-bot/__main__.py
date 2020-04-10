import functools
import argparse
import requests
import discord
import logging
import random
import json
import time
import os
import re

from datetime import datetime, timezone, date

HIST_CONFIG_DIR = "config"
HIST_CACHE_DIR = "data_cache"
HIST_LOG_DIR = "logs"
HIST_TOKEN_NAME = "token.txt"

HIST_URL = "https://history.muffinlabs.com/date"
HIST_NUM_ITEMS_DEFAULT = 5
HIST_WAIT_TIME_DEFAULT = 10

HIST_MODE_EVENTS = 1
HIST_MODE_BIRTHS = 2
HIST_MODE_DEATHS = 4
HIST_MODE_ALL = 8

BOT_GITHUB_URL = "https://github.com/LilSumac/discord-history-bot"


class HistoryBot(discord.Client):
    def __init__(
        self, logger, num_items=HIST_NUM_ITEMS_DEFAULT, wait_time=HIST_WAIT_TIME_DEFAULT
    ):
        self.logger = logger
        self.num_items = num_items
        self.wait_time = wait_time
        self.sent_history = dict()

        self.dispatchers = {
            "!today": self.get_history,
            "!events": functools.partial(self.get_history, req_mode=HIST_MODE_EVENTS),
            "!births": functools.partial(self.get_history, req_mode=HIST_MODE_BIRTHS),
            "!deaths": functools.partial(self.get_history, req_mode=HIST_MODE_DEATHS),
        }

        self.patterns = {
            "thatcher": self.honk,
        }

        super(HistoryBot, self).__init__()

    async def on_ready(self):
        self.logger.debug("Logged in as %s.", self.user.name)

    async def on_message(self, msg):
        if msg.author == self.user:
            return

        msg_strip = msg.content.strip()
        msg_parts = msg_strip.split()
        if len(msg_parts) > 0 and msg_parts[0] in self.dispatchers:
            await self.dispatchers[msg_parts[0]](msg)
        else:
            for pattern, func in self.patterns.items():
                msg_pattern = re.search(pattern, msg_strip)
                if msg_pattern:
                    await func(msg)

    async def get_history(self, msg, req_mode=HIST_MODE_ALL):
        if msg.channel.id in self.sent_history:
            cur_time = time.time()
            last_time = self.sent_history[msg.channel.id]
            passed = cur_time - last_time
            if passed < self.wait_time:
                await msg.channel.send(
                    "Please wait {0:d} seconds until trying again.".format(
                        int(self.wait_time - passed)
                    )
                )
                return

        cur_date = date.today()
        cur_date_file = cur_date.strftime("%m-%d")
        cur_date_header = cur_date.strftime("%B %d")

        (data, cache_file) = self.get_cache_data(cur_date_file)
        if not data and cache_file:
            self.logger.debug("Fetching history for %s from API...", cur_date_file)
            req = requests.get(HIST_URL, stream=True)
            req.raise_for_status()

            data = ""
            for chunk in req.iter_content(4096):
                data = "{}{}".format(data, chunk.decode(encoding="utf-8"))
                cache_file.write(chunk)

            cache_file.close()
            self.logger.debug("History fetched for %s.", cur_date_file)

        try:
            data_json = json.loads(data)
        except (json.JSONDecodeError, TypeError) as err:
            self.logger.warning(
                "Received invalid JSON data for %s! Removing cache and aborting...",
                cur_date_file,
            )
            rmfile_safe(HIST_CACHE_DIR, cur_date_file)

            await msg.channel.send("Something went wrong! Please try again.")
            return

        data_obj = data_json.get("data")
        if not data_obj:
            return

        embeds = self.create_response(cur_date_header, data_obj)
        for embed in embeds:
            embed.timestamp = datetime.now(tz=timezone.utc)
            await msg.channel.send(embed=embed)

        self.sent_history[msg.channel.id] = time.time()

    async def honk(self, msg):
        await msg.channel.send("<:honk:644674976556908544> THATCHER'S DEAD <:honk:644674976556908544>")

    def get_cache_data(self, cur_date):
        data_path = get_local_path(HIST_CACHE_DIR, cur_date)
        try:
            self.logger.debug("Attempting to find existing cache for %s...", cur_date)
            data_stream = open(data_path, "rb")
            data_bytes = data_stream.read()
            data = data_bytes.decode(encoding="utf-8")
            data_stream.close()

            # Check for invalid cache.
            if len(data) == 0:
                self.logger.debug(
                    "Existing cache for %s is invalid, rewriting...", cur_date
                )
                data = None
                data_stream = open(data_path, "wb")
            else:
                data_stream = None
                self.logger.debug("Found existing cache for %s.", cur_date)
        except FileNotFoundError:
            self.logger.debug("No existing cache found for %s.", cur_date)
            data = None
            data_stream = open(data_path, "wb")

        return data, data_stream

    def create_response(self, date_header, json_data):
        if not json_data:
            return None

        events = json_data.get("Events")
        births = json_data.get("Births")
        deaths = json_data.get("Deaths")
        if not events or not births or not deaths:
            return

        events_embed = discord.Embed(
            title="Events on {}".format(date_header),
            description="",
            color=discord.Color.from_rgb(51, 102, 255),
        )
        self.set_embed_content(events, events_embed)

        births_embed = discord.Embed(
            title="Births on {}".format(date_header),
            description="",
            color=discord.Color.from_rgb(0, 153, 51),
        )
        self.set_embed_content(births, births_embed)

        deaths_embed = discord.Embed(
            title="Deaths on {}".format(date_header),
            description="",
            color=discord.Color.from_rgb(204, 0, 0),
        )
        self.set_embed_content(deaths, deaths_embed)

        return [events_embed, births_embed, deaths_embed]

    def set_embed_content(self, event_list, embed):
        for _ in range(self.num_items):
            event = random.choice(event_list)
            linked_text = event.get("text", "???")
            for link in event.get("links", dict()):
                link_title = link.get("title", None)
                if not link_title:
                    continue

                match = re.search(link_title, linked_text, flags=re.I)
                if match:
                    linked_text = "{}[{}]({}){}".format(
                        linked_text[:match.start()],
                        link_title,
                        link.get("link", "https://google.com"),
                        linked_text[match.end():],
                    )

            year_text = "**[{}]**".format(event.get("year", "???"))
            embed.add_field(name=year_text, value=linked_text)
            event_list.remove(event)

        embed.add_field(name="\u200b", value="[Github]({})".format(BOT_GITHUB_URL), inline=False)


def get_local_path(*args):
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    for arg in args:
        cur_dir = os.path.join(cur_dir, arg)
    return cur_dir


def mkdir_safe(*args):
    try:
        os.mkdir(get_local_path(*args))
    except FileExistsError:
        pass


def rmfile_safe(*args):
    try:
        os.unlink(get_local_path(*args))
    except FileNotFoundError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Go back in time.")
    parser.add_argument(
        "--debug_log", default=False, type=bool, help="Print debug messages to console",
    )
    args = parser.parse_args()

    mkdir_safe(HIST_CONFIG_DIR)
    mkdir_safe(HIST_CACHE_DIR)
    mkdir_safe(HIST_LOG_DIR)

    try:
        token_stream = open(get_local_path(HIST_CONFIG_DIR, HIST_TOKEN_NAME), "r")
        token = token_stream.read()
    except FileNotFoundError:
        token_warning = (
            "Didn't find a {0} file in the configuration folder, so one was created for you. "
            "Please place your bot token in {1}/{0} before continuing."
        )
        print(token_warning.format(HIST_TOKEN_NAME, HIST_CONFIG_DIR))

        temp = open(get_local_path(HIST_CONFIG_DIR, HIST_TOKEN_NAME), "w")
        temp.close()
        return

    logging.basicConfig(format="%(asctime)s - %(name)s [%(levelname)s]: %(message)s")
    logger = logging.getLogger("discord-history-bot")
    logger.setLevel(logging.DEBUG if args.debug_log else logging.WARNING)

    logger.debug("Instantiating HistoryBot...")
    bot = HistoryBot(logger)
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("The token provided was invalid.")


if __name__ == "__main__":
    main()
