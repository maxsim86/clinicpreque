# services/sse_manager.py
import asyncio
from typing import Set

class SSEManager:
    def __init__(self):
        self._listeners: Set[asyncio.Queue] = set()

    async def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._listeners.discard(q)

    async def broadcast_refresh(self):
        """Menghantar signal kemas kini kepada semua pelayar yang disambungkan"""
        for q in list(self._listeners):
            await q.put("refresh")

sse_manager = SSEManager()