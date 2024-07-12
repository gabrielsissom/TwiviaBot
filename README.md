# TwiviaBot

A trivia game bot for your Twitch chat. To get started, visit [TwiviaBot's channel](https://www.twitch.tv/twiviabot) and use the %join command in its chat. 

![Join Image](/images/join.png)

## Commands:

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

Want to contribute to [TwiviaBot's question database](https://docs.google.com/spreadsheets/d/157Gb7JkwZvq26bz_wJVCn4x3H-iqNZ59/edit?usp=sharing&ouid=111078275511657347073&rtpof=true&sd=true)?

Bot made using [TwitchIO](https://twitchio.dev/en/latest/index.html).
