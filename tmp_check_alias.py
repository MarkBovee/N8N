from proxy_server.n8n_discovery import ToolDiscovery
import asyncio

async def run():
    td = ToolDiscovery()
    res = await td.get('Joke_API')
    print('Result for Joke_API:', res)

if __name__ == '__main__':
    asyncio.run(run())
