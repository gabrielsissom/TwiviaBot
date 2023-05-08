from twitchio.ext import commands
import os
import random
import asyncio
import requests
import json
import sqlite3
import time
from difflib import SequenceMatcher

TIME_BEFORE_HINT = 20 # Seconds before a hint is given.
TIME_BEFORE_ANSWER = 10 # Seconds (after hint is given) before the answer is revealed.
ANSWER_CORRECTNESS = 0.9 # Scale between 0.0 and 1.0 where 1.0 is an exact match.

def get_saved_channels():
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('SELECT name FROM channels')
    result = c.fetchall()
    conn.close()
    return [channel[0] for channel in result]

def setup_db():
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS channels (
                     name TEXT PRIMARY KEY
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS users (
                     username TEXT NOT NULL,
                     channel TEXT NOT NULL,
                     score INTEGER,
                     PRIMARY KEY (username, channel),
                     FOREIGN KEY (channel) REFERENCES channels (name)
                 )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS channel_cooldowns (
                 channel TEXT PRIMARY KEY,
                 cooldown INTEGER,
                 FOREIGN KEY (channel) REFERENCES channels (name)
             )''')

    conn.commit()
    conn.close()

def get_channel_cooldown(channel_name):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('SELECT cooldown FROM channel_cooldowns WHERE channel = ?', (channel_name,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 30  # Default cooldown is 30 seconds

def set_channel_cooldown(channel_name, cooldown):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO channel_cooldowns (channel, cooldown) VALUES (?, ?)',
              (channel_name, cooldown))
    conn.commit()
    conn.close()

def add_channel(channel_name):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO channels (name) VALUES (?)', (channel_name,))
    conn.commit()
    conn.close()

def remove_channel(channel_name):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM channels WHERE name = ?', (channel_name,))
    conn.commit()
    conn.close()

def reset_scores(channel_name):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE channel = ?', (channel_name,))
    conn.commit()
    conn.close()

def add_score(channel_name, username, points):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (username, channel, score) VALUES (?, ?, ?)',
              (username, channel_name, 0))
    c.execute('UPDATE users SET score = score + ? WHERE username = ? AND channel = ?',
              (points, username, channel_name))
    conn.commit()
    conn.close()

def get_score(channel_name, username):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('SELECT score FROM users WHERE username = ? AND channel = ?', (username, channel_name))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=os.environ['TMI_TOKEN'],
            client_id=os.environ['CLIENT_ID'],
            nick=os.environ['BOT_NICK'],
            prefix=os.environ['BOT_PREFIX'],
            initial_channels=channels
        )
        
        # self.categories = ['fooddrink']
        self.categories = [
            'artliterature',
            'language',
            'sciencenature',
            'general',
            'fooddrink',
            'peopleplaces',
            'geography',
            'historyholidays',
            'entertainment',
            'toysgames',
            'music',
            'mathematics',
            'religionmythology',
            'sportsleisure'
            ]
        self.channel_states = {} # key: channel_name, value: channel state
        self.current_question = None
        self.channels = channels

    def get_channel_state(self, channel_name):
        if channel_name not in self.channel_states:
            self.channel_states[channel_name] = {
                'current_question': None,
            }
        return self.channel_states[channel_name]
    
    def clean_up_channel_state(self, channel_name):
        if channel_name in self.channel_states:
            del self.channel_states[channel_name]

    async def check_answer(self, ctx):
        channel_state = self.get_channel_state(ctx.channel.name)
        try:
            await asyncio.wait_for(self.wait_for_answer(ctx), timeout=TIME_BEFORE_HINT)
        except asyncio.TimeoutError:
            if channel_state['current_question']:
                revealed_chars = int(len(channel_state['current_question']["answer"]) / 5) + 1
                hint = ''
                for i, char in enumerate(channel_state['current_question']["answer"]):
                    if char == ' ':
                        hint += ' '
                    elif i < revealed_chars:
                        hint += char
                    else:
                        hint += '_'
                print(f"[{ctx.channel.name}] Hint generated: {hint}")
                await ctx.send("Hint: " + hint)
        try:
            await asyncio.wait_for(self.wait_for_answer(ctx), timeout=TIME_BEFORE_ANSWER)
        except asyncio.TimeoutError:
            if channel_state['current_question']:  # If the question hasn't been answered yet
                await ctx.send("Time's up! The correct answer was: " + channel_state['current_question']["answer"])
                print(f"[{ctx.channel.name}] Time Up | A: {channel_state['current_question']['answer']}")
                channel_state['current_question'] = None
    
    async def wait_for_answer(self, ctx):
        channel_state = self.get_channel_state(ctx.channel.name)
        while channel_state['current_question'] is not None:
            await asyncio.sleep(1)

    async def event_ready(self):
        print(f'Logged in as | {self.nick}')
        print(f'User id is | {self.user_id}')

    async def event_message(self, message):
        if message.echo:
            return

        channel_state = self.get_channel_state(message.channel.name)
        user_answer = message.content.strip().lower()
        correct_answer = channel_state['current_question']['answer'].lower() if channel_state['current_question'] else None

        if channel_state['current_question'] and similarity(user_answer, correct_answer) >= ANSWER_CORRECTNESS:
            user = message.author.name
            channel = message.channel.name
            add_score(channel, user, 1)
            print(f"{user} answered with {similarity(user_answer, correct_answer)} accuracy.")
            await message.channel.send(f"{user} answered correctly! Their score is now {get_score(channel, user)}. Answer: {channel_state['current_question']['answer']}")
            channel_state['current_question'] = None

        await self.handle_commands(message)

    @commands.command()
    async def trivia(self, ctx: commands.Context):
        channel_name = ctx.channel.name
        channel_state = self.get_channel_state(ctx.channel.name)

        if 'last_trivia' not in channel_state:
            channel_state['last_trivia'] = 0

        cooldown = get_channel_cooldown(channel_name)
        time_since_last_trivia = time.time() - channel_state['last_trivia']

        if time_since_last_trivia < cooldown:
            # await ctx.send(f"Please wait {cooldown - int(time_since_last_trivia)} seconds before starting a new trivia.")
            return

        channel_state['last_trivia'] = time.time()
        
        if not channel_state['current_question']:
            response = requests.get('https://api.api-ninjas.com/v1/trivia?category={}'.format(random.choice(self.categories)), headers={'X-Api-Key': 'eA8ya6wbQP2nFIA3Z859Zw==RKDSp8A0PtOmArFY'})
            parsed_response = json.loads(response.text)
            question_data = parsed_response[0]
            channel_state['current_question'] = {
                "category": question_data["category"],
                "question": question_data["question"],
                #"answer": "Answer (really unimportant)", #Debug: removing parenthesis
                "answer": question_data["answer"],
            }

            if "(" in channel_state['current_question']["answer"]:
                print(f"Removing Parentheses From: {channel_state['current_question']['answer']}")
                channel_state['current_question']["answer"] = channel_state['current_question']["answer"][:channel_state['current_question']["answer"].index("(")]

            print(f"[{ctx.channel.name}] Triva Game Started by {ctx.author.name} [category: " + channel_state['current_question']['category'] + "]: Q: " + channel_state['current_question']["question"] + " A: " + channel_state['current_question']["answer"])

            if response.status_code == requests.codes.ok:
                await ctx.send(f"Trivia question: " + channel_state['current_question']["question"])
                await self.check_answer(ctx)
            else:
                await ctx.send("Error:", response.status_code, response.text)

            if channel_state['current_question']:  # If the question hasn't been answered yet
                await ctx.send("Time's up! The correct answer was: " + channel_state['current_question']["answer"])
                print(f"[{ctx.channel.name}] Time Up | A: {channel_state['current_question']['answer']}")
                channel_state['current_question'] = None
        else:
            await ctx.send("A trivia question is already active!")

    @commands.command()
    async def join(self, ctx: commands.Context, channel_name: str):
        if ctx.channel.name == 'twiviabot':
            if (channel_name == ctx.author.name) or (ctx.author.name == 'itssport'):
                if channel_name not in self.channels:
                    await self.join_channels([channel_name])
                    self.channels.append(channel_name)
                    add_channel(channel_name)
                    await ctx.send(f"Joined channel {channel_name}")
                else:
                    await ctx.send(f"Already in channel {channel_name}")
            else:
                await ctx.send("You may only add the bot to your own channel.")
        else:
            await ctx.send(f"This command may only be used in TwiviaBot's own chat.")
    
    @commands.command()
    async def part(self, ctx: commands.Context, channel_name: str):
        if (ctx.channel.name == 'twiviabot') or (ctx.author.name == ctx.channel.name) or (ctx.author.name == 'itssport'):
            if (channel_name == ctx.author.name) or (ctx.author.name == 'itssport'):
                if channel_name in self.channels:
                    await self.part_channels([channel_name])
                    self.channels.remove(channel_name)
                    remove_channel(channel_name)
                    await ctx.send(f"Left channel {channel_name}")
                else:
                    await ctx.send(f"Channel {channel_name} not found in the list.")
            else:
                await ctx.send("You may only remove the bot from your own channel.")
        else:
            await ctx.send(f"This command may only be used by the channel owner.")

    @commands.command()
    async def points(self, ctx: commands.Context):
        await ctx.send(f'The current points of {ctx.author.name} is ' + str(get_score(ctx.channel.name, ctx.author.name)))
    
    @commands.command()
    async def skip(self, ctx: commands.Context):
        channel_state = self.get_channel_state(ctx.channel.name)
        if ctx.author.is_mod or ctx.author.name == 'itssport':
            await ctx.send(f'Question skipped. A: ' + channel_state['current_question']["answer"])
            print(f"[{ctx.channel.name}] Question skipped by {ctx.author.name}")
            channel_state['current_question'] = None
        else:
            await ctx.send("You must be a moderator to use this command.")

    @commands.command()
    async def cooldown(self, ctx: commands.Context, cooldown: int = None):
        if ctx.author.name == ctx.channel.name or ctx.author.name == 'itssport':
            if cooldown is not None:
                set_channel_cooldown(ctx.channel.name, cooldown)
                await ctx.send(f"Cooldown set to {cooldown} seconds for {ctx.channel.name}.")
            else:
                await ctx.send(f"{ctx.channel.name}'s current cooldown is {get_channel_cooldown(ctx.channel.name)} seconds.")
        else:
            await ctx.send(f"{ctx.channel.name}'s current cooldown is {get_channel_cooldown(ctx.channel.name)} seconds.")


    @commands.command()
    async def help(self, ctx: commands.Context):
        await ctx.send(
            "COMMANDS: " +
            "%trivia - Start a new trivia game | " +
            "%points - See how many points you have | " +
            "%skip - Skip the current question (mod only) | " +
            "%cooldown [seconds] - Set a cooldown for trivia (streamer only) "
        )

setup_db()
channels = get_saved_channels()
if 'itssport' not in channels:
    add_channel('itssport')
    channels = get_saved_channels()
    print(f"itssport not found in channels list on boot, re-added.")
if 'twiviabot' not in channels:
    add_channel('twiviabot')
    channels = get_saved_channels()
    print(f"twiviabot not found in channels list on boot, re-added.")

twiviaBot = Bot()
twiviaBot.run()