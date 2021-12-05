import asyncio
import json
import logging
from typing import Any, Optional, Union

import aioredis
from aioredis import Redis

import config

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, prefix: str) -> None:
        self._redis: Redis = aioredis.from_url(
            f"redis://:{config.REDIS_PASSWORD}@{config.REDIS_HOST}:" +
            f"{config.REDIS_PORT}",
            encoding="utf-8",
            decode_responses=True
        )

        self._prefix = prefix

    async def add_in_sorted_set(self,
                                key: str,
                                value: Any,
                                score: Union[int, float]):
        str_value = json.dumps(value)
        key = f"{self._prefix}:sorted_set"
        mapping: dict = {str_value: score}
        await self._redis.zadd(key, mapping)

    async def pop_min_from_sorted_set(self,
                                      key: str) -> Optional[dict]:
        key = f"{self._prefix}:sorted_set"
        values = await self._redis.zpopmin(key)

        if not values:
            return None

        value_and_score = values[0]
        value = value_and_score[0]
        return json.loads(value)


async def test():
    storage = Storage("test_posts")
    post_time = 123456786

    post = {'post_time': 123456784,
            'chat_id': 123,
            'message_id': 321,
            'user_id': 456}

    await storage.add_in_sorted_set("posts_queue", post, post_time)
    post_get = await storage.pop_min_from_sorted_set("posts_queue")
    print(post_get)

if __name__ == '__main__':
    asyncio.run(test())
