import discord
import logging


class HistoryBot(discord.client):
    def __init__(self):
        self.logger = logging.getLogger("discord_history_bot")
        super(HistoryBot, self).__init__()

    async def on_ready(self):
        self.logger.info("Logged in as {}!".format(self.user))

    async def on_message(self, msg):
        self.logger.info("Received message from {0.author}: {0.content}".format(msg))


if __name__ == "__main__":
    token_stream = open("config/token", "rb")
    token_bytes = token_stream.read()
    token = token_bytes.decode(encoding="utf-8")

    bot = HistoryBot()
    bot.run(token)
