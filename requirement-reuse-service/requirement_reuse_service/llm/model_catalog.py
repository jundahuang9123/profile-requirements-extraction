"""Read provider model IDs without inference or credential-bearing diagnostics."""
import httpx


def model_rows(config):
    if config.provider == 'mock':
        return [{'id': 'mock-model'}]
    if config.provider == 'disabled':
        raise ValueError('Select and save a model provider first.')
    anthropic = config.provider == 'anthropic'
    url = 'https://api.anthropic.com/v1/models' if anthropic else f"{(config.base_url or '').rstrip('/')}/models"
    headers = ({'x-api-key': config.api_key or '', 'anthropic-version': '2023-06-01'}
               if anthropic else {'Authorization': f'Bearer {config.api_key}'} if config.api_key else {})
    headers.update(config.extra_headers)
    rows, params = [], {}
    try:
        for _ in range(20):
            response = httpx.get(url, headers=headers, timeout=8.0, **({'params': params} if params else {}))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ValueError('Invalid model catalogue.')
            rows.extend(row for row in payload['data'] if isinstance(row, dict) and isinstance(row.get('id'), str))
            if not anthropic or not payload.get('has_more'):
                return rows
            cursor = payload.get('last_id')
            if not isinstance(cursor, str) or not cursor or cursor == params.get('after_id'):
                raise ValueError('Invalid model catalogue cursor.')
            params = {'after_id': cursor}
        raise ValueError('Model catalogue exceeded the page limit.')
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ValueError('Could not load provider model list (' + type(exc).__name__ +
                         '). Check endpoint, credentials and availability; no run was created.') from None


def text_generation_model(row):
    # Gateways often expose embedding IDs alongside chat models. Do not infer
    # unsupported capabilities for otherwise unknown IDs.
    kind = str(row.get('type', row.get('task', ''))).lower()
    return ('embed' not in row['id'].lower() and 'rerank' not in row['id'].lower()
            and kind not in {'embedding', 'embeddings', 'reranking'})


def generation_models(config):
    return sorted({row['id'] for row in model_rows(config) if text_generation_model(row)})
