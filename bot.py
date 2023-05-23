from twitchio.ext import commands
import os
import random
import asyncio
import requests
import html
import json
import sqlite3
import time
from difflib import SequenceMatcher

HINT_CHARS_REVEALED = 0.4 # Scale between 0.0 and 1.0 where 1 reveals 100% of the answer.
TIME_BEFORE_HINT = 20 # Seconds before a hint is given.
TIME_BEFORE_ANSWER = 10 # Seconds (after hint is given) before the answer is revealed.
ANSWER_CORRECTNESS = 0.9 # Scale between 0.0 and 1.0 where 1.0 is an exact match.
CORRECT_ANSWER_VALUE = 1 # Number of points to award for a correct question.
BOT_PREFIX = '%' # Token required before each command

BANNED_IN_QUESTIONS = [
    "WHICH OF",
    "WHICH ONE OF",
    "THE FOLLOWING"
]

BANNED_IN_ANSWER = [
    "ALL OF THE ABOVE"
]

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

def get_top_users(channel_name, limit=5):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute('SELECT username, score FROM users WHERE channel = ? ORDER BY score DESC LIMIT ?', (channel_name, limit))
    result = c.fetchall()
    conn.close()
    return result

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
            prefix=BOT_PREFIX,
            initial_channels=channels
        )
        
        self.channel_states = {} # key: channel_name, value: channel state
        self.current_question = None
        self.channels = channels

    def get_question(self):
        api_url = 'https://opentdb.com/api.php?amount=1&type=multiple'
        response = requests.get(api_url)
        
        if response.status_code == requests.codes.ok:
            parsed_response = json.loads(response.text)
            question_data = parsed_response["results"]
            return question_data
        else:
            print("Error:", response.status_code, response.text)
            return 
    
    def format_question(self, question):
        formatted_question = html.unescape(question['question'])
        formatted_answer = html.unescape(question['correct_answer'])
        question['question'] = formatted_question
        question['correct_answer'] = formatted_answer
        return question

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
                answer = channel_state['current_question']["answer"]
                revealed_chars = int(len(answer) * HINT_CHARS_REVEALED) + 1

                # Select random indices to reveal
                indices_to_reveal = random.sample(range(len(answer)), revealed_chars)

                hint = ''
                for i, char in enumerate(answer):
                    if char == ' ':
                        hint += ' '
                    elif i in indices_to_reveal:
                        hint += char
                    else:
                        hint += '_'  # Add space between each character

                print(f"[{ctx.channel.name}] Hint generated: {hint.strip()}")
                await ctx.send("Hint: " + hint.strip())
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
            add_score(channel, user, CORRECT_ANSWER_VALUE)
            print(f"{user} answered with {similarity(user_answer, correct_answer)} accuracy.")
            await message.channel.send(f"{user} answered with {round(similarity(user_answer, correct_answer) * 100, 2)}% accuracy! Their score is now {get_score(channel, user)}. Answer: {channel_state['current_question']['answer']}")
            channel_state['current_question'] = None

        await self.handle_commands(message)

    @commands.command()
    async def trivia(self, ctx: commands.Context):
        channel_name = ctx.channel.name
        channel_state = self.get_channel_state(channel_name)
        if 'last_trivia' not in channel_state:
            channel_state['last_trivia'] = 0

        cooldown = get_channel_cooldown(channel_name)
        time_since_last_trivia = time.time() - channel_state['last_trivia']
        # print(time_since_last_trivia) #Debug

        if time_since_last_trivia < cooldown:
            await ctx.send(f"Please wait {cooldown - int(time_since_last_trivia)} seconds before starting a new trivia.")
            return

        channel_state['last_trivia'] = time.time()
        
        if not channel_state['current_question']:

            # Checking for phrases banned in question and answer.

            while True:
                question_data = self.get_question()[0]
                
                question_contains_phrase = False
                for phrase in BANNED_IN_QUESTIONS:
                    if phrase in question_data["question"].upper():
                        print(f"[{channel_name}] Question contained '{phrase}'; Generating new question.")
                        question_contains_phrase = True
                        break

                answer_contains_phrase = False
                for phrase in BANNED_IN_ANSWER:
                    if phrase in question_data["correct_answer"].upper():
                        print(f"[{channel_name}] Answer contained '{phrase}'; Generating new question.")
                        answer_contains_phrase = True
                        break

                # Questions containing 'NOT' in all caps are an edge-case, and should not
                # be compared to the question with .upper()
                question_contains_NOT = False
                if "NOT" in question_data["question"]:
                    print(f"[{channel_name}] Question contained 'NOT'; Generating new question.")
                    question_contains_NOT = True
                
                if not question_contains_phrase and not answer_contains_phrase and not question_contains_NOT:
                    break

            question_data = self.format_question(question_data)

            channel_state['current_question'] = {
                "category": question_data["category"],
                "question": question_data["question"],
                "answer": question_data["correct_answer"],
                "difficulty": question_data["difficulty"]
            }

            if "(" in channel_state['current_question']["answer"]:
                print(f"Removing Parentheses From: {channel_state['current_question']['answer']}")
                channel_state['current_question']["answer"] = channel_state['current_question']["answer"][:channel_state['current_question']["answer"].index("(")]

            print(f"[{ctx.channel.name}] Trivia Game Started by {ctx.author.name} [category: " + channel_state['current_question']['category'] + "]: Q: " + channel_state['current_question']["question"] + " A: " + channel_state['current_question']["answer"])
            
            await ctx.send(f"Trivia Question: [Difficulty - {channel_state['current_question']['difficulty']}] " + channel_state['current_question']["question"])
            await self.check_answer(ctx)

            if channel_state['current_question']:  # If the question hasn't been answered yet
                await ctx.send("Time's up! The correct answer was: " + channel_state['current_question']["answer"])
                print(f"[{ctx.channel.name}] Time Up | A: {channel_state['current_question']['answer']}")
                channel_state['current_question'] = None
        else:
            await ctx.send("A trivia question is already active!")
        
    @commands.command()
    async def join(self, ctx: commands.Context, channel_name: str = None):
        if channel_name == None:
            channel_name = ctx.author.name
        if ctx.channel.name == 'twiviabot':
            if (channel_name == ctx.author.name) or (ctx.author.name == 'itssport'):
                if channel_name not in self.channels:
                    await self.join_channels([channel_name])
                    self.channels.append(channel_name)
                    add_channel(channel_name)
                    print(f"TwiviaBot has joined channel {channel_name}.")
                    await ctx.send(f"Twivia bot has joined channel {channel_name}. Make sure to /mod TwiviaBot.")
                else:
                    await ctx.send(f"Already in channel {channel_name}")
            else:
                await ctx.send("You may only add the bot to your own channel.")
        else:
            await ctx.send(f"This command may only be used in TwiviaBot's chat.")
    
    @commands.command()
    async def part(self, ctx: commands.Context, channel_name: str = None):
        if channel_name == None:
            channel_name = ctx.author.name
        if (ctx.channel.name == 'twiviabot'):
            if (channel_name == ctx.author.name) or (ctx.author.name == 'itssport'):
                if channel_name in self.channels:
                    await self.part_channels([channel_name])
                    self.channels.remove(channel_name)
                    remove_channel(channel_name)
                    print(f"TwiviaBot has left channel {channel_name}.")
                    await ctx.send(f"TwiviaBot has left channel {channel_name}.")
                else:
                    await ctx.send(f"Channel {channel_name} not found in the list.")
            else:
                await ctx.send("You may only remove the bot from your own channel.")
        else:
            await ctx.send(f"This command may only be used in TwiviaBot's chat.")

    @commands.command()
    async def points(self, ctx: commands.Context):
        await ctx.send(f'The current points of {ctx.author.name} is ' + str(get_score(ctx.channel.name, ctx.author.name)))
    
    @commands.command()
    async def leaderboard(self, ctx: commands.Context):
        top_users = get_top_users(ctx.channel.name)
        leaderboard_message = f"{ctx.channel.name}'s Trivia Leaderboard: \n"
        for idx, user in enumerate(top_users, start=1):
            leaderboard_message += f"{idx}. {user[0]} - {user[1]} points | \n"
        await ctx.send(leaderboard_message)

    @commands.command()
    async def skip(self, ctx: commands.Context):
        channel_state = self.get_channel_state(ctx.channel.name)
        if ctx.author.is_mod or ctx.author.name == 'itssport':
            if not channel_state['current_question'] == None:
                await ctx.send(f'Question skipped. A: ' + channel_state['current_question']["answer"])
                print(f"[{ctx.channel.name}] Question skipped by {ctx.author.name}")
                channel_state['current_question'] = None
        else:
            await ctx.send("You must be a moderator to use this command.")

    @commands.command()
    async def cooldown(self, ctx: commands.Context, cooldown: int = None):
        channel_state = self.get_channel_state(ctx.channel.name)

        if (ctx.author.is_mod) or (ctx.author.name == 'itssport'):
            if cooldown is not None:
                set_channel_cooldown(ctx.channel.name, cooldown)
                await ctx.send(f"Cooldown set to {cooldown} seconds for {ctx.channel.name}.")
            else:
                channel_name = ctx.channel.name

                if 'last_trivia' not in channel_state:
                    channel_state['last_trivia'] = 0
                
                cooldown = get_channel_cooldown(channel_name)
                time_since_last_trivia = time.time() - channel_state['last_trivia']
                await ctx.send(f"{ctx.channel.name}'s trivia cooldown is set to {get_channel_cooldown(ctx.channel.name)} seconds. [{cooldown - int(time_since_last_trivia)}s remaining]")
        else:
            channel_name = ctx.channel.name

            if 'last_trivia' not in channel_state:
                channel_state['last_trivia'] = 0
            
            cooldown = get_channel_cooldown(channel_name)
            time_since_last_trivia = time.time() - channel_state['last_trivia']
            await ctx.send(f"{ctx.channel.name}'s trivia cooldown is set to {get_channel_cooldown(ctx.channel.name)} seconds. [{cooldown - int(time_since_last_trivia)}s remaining]")

    @commands.command()
    async def help(self, ctx: commands.Context):
        await ctx.send(
            "COMMANDS: " +
            "%join / %part - Add or remove bot from your channel | " +
            "%trivia - Start a new trivia game | " +
            "%points - See how many points you have | " +
            "%leaderboard - Show top 5 users in this channel | " +
            "%skip - Skip the current question (mod only) | " +
            "%cooldown [seconds] - Set a cooldown for trivia (mod only) "
        )

    @commands.command()
    async def announce(self, ctx: commands.Context):
        if ctx.author.name == 'itssport':
            announcement = ctx.message.content[10:]
            for channel_name in self.channels:
                channel = self.get_channel(channel_name)
                await channel.send(f"[ANNOUNCEMENT] {announcement}")
            await ctx.send("Announcement sent to all channels.")
        else:
            await ctx.send("You do not have permission to perform this command.")

setup_db()
channels = get_saved_channels()
if 'twiviabot' not in channels:
    add_channel('twiviabot')
    channels = get_saved_channels()
    print(f"twiviabot not found in channels list on boot, re-added.")
twiviaBot = Bot()
twiviaBot.run()
