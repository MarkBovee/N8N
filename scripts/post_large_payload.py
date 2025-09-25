import requests

b = {'model':'gpt-4.1','messages':[{'role':'user','content':'A'*500000}]}
resp = requests.post('http://localhost:11434/v1/chat/completions', json=b, timeout=120)
print('STATUS', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text[:1000])
