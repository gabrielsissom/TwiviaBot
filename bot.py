import os, random, asyncio, html, json, psycopg2, time, requests, sys
from twitchio.ext import commands
from difflib import SequenceMatcher
import discord

#GLOBAL CONSTANTS
DATABASE_URL = os.environ['DATABASE_URL']
DISCORD_WEBHOOK_URL = os.environ['DISCORD_WEBHOOK_URL']

#GLOBAL SETTINGS
HINT_CHARS_REVEALED = 0.4  # Scale between 0.0 and 1.0 where 1 reveals 100% of the answer.
TIME_BEFORE_HINT = 20  # Seconds before a hint is given.
TIME_BEFORE_ANSWER = 15  # Seconds (after hint is given) before the answer is revealed.
ANSWER_CLOSE = 0.8  # Scale between 0.0 and 1.0 where 1.0 is an exact match. Announces that a user is close to the correct answer.
ANSWER_CORRECTNESS = 0.9  # Scale between 0.0 and 1.0 where 1.0 is an exact match.
CORRECT_ANSWER_VALUE = 1  # Number of points to award for a correct question.
BOT_PREFIX = '%'  # Token required before each command
MAX_API_TRIES = 3  # Number of times to try getting a question set before giving up.

BANNED_IN_QUESTIONS = [
  "WHICH OF", "WHICH ONE OF", "OF THE FOLLOWING", "OUT OF THESE"
]

BANNED_IN_ANSWER = ["ALL OF THE ABOVE"]

REVEAL_IN_HINT = ["-", ",", "$", "%", ".", "/", "'", '"']

CATEGORIES = {
  "ALL": 0,
  "GENERAL": 9,
  "BOOKS": 10,
  "FILMS": 11,
  "MUSIC": 12,
  "THEATRE": 13,
  "TV": 14,
  "VIDEOGAMES": 15,
  "BOARDGAMES": 16,
  "SCIENCE/NATURE": 17,
  "COMPUTERS": 18,
  "MATHEMATICS": 19,
  "MYTHOLOGY": 20,
  "SPORTS": 21,
  "GEOGRAPHY": 22,
  "HISTORY": 23,
  "POLITICS": 24,
  "ART": 25,
  "CELEBRITIES": 26,
  "ANIMALS": 27,
  "VEHICLES": 28,
  "COMICS": 29,
  "GADGETS": 30,
  "ANIME": 31,
  "ANIMATION": 32,
  "GENSHIN": 33
}


def get_db_connection():
  return psycopg2.connect(DATABASE_URL)


def setup_db():
  conn = get_db_connection()
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

  c.execute('''CREATE TABLE IF NOT EXISTS channel_categories (
                 channel TEXT PRIMARY KEY,
                 category TEXT,
                 FOREIGN KEY (channel) REFERENCES channels (name)
             )''')

  c.execute(
    '''ALTER TABLE channels ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE'''
  )

  c.execute(
    '''ALTER TABLE channels ADD COLUMN IF NOT EXISTS is_premium BOOLEAN NOT NULL DEFAULT FALSE'''
  )

  c.execute(
    '''ALTER TABLE channels ADD COLUMN IF NOT EXISTS is_paused BOOLEAN NOT NULL DEFAULT FALSE'''
  )

  conn.commit()
  conn.close()


class DiscordWebhookStream(object):

  def __init__(self, webhook_url):
    self.webhook_url = webhook_url

  def write(self, message):
    # Send message to Discord webhook
    payload = {
      'content': f"```{message}```",
      'username': 'TwiviaBot',
      'avatar_url': 'https://i.imgur.com/3qA9RkH.png'
    }
    requests.post(self.webhook_url, json=payload)


webhook_url = DISCORD_WEBHOOK_URL

# Set custom streams
sys.stdout = DiscordWebhookStream(webhook_url)
sys.stderr = DiscordWebhookStream(webhook_url)


def get_saved_channels():
  conn = get_db_connection()
  c = conn.cursor()
  # Select only active channels.
  c.execute('''
      SELECT name FROM channels WHERE is_active = TRUE
  ''')
  result = c.fetchall()
  c.close()
  conn.close()
  return [channel[0] for channel in result]


