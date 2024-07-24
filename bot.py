import os, random, asyncio, psycopg2, time, requests, sys, threading
from twitchio.ext import commands
from difflib import SequenceMatcher

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

#GOOGLE API
SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

TRIVIA_SPREADSHEET_ID = "1PJoXgEcnBGiFa60_I-YvuWdb9PpnXENzsj_WAoSTmNQ"

#GLOBAL CONSTANTS
DATABASE_URL = os.environ['DATABASE_URL']
DISCORD_WEBHOOK_URL = os.environ['DISCORD_WEBHOOK_URL']
TRIVIA_FILE_NAME = 'trivia.xlsx'

#GLOBAL SETTINGS
HINT_CHARS_REVEALED = 0.4  # Scale between 0.0 and 1.0 where 1 reveals 100% of the answer.
TIME_BEFORE_HINT = 20  # Seconds before a hint is given.
TIME_BEFORE_ANSWER = 15  # Seconds (after hint is given) before the answer is revealed.
ANSWER_CLOSE = 0.8  # Scale between 0.0 and 1.0 where 1.0 is an exact match. Announces that a user is close to the correct answer.
ANSWER_CORRECTNESS = 0.9  # Scale between 0.0 and 1.0 where 1.0 is an exact match.
CORRECT_ANSWER_VALUE = 1  # Number of points to award for a correct question.
BOT_PREFIX = '%'  # Token required before each command

REVEAL_IN_HINT = ["-", ",", "$", "%", ".", "/", "'", '"', '&', '(', ')']

