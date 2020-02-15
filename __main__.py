import argparse
import datetime
import requests
import discord
import logging
import random
import json
import time
import os

HIST_CONFIG_DIR = "config"
HIST_CACHE_DIR = "data_cache"
HIST_LOG_DIR = "logs"
HIST_TOKEN_NAME = "token.txt"

HIST_URL = "http://history.muffinlabs.com/date"
HIST_NUM_ITEMS_DEFAULT = 5
HIST_WAIT_TIME_DEFAULT = 10


class HistoryBot(discord.Client):
    def __init__(
        self, logger, num_items=HIST_NUM_ITEMS_DEFAULT, wait_time=HIST_WAIT_TIME_DEFAULT
    ):
        self.logger = logger
        self.num_items = num_items
        self.wait_time = wait_time
        self.sent_history = dict()
        super(HistoryBot, self).__init__()

    async def on_ready(self):
        self.logger.debug("Logged in as %s.", self.user.name)

    async def on_message(self, msg):
        if msg.author == self.user:
            return

        mentioned = discord.utils.get(msg.mentions, id=self.user.id)
        if not mentioned:
            return

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

        cur_date = datetime.date.today()
        cur_date_file = cur_date.strftime("%m-%d")
        cur_date_header = cur_date.strftime("%B %d")

        (data, data_stream) = self.get_cache_data(cur_date_file)
        if data is None:
            self.logger.debug("Fetching history for %s from API...", cur_date_file)
            req = requests.get(HIST_URL, stream=True)
            req.raise_for_status()

            data = ""
            for chunk in req.iter_content(4096):
                data = "{}{}".format(data, chunk.decode(encoding="utf-8"))
                data_stream.write(chunk)

            data_stream.close()
            self.logger.debug("History fetched for %s.", cur_date_file)

        try:
            data_json = json.loads(data)
        except (json.JSONDecodeError, TypeError) as err:
            self.logger.warning(
                "Received invalid JSON data for %s! Removing cache and aborting...",
                cur_date_file,
            )
            data_stream.close()
            rmfile_safe(HIST_CACHE_DIR, cur_date_file)

            await msg.channel.send("Something went wrong! Please try again.")
            return

        data_obj = data_json.get("data")
        if not data_obj:
            return

        responses = self.create_response(cur_date_header, data_obj)
        for response in responses:
            await msg.channel.send(response)

        self.sent_history[msg.channel.id] = time.time()

    def get_cache_data(self, cur_date):
        data_path = get_local_path(HIST_CACHE_DIR, cur_date)
        try:
            self.logger.debug("Attempting to read existing cache for %s...", cur_date)
            data_stream = open(data_path, "rb")
            data_bytes = data_stream.read()
            data = data_bytes.decode(encoding="utf-8")

            # Check for invalid cache.
            if len(data) == 0:
                self.logger.debug(
                    "Existing cache for %s is invalid, rewriting...", cur_date
                )
                data = None
                data_stream.close()
                data_stream = open(data_path, "wb")
            else:
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

        response_list = list()
        response_list.append("**{}: Let's look back...**\n\n".format(date_header))
        response_list.append("{}\n".format("__**Events**__"))
        for _ in range(self.num_items):
            event = random.choice(events)
            response_list.append(
                "[{}] {}\n".format(event.get("year", "???"), event.get("text", "???"))
            )
            events.remove(event)

        response_list.append("\n{}\n".format("__**Births**__"))
        for _ in range(self.num_items):
            birth = random.choice(births)
            response_list.append(
                "[{}] {}\n".format(birth.get("year", "???"), birth.get("text", "???"))
            )
            births.remove(birth)

        response_list.append("\n{}\n".format("__**Deaths**__"))
        for _ in range(self.num_items):
            death = random.choice(deaths)
            response_list.append(
                "[{}] {}\n".format(death.get("year", "???"), death.get("text", "???"))
            )
            deaths.remove(death)

        final_list = []
        cur_str = ""
        cur_len = 0
        for response in response_list:
            if cur_len + len(response) > 2000:
                final_list.append(cur_str)
                cur_str = ""
                cur_len = 0

            cur_str = "{}{}".format(cur_str, response)
            cur_len += len(response)
        if cur_str != "":
            final_list.append(cur_str)

        return final_list


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
        "--log_debug", default=False, type=bool, help="Print debug messages to console",
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
    logger.setLevel(logging.DEBUG if args.log_debug else logging.WARNING)

    logger.debug("Instantiating HistoryBot...")
    bot = HistoryBot(logger)
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("The token provided was invalid.")


if __name__ == "__main__":
    main()
