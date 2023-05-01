import requests
import random

categories = [
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
api_url = 'https://api.api-ninjas.com/v1/trivia?category={}'.format(random.choice(categories))
response = requests.get(api_url, headers={'X-Api-Key': 'eA8ya6wbQP2nFIA3Z859Zw==RKDSp8A0PtOmArFY'})
if response.status_code == requests.codes.ok:
    print(response.text)
else:
    print("Error:", response.status_code, response.text)