CATEGORIES = {
  0: "General",
  1: "Science & Nature",
  2: "Geography",
  3: "Entertainment",
  4: "Sports & Leisure",
  5: "Music",
  15: "Genshin Impact"
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
                 ids INTEGER[],
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


class DiscordWebhookStream:
  def __init__(self, webhook_url, batch_interval=2):
      self.webhook_url = webhook_url
      self.buffer = ""
      self.lock = threading.Lock()
      self.batch_interval = batch_interval
      self.stop_event = threading.Event()
      self.thread = threading.Thread(target=self._send_batches)
      self.thread.start()

  def write(self, message):
      with self.lock:
          self.buffer += message

  def flush(self):
      with self.lock:
          self._send_message(self.buffer)
          self.buffer = ""

  def _send_message(self, message):
      if message.strip():
          payload = {
              'content': f"```{message}```",
              'username': 'TwiviaBot',
              'avatar_url': 'https://i.imgur.com/3qA9RkH.png'
          }
          try:
              requests.post(self.webhook_url, json=payload)
          except requests.RequestException as e:
              print(f"Failed to send message to Discord: {e}", file=sys.__stderr__)

  def _send_batches(self):
      while not self.stop_event.is_set():
          time.sleep(self.batch_interval)
          with self.lock:
              if self.buffer:
                  self._send_message(self.buffer)
                  self.buffer = ""

  def close(self):
      self.stop_event.set()
      self.thread.join()
      self.flush()

# Usage
webhook_url = DISCORD_WEBHOOK_URL

# Set custom streams
sys.stdout = DiscordWebhookStream(webhook_url)
sys.stderr = DiscordWebhookStream(webhook_url)

# Ensure streams are closed properly on exit
import atexit
atexit.register(sys.stdout.close)
atexit.register(sys.stderr.close)


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

#Overwrites everything in the 'ids' collumn with new integer array (new_categories)
# new_categories must be an array of integers
def set_channel_category(channel_name, new_categories):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute(
      '''
      UPDATE channel_categories
      SET ids = %s
      WHERE channel = %s
      ''', (new_categories, channel_name))
  conn.commit()
  c.close()
  conn.close()

#Appends a new integer to the 'ids' collumn
# new_category_id must be an integer
def add_channel_category(channel_name, new_category_id: int):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('SELECT ids FROM channel_categories WHERE channel = %s', (channel_name,))
  result = c.fetchone()

  if result:
      # Channel exists, update the ids array
      existing_ids = result[0]
      if new_category_id not in existing_ids:
          existing_ids.append(new_category_id)
          c.execute('UPDATE channel_categories SET ids = %s WHERE channel = %s', (existing_ids, channel_name))
  else:
      # Channel does not exist, create a new entry
      c.execute('INSERT INTO channel_categories (channel, ids) VALUES (%s, %s)', (channel_name, [new_category_id]))

  conn.commit()
  c.close()
  conn.close()


def remove_channel_category(channel_name, value_to_remove):
  """
  Removes a specific value from the 'ids' array in the channel_categories table.

  Args:
      channel_name: The name of the channel.
      value_to_remove: The integer value to remove from the 'ids' array.
  """
  conn = get_db_connection()
  c = conn.cursor()
  c.execute("""
    UPDATE channel_categories
    SET ids = array_remove(ids, %s)
    WHERE channel = %s
  """, (value_to_remove, channel_name))
  conn.commit()
  c.close()
  conn.close()


def get_channel_category_ids(channel_name):
  conn = get_db_connection()
  c = conn.cursor()
  c.execute('SELECT ids FROM channel_categories WHERE channel = %s',
            (channel_name, ))
  result = c.fetchone()
  c.close()
  conn.close()
  if result:
    return result[0]
  else:
    return None

def get_channel_categories(channel_name):
  channel_category_ids = get_channel_category_ids(channel_name)
  if channel_category_ids:
    channel_categories = []
    for id in channel_category_ids:
      channel_categories.append(CATEGORIES[id])
    return channel_categories
  else:
    #returns None if no categories are set
    return None

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

  async def get_question(self, channel_name, precategory: str = None):
    
    categories = []

    # Use pre-determined category if provided
    if precategory != None:
      matched_category = None
      for key, value in CATEGORIES.items():
        if precategory.upper() == value.upper():
          matched_category = key
          break  # Exit the loop once a match is found

      if matched_category:
        categories.append(matched_category)
      else:
        # If no valid category is provided, use channel's category list
        check_for_none = get_channel_category_ids(channel_name)
        if check_for_none:
          categories.extend(check_for_none)
    else:
      # If category is not provided, use channel's category list
      check_for_none = get_channel_category_ids(channel_name)
      if check_for_none:
        categories.extend(check_for_none)

    # Select a random category from channel's categories
    if len(categories) > 0:
      selected_category_id = random.choice(categories)
      #temporary 70% chance of selecting the general category
      #since this category has 90% of the questions
      if 0 in categories:
        if random.randint(1, 100) <= 70:
          selected_category_id = 0
    else:
      selected_category_id = random.choice(list(CATEGORIES.keys()))
      #temporary 70% chance of selecting the general category
      #since this category has 90% of the questions
      if 0 in list(CATEGORIES.keys()):
        if random.randint(1, 100) <= 70:
          selected_category_id = 0

    service = build('sheets', 'v4', credentials=credentials)
    
    #select random row(question)
    range_name = f"'{CATEGORIES[selected_category_id]}'"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=TRIVIA_SPREADSHEET_ID, range=range_name)
        .execute()
    )

    values = result.get('values', [])

    if not values:
        print('No data found.')
        return None
    else:
        # Find the number of rows
        num_rows = len(values)

        # Select a random row
        random_row_index = random.randint(2, num_rows - 1)
        random_row = values[random_row_index]

        # Move elements to an array
        row_array = list(random_row)
    
    #Remove None values
    raw_question_data_array = [x for x in row_array if x is not None]
    
    #Create an array for answers
    usable_answers = [f"{raw_question_data_array[3]}".strip()]
    if len(raw_question_data_array) > 4:
      for i in range(4, len(raw_question_data_array)):
        usable_answers.append(f"{raw_question_data_array[i]}".strip())

    #Format question for return
    question_data = {'question_id': int(raw_question_data_array[0]), 'category': raw_question_data_array[1].strip(), 'question': raw_question_data_array[2].strip(), 'answer': usable_answers}
    
    return question_data

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
        answer = channel_state['current_question']["answer"][0]
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
                       channel_state['current_question']['answer'][0])
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
    self.update_channels_list()

  async def event_channel_joined(self, channel):
    self.update_channels_list()

  async def event_channel_left(self, channel):
    self.update_channels_list()

  def update_channels_list(self):
    self.channels_list = [channel for channel in self.connected_channels]

  async def event_message(self, message):
    #If message is from self, return
    if message.echo:
      return

    channel_state = self.get_channel_state(message.channel.name)

    if channel_state['current_question']:  #if a question is active
      user_answer = message.content.strip().lower()
      correct_answer_array = channel_state['current_question']['answer'] if channel_state['current_question'] else None

      #Check similarity between user answer and correct answers
      user_answer_similarity = 0
      for answer in correct_answer_array:
        check_similarity = similarity(user_answer, answer.lower())
        if check_similarity > user_answer_similarity:
          user_answer_similarity = check_similarity
        

      if (user_answer_similarity >= ANSWER_CLOSE) and (
          user_answer_similarity < ANSWER_CORRECTNESS):  #If user answers CLOSELY
        await message.channel.send(
          f"{message.author.name} is close! {round(user_answer_similarity * 100, 2)}% accurate."
        )

      if user_answer_similarity >= ANSWER_CORRECTNESS:  #If user answers CORRECTLY
        add_score(message.channel.name, message.author.name,
                  CORRECT_ANSWER_VALUE)
        print(  #console message
          f"[{message.channel.name}] {message.author.name} answered with {user_answer_similarity} accuracy."
        )
        await message.channel.send(  #chat message
          f"{message.author.name} answered with {round(user_answer_similarity * 100, 2)}% accuracy! Their score is now {get_score(message.channel.name, message.author.name)}. Answer: {channel_state['current_question']['answer'][0]}"
        )
        channel_state['current_question'] = None

    await self.handle_commands(message)


  # %trivia
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

    if time_since_last_trivia < cooldown:
      await ctx.send(
        f"Please wait {cooldown - int(time_since_last_trivia)} seconds before starting a new trivia."
      )
      return

    channel_state['last_trivia'] = time.time()

    if not channel_state[
        'current_question']:  # Checking if the current_question is None (i.e. no question is active)
      if not cat == None:  # If a category is provided
        category_choice = ctx.message.content[7:].strip().lower()
        question_data = await self.get_question(channel_name, category_choice)
      else:  # If a cateogry is not provided
        question_data = await self.get_question(channel_name)

      if question_data == None:  # If get_question returns None, API failed.
        print(f"[{channel_name}] Question failure: Question failed.")
        await ctx.send("Trivia failed. Try again.")
        return
        
      #Add trivia data to channel state
      channel_state['current_question'] = {
        "question_id": question_data['question_id'],
        "category": question_data["category"],
        "question": question_data["question"],
        "answer": question_data["answer"]
      }

      #Console question details
      print(
        f"[{ctx.channel.name}] Trivia Game Started by {ctx.author.name} [category: "
        + channel_state['current_question']['category'] + f"]: Q ({channel_state['current_question']['question_id']}): " +
        channel_state['current_question']["question"] + f" A: {channel_state['current_question']['answer']}")

      await ctx.send(
        f"[Category - {channel_state['current_question']['category']}] Question: "
        + channel_state['current_question']["question"])
      await self.check_answer(ctx)

      if channel_state[
          'current_question']:  # If the question hasn't been answered yet
        await ctx.send("Time's up! The correct answer was: " +
                       channel_state['current_question']["answer"][0])
        print(
          f"[{ctx.channel.name}] Time Up | A: {channel_state['current_question']['answer'][0]}"
        )
        channel_state['current_question'] = None
    else:
      await ctx.send("A trivia question is already active!")


  # %channels
  @commands.command()
  async def channels(self, ctx: commands.Context):
    if ctx.author.name == 'itssport':
      active_channels = sorted(get_saved_channels())
      channels_message = "TwiviaBot exists in: "
      for channel in active_channels:
        channels_message += (f'{channel}, ')
      print(channels_message)


  # %sub
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


  # %unsub
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


  # %join
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


  # %forcejoin
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


  # %part
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


  # %forcepart
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


  # %points
  @commands.command()
  async def points(self, ctx: commands.Context):
    await ctx.send(f'The current points of {ctx.author.name} is ' +
                   str(get_score(ctx.channel.name, ctx.author.name)))


  # %leaderboard
  @commands.command()
  async def leaderboard(self, ctx: commands.Context):
    top_users = get_top_users(ctx.channel.name)
    leaderboard_message = f"{ctx.channel.name}'s Trivia Leaderboard: \n"
    for idx, user in enumerate(top_users, start=1):
      leaderboard_message += f"{idx}. {user[0]} - {user[1]} points | \n"
    await ctx.send(leaderboard_message)


  # %game
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


  # %skip
  @commands.command()
  async def skip(self, ctx: commands.Context):
    channel_state = self.get_channel_state(ctx.channel.name)
    if ctx.author.is_mod or ctx.author.name == 'itssport':
      if not channel_state['current_question'] == None:
        await ctx.send(f"Question skipped. A: {channel_state['current_question']['answer'][0]}")
        print(f"[{ctx.channel.name}] Question skipped by {ctx.author.name}")
        channel_state['current_question'] = None
    else:
      await ctx.send("You must be a moderator to use this command.")


  # %cooldown
  @commands.command()
  async def cooldown(self, ctx: commands.Context, cooldown: int = None):
    channel_state = self.get_channel_state(ctx.channel.name)

    if (ctx.author.is_mod) or (ctx.author.name == 'itssport'):
      if cooldown is not None:
        if cooldown >= 0:
          if cooldown <= 1000000:
            set_channel_cooldown(ctx.channel.name, cooldown)
            await ctx.send(
              f"Cooldown set to {cooldown} seconds for {ctx.channel.name}.")
          else:
            await ctx.send("Cooldown may not be greater than 1,000,000 seconds.")
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


  # %category
  @commands.command()
  async def category(self, ctx: commands.Context, are_args: str = None):
    channel_name = ctx.channel.name

    if (ctx.author.is_mod) or (ctx.author.name == 'itssport'):
      if are_args:
        
        category_choice = ctx.message.content[9:].strip().lower()
        matched_category = None
        
        for key, value in CATEGORIES.items():
          if category_choice.upper() == value.upper():
            matched_category = key
            break  # Exit the loop once a match is found

        if matched_category != None:
          user_categories = get_channel_category_ids(channel_name)
          if user_categories and (matched_category in user_categories):
            remove_channel_category(channel_name, int(matched_category))
            await ctx.send(f"{CATEGORIES[matched_category]} has been removed from {ctx.channel.name}'s categories.")
          else:
            add_channel_category(channel_name, int(matched_category))
            await ctx.send(f"{CATEGORIES[matched_category]} has been added to {ctx.channel.name}'s categories.")
        else:
          await ctx.send(f"Invalid category: {category_choice}. To see a list of valid categories, use '%categories'.")
      else:
        are_any_cateogries = get_channel_categories(channel_name)
        
        if are_any_cateogries:
          await ctx.send(f"{ctx.channel.name}'s trivia categories are set to {are_any_cateogries}.")
        
        else:
          await ctx.send(f"{ctx.channel.name}'s trivia categories are not set; All categories will be used. Do '%category [category_name]' to set categories.")
          
    else:
      are_any_cateogries = get_channel_categories(channel_name)
      if are_any_cateogries:
        await ctx.send(f"{ctx.channel.name}'s trivia categories are set to {are_any_cateogries}.")
      else:
        await ctx.send(f"{ctx.channel.name}'s trivia categories are not set; All categories will be used. Do '%category [category_name]' to set categories.")


  # %categories
  @commands.command()
  async def categories(self, ctx: commands.Context):
    all_cats = ""
    for category in CATEGORIES.values():
      all_cats += f"{category}, "
    all_cats = all_cats[:-2]

    await ctx.send(f"Available categories: {all_cats}.")


  # %help
  @commands.command()
  async def help(self, ctx: commands.Context):
    await ctx.send(
      "To view a list of commands/functionality, visit: https://www.itssport.co/twiviabot"
    )

  # %announce
  @commands.command()
  async def announce(self, ctx: commands.Context):
    if ctx.author.name == 'itssport':
      message = ctx.message.content[10:]
      for channel in self.channels_list:
        try:
          await channel.send(f"[ANNOUNCEMENT] {message}")
        except:
          print(f"[{channel}] Could not send announcement.")
      await ctx.send("Announcement sent to all channels.")
      print("Announcement sent to all channels.")
    else:
      await ctx.send("You do not have permission to perform this command.")


def main():

  #Initialize DB if not already created
  setup_db()

  # Load channels into memory
  channels = get_saved_channels()

  # Ensure TwiviaBot is in the channels
  if 'twiviabot' not in channels:
    add_channel('twiviabot')
    channels = get_saved_channels()
    print("[STARTUP] twiviabot not found in channels list on boot, re-added.")

  # Initialize TwiviaBot
  print("[STARTUP] loading channels...")
  twiviaBot = Bot(channels)
  # Run TwiviaBot
  print("[STARTUP] starting bot...")
  twiviaBot.run()


if __name__ == "__main__":
  main()
