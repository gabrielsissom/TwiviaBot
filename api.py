import requests
import json
import html

def get_question():
    api_url = 'https://opentdb.com/api.php?amount=1&type=multiple'
    response = requests.get(api_url)
    
    if response.status_code == requests.codes.ok:
        parsed_response = json.loads(response.text)
        question_data = parsed_response["results"]
        return question_data
    else:
        print("Error:", response.status_code, response.text)
        return 

def format_question(question):
    formatted_question = html.unescape(question['question'])
    formatted_answer = html.unescape(question['correct_answer'])
    question['question'] = formatted_question
    question['answer'] = formatted_answer
    return question

question = get_question()[0]
print(question)

while "WHICH OF" in question["question"].upper():
    print("Got new question")
    question = get_question()[0]
    print(question)

question = format_question(question)
print(question['question'])
print(question['correct_answer'])