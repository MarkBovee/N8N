import requests

b = {
    'model': 'gpt-4.1',
    'messages': [{'role':'user','content':'Call a tool if available'}],
    'tools': [
        {'type':'function','function':{'name':'add','description':'Add two numbers','parameters':{}}},
        {'type':'function','function':{'name':'echo','description':'Echo text','parameters':{}}}
    ],
    'stream': False
}
resp = requests.post('http://localhost:11434/v1/chat/completions', json=b, timeout=120)
print('STATUS', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text[:2000])
