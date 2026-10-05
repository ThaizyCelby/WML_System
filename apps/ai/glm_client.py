# apps/ai/glm_client.py
import logging
import time

import jwt
from openai import OpenAI
from django.conf import settings

logger = logging.getLogger(__name__)


def _build_zhipu_token(api_key: str) -> str:
    """
    Convert a BigModel API key (<id>.<secret>) into a signed JWT.

    BigModel's /api/paas/v4/* endpoints require this JWT as the Bearer
    token. Passing the raw key returns 401
    '令牌已过期或验证不正确'.
    """
    try:
        key_id, secret = api_key.split('.', 1)
    except ValueError as exc:
        raise ValueError(
            "GLM_API_KEY must be in the format '<id>.<secret>' from BigModel."
        ) from exc

    now_ms = int(time.time() * 1000)
    payload = {
        'api_key': key_id,
        'exp': now_ms + 3_600_000,  # 1 hour
        'timestamp': now_ms,
    }
    headers = {'alg': 'HS256', 'sign_type': 'SIGN'}

    return jwt.encode(payload, secret, algorithm='HS256', headers=headers)


class GLMClient:
    """BigModel GLM API client using a signed JWT for auth."""

    def __init__(self):
        config = settings.AI_PROVIDERS.get('glm', {})
        self.api_key = config.get('api_key')
        self.base_url = config.get('base_url', 'https://open.bigmodel.cn/api/paas/v4')
        self.model = config.get('model', 'glm-4.7-flash')
        self.timeout = config.get('timeout_seconds', 45)
        self.temperature = config.get('temperature', 0.05)
        self.max_tokens = config.get('max_tokens', 4096)

        if not self.api_key:
            raise ValueError("GLM_API_KEY is not configured.")

        self.client = OpenAI(
            api_key=self.api_key,   # placeholder; real auth is the token below
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def _auth_headers(self) -> dict:
        return {'Authorization': f'Bearer {_build_zhipu_token(self.api_key)}'}

    def chat_completion(self, messages, **kwargs):
        try:
            response = self.client.chat.completions.create(
                model=kwargs.get('model', self.model),
                messages=messages,
                temperature=kwargs.get('temperature', self.temperature),
                max_tokens=kwargs.get('max_tokens', self.max_tokens),
                extra_headers=self._auth_headers(),
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"GLM API error: {e}")
            raise