def get_premium_channels():
  conn = get_db_connection()
  c = conn.cursor()
  # Select only active channels.
  c.execute('''
      SELECT name FROM channels WHERE is_premium = TRUE
  ''')
  result = c.fetchall()
  c.close()
  conn.close()
  return [channel[0] for channel in result]


def get_top_users(channel_name, limit=5):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute(
    'SELECT username, score FROM users WHERE channel = %s AND score > 0 ORDER BY score DESC LIMIT %s',
    (channel_name, limit))
  result = c.fetchall()
  c.close()
  conn.close()
  return result


def reset_user_scores(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('UPDATE users SET score = 0 WHERE channel = %s', (channel_name, ))
  conn.commit()
  c.close()
  conn.close()
  return


def get_channel_cooldown(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('SELECT cooldown FROM channel_cooldowns WHERE channel = %s',
            (channel_name, ))
  result = c.fetchone()
  c.close()
  conn.close()
  return result[0] if result else 30  # Default cooldown is 30 seconds


def set_channel_cooldown(channel_name, cooldown):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute(
    '''
    INSERT INTO channel_cooldowns (channel, cooldown) 
    VALUES (%s, %s) 
    ON CONFLICT (channel) 
    DO UPDATE SET cooldown = EXCLUDED.cooldown
    ''', (channel_name, cooldown))
  conn.commit()
  c.close()
  conn.close()


def set_channel_category(channel_name, category):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute(
    '''
    INSERT INTO channel_categories (channel, category) 
    VALUES (%s, %s) 
    ON CONFLICT (channel) 
    DO UPDATE SET category = EXCLUDED.category
    ''', (channel_name, category))
  conn.commit()
  c.close()
  conn.close()


def get_channel_category(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('SELECT category FROM channel_categories WHERE channel = %s',
            (channel_name, ))
  result = c.fetchone()
  c.close()
  conn.close()
  return result[0] if result else 'ALL'  # Default cooldown is 30 seconds


def add_channel(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  # Re-activate if the channel has been added back.
  c.execute(
    '''
      INSERT INTO channels (name) VALUES (%s)
      ON CONFLICT (name) DO UPDATE SET is_active = TRUE
  ''', (channel_name, ))
  conn.commit()
  c.close()
  conn.close()


def remove_channel(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  # Soft delete: Set is_active to FALSE instead of deleting.
  c.execute(
    '''
      UPDATE channels SET is_active = FALSE WHERE name = %s
  ''', (channel_name, ))
  conn.commit()
  c.close()
  conn.close()


def add_premium(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  # Re-activate if the channel has been added back.
  c.execute(
    '''
      INSERT INTO channels (name) VALUES (%s)
      ON CONFLICT (name) DO UPDATE SET is_premium = TRUE
  ''', (channel_name, ))
  conn.commit()
  c.close()
  conn.close()


def remove_premium(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute(
    '''
      UPDATE channels SET is_premium = FALSE WHERE name = %s
  ''', (channel_name, ))
  conn.commit()
  c.close()
  conn.close()


def set_is_paused(channel_name, is_paused: bool):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('UPDATE channels SET is_paused = %s WHERE name = %s', (
    is_paused,
    channel_name,
  ))
  conn.commit()
  c.close()
  conn.close()


def get_is_paused(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('SELECT is_paused FROM channels WHERE name = %s', (channel_name, ))
  result = c.fetchone()
  c.close()
  conn.close()
  return result[0]


def reset_scores(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('DELETE FROM users WHERE channel = %s', (channel_name, ))
  conn.commit()
  c.close()
  conn.close()


def add_score(channel_name, username, points):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute(
    'INSERT INTO users (username, channel, score) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING',
    (username, channel_name, 0))
  c.execute(
    'UPDATE users SET score = score + %s WHERE username = %s AND channel = %s',
    (points, username, channel_name))
  conn.commit()
  c.close()
  conn.close()


def get_score(channel_name, username):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('SELECT score FROM users WHERE username = %s AND channel = %s',
            (username, channel_name))
  result = c.fetchone()
  c.close()
  conn.close()
  return result[0] if result else 0


def similarity(a, b):
  return SequenceMatcher(None, a, b).ratio()


class Bot(commands.Bot):

  def __init__(self, channels):
    super().__init__(token=os.environ['TMI_TOKEN'],
                     client_id=os.environ['CLIENT_ID'],
                     nick=os.environ['BOT_NICK'],
                     prefix=BOT_PREFIX,
                     initial_channels=channels)

    self.channel_states = {}  # key: channel_name, value: channel state
    # self.current_question = None  # deprecated use channel_states
    self.channels = channels

  async def get_question(self, channel_name, precategory=None):
    api_url = 'https://opentdb.com/api.php?amount=5&type=multiple'
    cat_ids = []
    categories = ''

    # Use pre-determined category if provided
    if precategory != None:
      if precategory.upper() in CATEGORIES:
        categories = precategory.upper()
      else:
        categories = get_channel_category(channel_name)
    else:
      categories = get_channel_category(channel_name)

    # If no category is provided, use channel's category list
    for category in CATEGORIES:
      if category in categories:
        cat_ids.append(CATEGORIES[category])

    # Select a random category from channel's categories
    id = random.choice(cat_ids)
    if not 0 in cat_ids:
      api_url = f"https://opentdb.com/api.php?amount=5&category={id}&type=multiple"

    ## Genshin Trivia
    if id == 33:
      with open("genshin.json", "r") as read_file:
        genshin_questions = json.load(read_file)
      question_data = random.choice(genshin_questions)
      return question_data

    api_successful = False  # Set to True if API request is successful
    new_question_set_needed = True  # Set to False if a question set contains a suitable question
    api_tries = 0
    question_set_iteration = 0

    while (not api_successful) and (api_tries < MAX_API_TRIES) and (
        new_question_set_needed):
      response = requests.get(api_url)
      if response.status_code == requests.codes.ok:
        api_successful = True  # The API retrieved a set of 5 questions
        results = response.json()['results']  # parse json once
        question_set_iteration = 0
        new_question_set_needed = False
        # Checking for phrases banned in question and answer.

        # print(results) #DEBUG
        while (question_set_iteration < 5):  # Iterate through the question set

          question_contains_banned_phrase = False
          question_upper = results[question_set_iteration]['question'].upper()
          for phrase in BANNED_IN_QUESTIONS:
            if phrase in question_upper:
              print(
                f"[{channel_name}] ({question_set_iteration + 1} of 5) Question contained '{phrase}' | {results[question_set_iteration]['question']}"
              )
              question_contains_banned_phrase = True
              break

          answer_contains_banned_phrase = False
          answer_upper = results[question_set_iteration]["correct_answer"].upper()
          for phrase in BANNED_IN_ANSWER:
            if phrase in answer_upper:
              print(
                f"[{channel_name}] ({question_set_iteration + 1} of 5) Answer contained '{phrase}' | {results[question_set_iteration]['correct_answer']}"
              )
              answer_contains_banned_phrase = True
              break

          # Questions containing 'NOT' in all caps are an edge-case, and should not
          # be compared to the question with .upper()
          question_contains_NOT = False
          if "NOT" in results[question_set_iteration]["question"]:
            print(
              f"[{channel_name}] ({question_set_iteration + 1} of 5) Question contained 'NOT' | {results[question_set_iteration]['question']}"
            )
            question_contains_NOT = True

          if not question_contains_banned_phrase and not answer_contains_banned_phrase and not question_contains_NOT:
            print(
              f"[{channel_name}] Found suitable question ({question_set_iteration + 1} of 5) | {results[question_set_iteration]}"
            )
            break
          else:
            # print(f"[{channel_name}] BANNED PHRASES IN (Q: {results[question_set_iteration]['question']} A: {results[question_set_iteration]['correct_answer']})")
            question_set_iteration += 1
            if question_set_iteration >= 5:
              new_question_set_needed = True

      else:
        api_successful = False
        if api_tries < MAX_API_TRIES:
          print(
            f"[{channel_name}] API Error: {response.status_code} | {response.text}"
          )
          print(
            f"[{channel_name}] Retrying... ({api_tries + 1} of {MAX_API_TRIES})"
          )
          api_tries += 1
          await asyncio.sleep(3)

        else:
          print(f"[{channel_name}] API failure: Question failed.")
          return None

    # parsed_response = json.loads(response.text) #DEBUG
    # print(parsed_response) #DEBUG
    question_data = results[question_set_iteration]
    # print(question_data) #DEBUG
    return question_data

  def format_question(self, question):
    formatted_question = html.unescape(question['question'])
    formatted_answer = html.unescape(question['correct_answer'])
    formatted_category = html.unescape(question['category'])
    question['question'] = formatted_question
    question['correct_answer'] = formatted_answer
    question['category'] = formatted_category
    return question

  def get_channel_state(self, channel_name):
    if channel_name not in self.channel_states:
      is_paused = get_is_paused(channel_name)
      self.channel_states[channel_name] = {
        'current_question': None,
        'is_paused': is_paused,
      }
    return self.channel_states[channel_name]

  def update_game_state(self, channel_name, *, is_paused: bool):
    channel_state = self.get_channel_state(channel_name)
    set_is_paused(channel_name, is_paused)
    channel_state['is_paused'] = is_paused

  def clean_up_channel_state(self, channel_name):
    if channel_name in self.channel_states:
      del self.channel_states[channel_name]

  async def check_answer(self, ctx):
    channel_state = self.get_channel_state(ctx.channel.name)
    try:
      await asyncio.wait_for(self.wait_for_answer(ctx),
                             timeout=TIME_BEFORE_HINT)
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
          elif (i in indices_to_reveal) or (char in REVEAL_IN_HINT):
            hint += char
          else:
            hint += '_'  # Add space between each character

        print(f"[{ctx.channel.name}] Hint generated: {hint.strip()}")
        await ctx.send("Hint: " + hint.strip())
    try:
      await asyncio.wait_for(self.wait_for_answer(ctx),
                             timeout=TIME_BEFORE_ANSWER)
    except asyncio.TimeoutError:
      if channel_state[
          'current_question']:  # If the question hasn't been answered yet
        await ctx.send("Time's up! The correct answer was: " +
                       channel_state['current_question']["answer"])
        print(
          f"[{ctx.channel.name}] Time Up | A: {channel_state['current_question']['answer']}"
        )
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
    if channel_state['current_question']:
      user_answer = message.content.strip().lower()
      correct_answer = channel_state['current_question']['answer'].lower(
      ) if channel_state['current_question'] else None

      if (similarity(user_answer, correct_answer) >=
          ANSWER_CLOSE) and (similarity(user_answer, correct_answer) <
                             ANSWER_CORRECTNESS):  #If user answers CLOSELY
        user = message.author.name
        await message.channel.send(
          f"{user} is close! {round(similarity(user_answer, correct_answer) * 100, 2)}% accurate."
        )

      if similarity(
          user_answer,
          correct_answer) >= ANSWER_CORRECTNESS:  #If user answers CORRECTLY
        user = message.author.name
        channel = message.channel.name
        add_score(channel, user, CORRECT_ANSWER_VALUE)
        print(
          f"[{channel}] {user} answered with {similarity(user_answer, correct_answer)} accuracy."
        )
        await message.channel.send(
          f"{user} answered with {round(similarity(user_answer, correct_answer) * 100, 2)}% accuracy! Their score is now   {get_score(channel, user)}. Answer: {channel_state['current_question']['answer']}"
        )
        channel_state['current_question'] = None

    await self.handle_commands(message)

  @commands.command()
  async def trivia(self, ctx: commands.Context, cat: str = None):
    channel_name = ctx.channel.name
    channel_state = self.get_channel_state(channel_name)

    if channel_state.get('is_paused'):
      await ctx.send(
        f"{ctx.channel.name}'s game is paused. '%game resume' to keep playing!"
      )
      return

    if 'last_trivia' not in channel_state:
      channel_state['last_trivia'] = 0

    cooldown = get_channel_cooldown(channel_name)
    time_since_last_trivia = time.time() - channel_state['last_trivia']
    # print(time_since_last_trivia) #Debug

    if time_since_last_trivia < cooldown:
      await ctx.send(
        f"Please wait {cooldown - int(time_since_last_trivia)} seconds before starting a new trivia."
      )
      return

    channel_state['last_trivia'] = time.time()

    if not channel_state[
        'current_question']:  # Checking if the current_question is None (i.e. no question is active)
      if not cat == None:  # If a category is provided
        question_data = await self.get_question(channel_name, cat)
      else:  # If a cateogry is not provided
        question_data = await self.get_question(channel_name)

      if question_data == None:  # If get_question returns None, API failed.
        print(f"[{channel_name}] API failure: Question failed.")
        await ctx.send("Trivia API failed. Try again.")
        return

      question_data = self.format_question(question_data)

      channel_state['current_question'] = {
        "category": question_data["category"],
        "question": question_data["question"],
        "answer": question_data["correct_answer"],
        "difficulty": question_data["difficulty"]
      }

      if "(" in channel_state['current_question']["answer"]:
        print(
          f"[{ctx.channel.name}] Removing Parentheses From: {channel_state['current_question']['answer']}"
        )
        channel_state['current_question']["answer"] = channel_state[
          'current_question'][
            "answer"][:channel_state['current_question']["answer"].index("(")]

      print(
        f"[{ctx.channel.name}] Trivia Game Started by {ctx.author.name} [category: "
        + channel_state['current_question']['category'] + "]: Q: " +
        channel_state['current_question']["question"] + " A: " +
        channel_state['current_question']["answer"])

      await ctx.send(
        f"Trivia: [Category - {channel_state['current_question']['category']}] [Difficulty - {channel_state['current_question']['difficulty'].upper()}] Q: "
        + channel_state['current_question']["question"])
      await self.check_answer(ctx)

      if channel_state[
          'current_question']:  # If the question hasn't been answered yet
        await ctx.send("Time's up! The correct answer was: " +
                       channel_state['current_question']["answer"])
        print(
          f"[{ctx.channel.name}] Time Up | A: {channel_state['current_question']['answer']}"
        )
        channel_state['current_question'] = None
    else:
      await ctx.send("A trivia question is already active!")

  @commands.command()
  async def channels(self, ctx: commands.Context):
    if ctx.author.name == 'itssport':
      active_channels = sorted(get_saved_channels())
      channels_message = "TwiviaBot exists in: "
      for channel in active_channels:
        channels_message += (f'{channel}, ')
      await ctx.send(channels_message)

  @commands.command()
  async def sub(self, ctx: commands.Context, channel_name: str = None):
    if (ctx.author.name == 'itssport'):
      if channel_name not in get_premium_channels():
        add_premium(channel_name)
        print(f"[{channel_name}] Added to premium channels.")
        await ctx.send(f"Channel {channel_name} is now premium.")
      else:
        await ctx.send(f"Channel {channel_name} is already premium.")
    else:
      await ctx.send("You do not have permission to use this command.")

  @commands.command()
  async def unsub(self, ctx: commands.Context, channel_name: str = None):
    if (ctx.author.name == 'itssport'):
      if channel_name in get_premium_channels():
        remove_premium(channel_name)
        print(f"[{channel_name}] Removed from premium channels.")
        await ctx.send(f"Channel {channel_name} is no longer premium.")
      else:
        await ctx.send(f"Channel {channel_name} is not premium.")
    else:
      await ctx.send("You do not have permission to use this command.")

  @commands.command()
  async def join(self, ctx: commands.Context):
    channel_name = ctx.author.name
    if ctx.channel.name == 'twiviabot':
      if channel_name not in self.channels:
        await self.join_channels([channel_name])
        self.channels.append(channel_name)
        add_channel(channel_name)
        print(f"TwiviaBot has joined channel {channel_name}.")
        await ctx.send(
          f"Twivia bot has joined channel {channel_name}. Make sure to /mod TwiviaBot."
        )
      else:
        await ctx.send(f"Already in channel {channel_name}")
    else:
      await ctx.send("This command may only be used in TwiviaBot's chat.")

  @commands.command()
  async def forcejoin(self, ctx: commands.Context, channel_name: str = None):
    if ctx.author.name == 'itssport' and not channel_name == None:
      if channel_name not in self.channels:
        await self.join_channels([channel_name])
        self.channels.append(channel_name)
        add_channel(channel_name)
        print(f"TwiviaBot has joined channel {channel_name}.")
        await ctx.send(
          f"Twivia bot has joined channel {channel_name}. Make sure to /mod TwiviaBot."
        )
      else:
        await ctx.send(f"Already in channel {channel_name}")

  @commands.command()
  async def part(self, ctx: commands.Context):
    channel_name = ctx.author.name
    if (ctx.channel.name == 'twiviabot'):
      if channel_name in self.channels:
        await self.part_channels([channel_name])
        self.channels.remove(channel_name)
        remove_channel(channel_name)
        print(f"TwiviaBot has left channel {channel_name}.")
        await ctx.send(f"TwiviaBot has left channel {channel_name}.")
      else:
        await ctx.send(f"Channel {channel_name} not found in the list.")
    else:
      await ctx.send("This command may only be used in TwiviaBot's chat.")

  @commands.command()
  async def forcepart(self, ctx: commands.Context, channel_name: str = None):
    if ctx.author.name == 'itssport' and not channel_name == None:
      await self.part_channels([channel_name])
      try:
        self.channels.remove(channel_name)
      except:
        print(f"Channel {channel_name} not found in the list.")
      remove_channel(channel_name)
      print(f"TwiviaBot has left channel {channel_name}.")
      await ctx.send(f"TwiviaBot has left channel {channel_name}.")

  @commands.command()
  async def points(self, ctx: commands.Context):
    await ctx.send(f'The current points of {ctx.author.name} is ' +
                   str(get_score(ctx.channel.name, ctx.author.name)))

  @commands.command()
  async def leaderboard(self, ctx: commands.Context):
    top_users = get_top_users(ctx.channel.name)
    leaderboard_message = f"{ctx.channel.name}'s Trivia Leaderboard: \n"
    for idx, user in enumerate(top_users, start=1):
      leaderboard_message += f"{idx}. {user[0]} - {user[1]} points | \n"
    await ctx.send(leaderboard_message)

  @commands.command()
  async def game(self, ctx: commands.Context, arg: str = None):
    if (ctx.author.name == ctx.channel.name) or (ctx.author.name
                                                 == 'itssport'):
      if (arg == 'pause'):
        await self.skip(ctx)  # skip current question if exists
        self.update_game_state(ctx.channel.name, is_paused=True)
        await ctx.send(f"{ctx.channel.name}'s game paused.")
      elif (arg == 'resume'):
        self.update_game_state(ctx.channel.name, is_paused=False)
        await ctx.send(f"{ctx.channel.name}'s game resumed.")
      elif (arg == 'new'):
        await self.skip(ctx)  # skip current question if exists
        await self.leaderboard(ctx)
        reset_user_scores(ctx.channel.name)
        self.update_game_state(ctx.channel.name, is_paused=False)
        await ctx.send(
          f"A new game has started in {ctx.channel.name}'s channel!")
      else:
        await ctx.send(
          "unrecongnized command argument; try '%game pause', '%game resume', or '%game new'"
        )
    else:
      await ctx.send("This command may only be used by the channel owner.")

  @commands.command()
  async def skip(self, ctx: commands.Context):
    channel_state = self.get_channel_state(ctx.channel.name)
    if ctx.author.is_mod or ctx.author.name == 'itssport':
      if not channel_state['current_question'] == None:
        await ctx.send('Question skipped. A: ' +
                       channel_state['current_question']["answer"])
        print(f"[{ctx.channel.name}] Question skipped by {ctx.author.name}")
        channel_state['current_question'] = None
    else:
      await ctx.send("You must be a moderator to use this command.")

  @commands.command()
  async def cooldown(self, ctx: commands.Context, cooldown: int = None):
    channel_state = self.get_channel_state(ctx.channel.name)

    if (ctx.author.is_mod) or (ctx.author.name == 'itssport'):
      if cooldown is not None:
        if cooldown >= 0:
          set_channel_cooldown(ctx.channel.name, cooldown)
          await ctx.send(
            f"Cooldown set to {cooldown} seconds for {ctx.channel.name}.")
        else:
          await ctx.send("Cooldown may not be negative.")
      else:
        channel_name = ctx.channel.name

        if 'last_trivia' not in channel_state:
          channel_state['last_trivia'] = 0

        cooldown = get_channel_cooldown(channel_name)
        time_since_last_trivia = time.time() - channel_state['last_trivia']

        cooldown_remaining = cooldown - int(time_since_last_trivia)
        if cooldown_remaining < 0:
          cooldown_remaining = 0

        await ctx.send(
          f"{ctx.channel.name}'s trivia cooldown is set to {get_channel_cooldown(ctx.channel.name)} seconds. [{cooldown_remaining}s remaining]"
        )
    else:
      channel_name = ctx.channel.name

      if 'last_trivia' not in channel_state:
        channel_state['last_trivia'] = 0

      cooldown = get_channel_cooldown(channel_name)
      time_since_last_trivia = time.time() - channel_state['last_trivia']
      await ctx.send(
        f"{ctx.channel.name}'s trivia cooldown is set to {get_channel_cooldown(ctx.channel.name)} seconds. [{cooldown - int(time_since_last_trivia)}s remaining]"
      )

  @commands.command()
  async def category(self, ctx: commands.Context, category: str = None):
    channel_name = ctx.channel.name

    if (ctx.author.is_mod) or (ctx.author.name == 'itssport'):
      if not category == None:
        if "," in category:
          split_categories = category.split(",")
        else:
          split_categories = [category]
        new_categories = ""
        invalid_categories = ""

        for i in split_categories:
          if i.upper() in CATEGORIES:
            new_categories += f" {i.upper()}"
          else:
            invalid_categories += f" {i.upper()}"

        if "ALL" in new_categories:
          new_categories = "ALL"
          invalid_categories = ""

        print(f"[{ctx.channel.name}] Category update: {new_categories}")

        if not invalid_categories == "":
          await ctx.send(
            f"The following categories were invalid: {invalid_categories}")

        if not new_categories == "":
          set_channel_category(ctx.channel.name, new_categories)

        print(
          f"[{channel_name}] Categories set to {get_channel_category(channel_name)}"
        )
        await ctx.send(
          f"Categories set to {get_channel_category(channel_name)} for {ctx.channel.name}."
        )
      else:
        category = get_channel_category(channel_name)
        await ctx.send(
          f"{ctx.channel.name}'s trivia categories are set to {get_channel_category(ctx.channel.name)}."
        )
    else:
      category = get_channel_category(channel_name)
      await ctx.send(
        f"{ctx.channel.name}'s trivia categories are set to {get_channel_category(ctx.channel.name)}."
      )

  @commands.command()
  async def categories(self, ctx: commands.Context):
    all_cats = ""
    for category in CATEGORIES:
      all_cats += f"{category}, "
    all_cats = all_cats[:-2]

    await ctx.send(f"Available categories: {all_cats}.")

  @commands.command()
  async def help(self, ctx: commands.Context):
    await ctx.send(
      "To view a list of commands/functionality, visit: https://www.itssport.co/twiviabot"
    )

  @commands.command()
  async def announce(self, ctx: commands.Context):
    if ctx.author.name == 'itssport':
      announcement = ctx.message.content[10:]
      for channel_name in self.channels:
        channel = self.get_channel(channel_name)
        await channel.send(f"[ANNOUNCEMENT] {announcement}")
      await ctx.send("Announcement sent to all channels.")
      print("Announcement sent to all channels.")
    else:
      await ctx.send("You do not have permission to perform this command.")


def main():
  setup_db()
  channels = get_saved_channels()
  if 'twiviabot' not in channels:
    add_channel('twiviabot')
    channels = get_saved_channels()
    print("[STARTUP] twiviabot not found in channels list on boot, re-added.")
  print("[STARTUP] loading channels...")
  twiviaBot = Bot(channels)
  print("[STARTUP] starting bot...")
  twiviaBot.run()
  print("[STARTUP] bot started.")


if __name__ == "__main__":
  main()
