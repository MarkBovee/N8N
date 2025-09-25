import requests
s = 'S'*2364
b = {'model':'gpt-4.1','messages':[{'role':'system','content':s},{'role':'user','content':'Hello'}]}
resp = requests.post('http://localhost:11434/v1/chat/completions', json=b, timeout=120)
print('STATUS', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text[:2000])
