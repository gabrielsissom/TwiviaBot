import os # for importing env vars for the bot to use
from twitchio.ext import commands
import ssl
import certifi

ssl_context = ssl.create_default_context(cafile=certifi.where())

bot = commands.Bot(
    # set up the bot
    token=os.environ['TMI_TOKEN'],
    client_id=os.environ['CLIENT_ID'],
    nick=os.environ['BOT_NICK'],
    prefix=os.environ['BOT_PREFIX'],
    initial_channels=[os.environ['CHANNEL']]
)

if __name__ == "__main__":
    bot.run()