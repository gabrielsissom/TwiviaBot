# TwiviaBot

A trivia game bot for your Twitch chat. To get started, visit [TwiviaBot's channel](https://www.twitch.tv/twiviabot) and use the %join command in its chat. 

![Join Image](/images/join.png)



# TwiviaBot 2.0 Patch Notes:


## IMPORTANT: Many of the changes detailed below are a WORK IN PROGRESS, and may not work for every question. The questions are being updated over time to support this functionality. You can report incorrect/broken questions in my [Discord server](https://www.discord.gg/hMcbSTFCnU)


## Multi-correct answers:

  - Questions can now have multiple correct answers. This enables some new question types, as well as some quality of life changes.
  - Answers that have multiple spellings will accept other variants. 
  - Answers that are numbers like '2' will also accept 'two' and vice versa.
  ![Example](/images/two.png)
  - Questions may ask for one of many possible answers.
  ![Example](/images/garlic.png)


## NEW Questions and Categories: 
  - A new set of 45,000+ questions are in the process of being added/validated. 
  - Categories are being re-worked and improved, so ensure you double-check your channel's set categories using %category. (7 categories at launch, 9 more coming)
  - Note: the %category command has been slightly reworked as well, read more on that below.
  - 

## Contribution:
  - All TwiviaBot Questions are now being hosted online in a [Google Spreadsheet](https://docs.google.com/spreadsheets/d/1PJoXgEcnBGiFa60_I-YvuWdb9PpnXENzsj_WAoSTmNQ/edit?usp=sharing) where users can contribute/comment. 
  - If you have an issue with a specific question or two, you can open the [Trivia Sheet](https://docs.google.com/spreadsheets/d/1PJoXgEcnBGiFa60_I-YvuWdb9PpnXENzsj_WAoSTmNQ/edit?usp=sharing) and leave a comment on the question. (use ctrl + f to help)
  - If you'd like to contribute to trivia, you can submit your question via [Discord](https://www.discord.gg/hMcbSTFCnU). 
  - If you'd like to contribute a LOT more than just a few questions or help validate question data, you can also inquiry about edit permissions in the [Discord server](https://www.discord.gg/hMcbSTFCnU). 

end of patch notes



# Commands:

### %join - Makes TwiviaBot join your channel.
 - Only works in [TwiviaBot's Channel](https://www.twitch.tv/twiviabot).
 - Ensure you `/mod TwiviaBot` in your channel so the bot will function properly.

### %part - Makes TwiviaBot leave your channel.
 - Only works in [TwiviaBot's Channel](https://www.twitch.tv/twiviabot).
 - Does **not** remove points, leaderboard, or cooldown settings.

### %trivia - Starts a trivia game in the channel.
- Optional: `%trivia [category]`
- A trivia game may be started by any channel member.
- Answers to trivia questions must be above a 90% match to be counted as correct.
- Answers to trivia questions above an 80% match will be announced as 'close'.

### %points - Displays the total points of a user in the current channel.
- Points are tracked separately in different Twitch channels.

### %leaderboard - Displays the top 5 users with the most points in the current channel.
- Points are tracked separeately in different Twitch channels, so leaderboards will also be independent.

### %game <pause|resume|new> - Pauses the game in the current channel.
- Only the **channel owner** may pause, resume, or start a new game.
- (pause/resume) Points are maintained but no new questions can be started while game is paused.
- (new) Points are reset to 0 for all users in current channel only.

### %skip - Skips the current trivia game question.
- Only the **channel owner** or a **moderator** of the channel may skip a question.
- Does **not** reset the cooldown set for the channel. 

### %cooldown - Displays/Modifies the amount of time before a new trivia game may be started.
- To modify a channel's cooldown, use the command `%cooldown [time]` where `[time]` is a number of seconds. ex: `%cooldown 300` (5 minute cooldown)
- Only the **channel owner** or a **moderator** of the channel may modify the channel cooldown. For all other users, the command will display the total and remaining cooldown for the trivia game. 

### %category - Displays/Modifies the trivia question categories for the channel.
- To add or remove a category, use the command `%category [category]`.
- Only the **channel owner** or a **moderator** of the channel may modify the channel categories. For all other users, the command will display the channel's selected categories. 

### %categories - Displays a list of all selectable categories.

## Resources:

Want to contribute to [TwiviaBot's question database](https://docs.google.com/spreadsheets/d/1PJoXgEcnBGiFa60_I-YvuWdb9PpnXENzsj_WAoSTmNQ/edit?usp=sharing)?

Bot made using [TwitchIO](https://twitchio.dev/en/latest/index.html).
