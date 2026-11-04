"""Provider adapters. No external endpoint or model is silently substituted."""
import asyncio
import json
import time
import httpx
from fastapi import HTTPException
from .config import settings
from .security import cipher, normalize_api_key

PROVIDERS = ('openai', 'anthropic', 'gemini', 'groq', 'deepseek', 'ollama', 'compatible')
failures: dict[str, tuple[int, float]] = {}


class Gateway:
    def __init__(self, connection):
        self.provider = connection.provider
        self.key = normalize_api_key(cipher().decrypt(connection.encrypted_key.encode()).decode(), required=self.provider != 'ollama')
        self.root = getattr(settings, f'{self.provider}_url', '').rstrip('/')
        if not self.root:
            raise HTTPException(503, 'Provider endpoint is not configured by the administrator')
        self.headers = {'Authorization': f'Bearer {self.key}'} if self.key else {}
        if self.provider == 'anthropic':
            self.headers = {'x-api-key': self.key, 'anthropic-version': '2023-06-01'}

    async def request(self, method, path, body=None):
        count, opened = failures.get(self.root, (0, 0))
        if count >= 3 and time.monotonic() - opened < 60:
            raise HTTPException(503, 'Provider circuit open; retry after one minute')
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=10), follow_redirects=False, trust_env=False) as client:
            for attempt in range(3):
                try:
                    response = await client.request(method, self.root + path, headers=self.headers, json=body)
                    if response.status_code == 401:
                        provider = {'openai': 'OpenAI', 'anthropic': 'Anthropic', 'gemini': 'Google Gemini', 'groq': 'Groq', 'deepseek': 'DeepSeek', 'ollama': 'Ollama', 'compatible': 'Your provider'}.get(self.provider, 'Your provider')
                        raise HTTPException(422, f'{provider} rejected the API key (401). In AI connections, choose Update key and enter a valid {provider} API key, then Discover models. Changing the model does not fix an authentication failure.')
                    if response.status_code == 429 or response.status_code >= 500:
                        response.raise_for_status()
                    if response.status_code >= 400:
                        raise HTTPException(502, f'Provider rejected request ({response.status_code}); check key, model and capabilities')
                    if len(response.content) > 4_000_000:
                        raise HTTPException(502, 'Provider response exceeds limit')
                    failures.pop(self.root, None)
                    return response.json()
                except (httpx.HTTPError, ValueError):
                    if attempt == 2:
                        failures[self.root] = (count + 1, time.monotonic())
                        raise HTTPException(502, 'Provider unavailable; no changes were applied')
                    await asyncio.sleep(0.5 * 2 ** attempt)

    async def models(self):
        if self.provider == 'ollama':
            data = await self.request('GET', '/api/tags')
            return [m['name'] for m in data.get('models', [])]
        data = await self.request('GET', '/v1/models' if self.provider == 'anthropic' else '/models')
        return sorted(m['id'] for m in data.get('data', []))

    async def complete(self, model, messages, tools=None):
        if self.provider == 'anthropic':
            system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
            converted = []
            for msg in messages:
                if msg['role'] == 'system':
                    continue
                if msg['role'] == 'tool':
                    converted.append({'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': msg['tool_call_id'], 'content': msg['content']}]})
                elif msg.get('tool_calls'):
                    blocks = ([{'type': 'text', 'text': msg['content']}] if msg.get('content') else [])
                    blocks += [{'type': 'tool_use', 'id': c['id'], 'name': c['function']['name'], 'input': json.loads(c['function']['arguments'])} for c in msg['tool_calls']]
                    converted.append({'role': 'assistant', 'content': blocks})
                else:
                    converted.append(msg)
            body = {'model': model, 'system': system, 'messages': converted, 'max_tokens': 4096}
            if tools:
                body['tools'] = [{'name': t['function']['name'], 'description': t['function']['description'], 'input_schema': t['function']['parameters']} for t in tools]
            data = await self.request('POST', '/v1/messages', body)
            content = '\n'.join(b['text'] for b in data['content'] if b['type'] == 'text')
            calls = [{'id': b['id'], 'type': 'function', 'function': {'name': b['name'], 'arguments': json.dumps(b['input'])}} for b in data['content'] if b['type'] == 'tool_use']
            return {'role': 'assistant', 'content': content, **({'tool_calls': calls} if calls else {})}, data.get('usage', {})
        if self.provider == 'ollama':
            body = {'model': model, 'messages': messages, 'stream': False, 'options': {'num_predict': 4096}}
            if tools:
                body['tools'] = tools
            data = await self.request('POST', '/api/chat', body)
            message = data['message']
            for i, call in enumerate(message.get('tool_calls', [])):
                call.setdefault('id', f'call_{i}')
                call.setdefault('type', 'function')
                if isinstance(call['function']['arguments'], dict):
                    call['function']['arguments'] = json.dumps(call['function']['arguments'])
            return message, {'input_tokens': data.get('prompt_eval_count', 0), 'output_tokens': data.get('eval_count', 0)}
        body = {'model': model, 'messages': messages, 'max_tokens': 4096}
        if tools:
            body['tools'] = tools
        data = await self.request('POST', '/chat/completions', body)
        return data['choices'][0]['message'], {'input_tokens': data.get('usage', {}).get('prompt_tokens', 0), 'output_tokens': data.get('usage', {}).get('completion_tokens', 0)}
