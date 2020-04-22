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

HIST_URL = "https://history.muffinlabs.com/date/{}/{}"
HIST_NUM_ITEMS_DEFAULT = 5
HIST_WAIT_TIME_DEFAULT = 10

HIST_MODE_EVENTS = 1
HIST_MODE_BIRTHS = 2
HIST_MODE_DEATHS = 4
HIST_MODE_ALL = 8

BOT_GITHUB_URL = "https://github.com/LilSumac/discord-history-bot"

MONTH_TO_NUMBER = [
    "jan|january",
    "feb|february",
    "mar|march",
    "apr|april",
    "may",
    "jun|june",
    "jul|july",
    "aug|august",
    "sept|september",
    "oct|october",
    "nov|november",
    "dec|december",
]
MONTH_REGEX = "|".join(MONTH_TO_NUMBER)


class HistoryBot(discord.Client):
    @staticmethod
    def get_month_from_str(month):
        index = 0
        while index < 12:
            month_match = re.search("({})".format(MONTH_TO_NUMBER[index]), month)
            if month_match:
                return index + 1
            index += 1

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
                msg_pattern = re.search(pattern, msg_strip, re.M | re.I)
                if msg_pattern:
                    await func(msg)

    async def get_history(self, msg, req_mode=HIST_MODE_ALL):
        if msg.channel.id in self.sent_history:
            cur_time = time.time()
            last_time = self.sent_history[msg.channel.id]
            passed = cur_time - last_time
            if passed < self.wait_time:
                await msg.channel.send(
                    "Please wait {0:d} seconds until trying to get history.".format(
                        int(self.wait_time - passed)
                    )
                )
                return

        msg_strip = msg.content.strip()
        args = msg_strip.split()
        args.pop()  # Get rid of the first 'argument' (the command itself).

        req_date = []   # Contents will be [month, day].
        if len(args) == 0:
            cur_date = date.today()
            cur_month = cur_date.strftime("%m")
            cur_day = cur_date.strftime("%d")

            req_date.append(cur_month)
            req_date.append(cur_day)
        else:
            if len(args) == 1:
                date_pattern = re.search("^({}|\d{{1, 2}})\/(\d{{1, 2}})$".format(MONTH_REGEX), args[0])
            elif len(args) == 2:
                date_pattern = re.search("^({}|\d{{1, 2}})\s(\d{{1, 2}})$".format(MONTH_REGEX), args[0])
            else:
                await self.usage(msg)
                return

            if not date_pattern:
                await self.usage(msg)
                return

            try:
                cur_month = self.get_month_from_str(date_pattern.group(1))
                cur_day = date_pattern.group(3)
            except IndexError:
                await self.usage(msg)
                return

            if not cur_month or not cur_day:
                await self.usage(msg)
                return

            req_date.append(cur_month)
            req_date.append(cur_day)

        if len(req_date) != 2:
            await self.usage(msg)
            return

        req_date_fmt = "{}-{}".format(req_date[0], req_date[1])

        (data, cache_file) = self.get_cache_data(req_date_fmt)
        if not data and cache_file:
            self.logger.debug("Fetching history for %s from API...", req_date_fmt)
            req = requests.get(HIST_URL.format(req_date[0], req_date[1]), stream=True)

            try:
                req.raise_for_status()
            except requests.exceptions.HTTPError:
                await msg.channel.send("The server didn't like that! Did you give me a valid date?")
                return

            data = ""
            for chunk in req.iter_content(4096):
                data = "{}{}".format(data, chunk.decode(encoding="utf-8"))
                cache_file.write(chunk)

            cache_file.close()
            self.logger.debug("History fetched for %s.", req_date_fmt)

        try:
            data_json = json.loads(data)
        except (json.JSONDecodeError, TypeError) as err:
            self.logger.warning(
                "Received invalid JSON data for %s! Removing cache and aborting...",
                req_date_fmt,
            )
            rmfile_safe(HIST_CACHE_DIR, req_date_fmt)

            await msg.channel.send("Something went wrong! Please try again.")
            return

        data_obj = data_json.get("data")
        if not data_obj:
            return

        embeds = self.create_response(req_date_fmt, data_obj)
        for embed in embeds:
            if embed:
                embed.timestamp = datetime.now(tz=timezone.utc)
                await msg.channel.send(embed=embed)

        self.sent_history[msg.channel.id] = time.time()

    async def honk(self, msg):
        await msg.channel.send("<:honk:644674976556908544> THATCHER'S DEAD <:honk:644674976556908544>")

    async def usage(self, msg):
        await msg.channel.send("Not really sure what you meant there...")
        await msg.channel.send("I accept the following date formats!")
        await msg.channel.send("<month> <date> eg. feb 13, 06 22")
        await msg.channel.send("<month>/<date> eg. 02/13, 6/22")

    def get_cache_data(self, req_date):
        data_path = get_local_path(HIST_CACHE_DIR, req_date)
        try:
            self.logger.debug("Attempting to find existing cache for %s...", req_date)
            data_stream = open(data_path, "rb")
            data_bytes = data_stream.read()
            data = data_bytes.decode(encoding="utf-8")
            data_stream.close()

            # Check for invalid cache.
            if len(data) == 0:
                self.logger.debug(
                    "Existing cache for %s is invalid, rewriting...", req_date
                )
                data = None
                data_stream = open(data_path, "wb")
            else:
                data_stream = None
                self.logger.debug("Found existing cache for %s.", req_date)
        except FileNotFoundError:
            self.logger.debug("No existing cache found for %s.", req_date)
            data = None
            data_stream = open(data_path, "wb")

        return data, data_stream

    def create_response(self, date_header, json_data, req_mode=HIST_MODE_ALL):
        if not json_data:
            return None

        events = json_data.get("Events")
        births = json_data.get("Births")
        deaths = json_data.get("Deaths")
        events_embed = births_embed = deaths_embed = None

        if req_mode in (HIST_MODE_ALL, HIST_MODE_EVENTS):
            events_embed = discord.Embed(
                title="Events on {}".format(date_header),
                description="",
                color=discord.Color.from_rgb(51, 102, 255),
            )
            self.set_embed_content(events, events_embed)

        if req_mode in (HIST_MODE_ALL, HIST_MODE_BIRTHS):
            births_embed = discord.Embed(
                title="Births on {}".format(date_header),
                description="",
                color=discord.Color.from_rgb(0, 153, 51),
            )
            self.set_embed_content(births, births_embed)

        if req_mode in (HIST_MODE_ALL, HIST_MODE_DEATHS):
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
