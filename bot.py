from twitchio.ext import commands
import os
import random
from asyncio import sleep
import json
import requests

def load_scores():
    with open("scores.json", "r") as file:
        return json.load(file)

def save_scores(scores):
    with open("scores.json", "w") as file:
        json.dump(scores, file, indent=4)

def add_score(username, points):
    scores = load_scores()
    if username in scores:
        scores[username] += points
    else:
        scores[username] = points
    save_scores(scores)

def get_score(username):
    scores = load_scores()
    return scores.get(username, 0)


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=os.environ['TMI_TOKEN'],
            client_id=os.environ['CLIENT_ID'],
            nick=os.environ['BOT_NICK'],
            prefix=os.environ['BOT_PREFIX'],
            initial_channels=[os.environ['CHANNEL']]
        )

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
        self.current_question = None

    async def event_ready(self):
        print(f'Logged in as | {self.nick}')
        print(f'User id is | {self.user_id}')

    async def event_message(self, message):
        if message.echo:
            return

        print(message.author)
        print(message.content)

        if self.current_question and message.content.strip().lower() == self.current_question['answer'].lower():
            user = message.author.name
            add_score(user, 1)
            await message.channel.send(f"{user} answered correctly! Their score is now {get_score(user)}.")
            self.current_question = None

        await self.handle_commands(message)

    @commands.command()
    async def hello(self, ctx: commands.Context):
        await ctx.send(f'Hello {ctx.author.name}!')

    @commands.command()
    async def alexa(self, ctx: commands.Context):
        await ctx.send(f'BITCH')

    @commands.command()
    async def trivia(self, ctx: commands.Context):
        if not self.current_question:
            response = requests.get('https://api.api-ninjas.com/v1/trivia?category={}'.format(random.choice(self.categories)), headers={'X-Api-Key': 'eA8ya6wbQP2nFIA3Z859Zw==RKDSp8A0PtOmArFY'})
            parsed_response = json.loads(response.text)
            question_data = parsed_response[0]
            self.current_question = {
                "category": question_data["category"],
                "question": question_data["question"],
                "answer": question_data["answer"],
            }
            print(f"Triva Game Started: Q: " + self.current_question["question"] + " A: " + self.current_question["answer"])

            if response.status_code == requests.codes.ok:
                await ctx.send(f"Trivia question: " + self.current_question["question"])
                await sleep(30)  # Users have 30 seconds to answer
            else:
                await ctx.send("Error:", response.status_code, response.text)

            if self.current_question:  # If the question hasn't been answered yet
                await ctx.send("Time's up! The correct answer was: " + self.current_question["answer"])
                self.current_question = None
        else:
            await ctx.send("A trivia question is already active!")
    
    @commands.command()
    async def points(self, ctx: commands.Context):
        await ctx.send(f'The current points of {ctx.author.name} is ' + str(get_score(ctx.author.name)))

twiviaBot = Bot()
twiviaBot.run()
