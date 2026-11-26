"""In-memory mailboxes: the only state the relay has. A mailbox id is a random capability
known to one broker and its paired phone; each slot holds the latest message (ciphertext the
relay cannot read) until it expires. Readers long-poll for a newer sequence number."""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

BOX_ID = re.compile(r"[A-Za-z0-9_-]{16,64}")
SLOTS = {"a", "b", "req", "ans"}     # pairing: a (phone->broker), b (broker->phone); approvals: req, ans
MAX_BYTES = 64 * 1024
MAX_KEYS = 2000                      # stored messages, and separately, waiting readers
TTL_S = 300


@dataclass
class Message:
    seq: int
    data: bytes
    expires: float


class Mailboxes:
    def __init__(self, ttl: float = TTL_S):
        # Starts from the clock (ms) so sequence numbers keep growing across relay restarts:
        # phones remember the last one they saw.
        self.ttl, self.counter = ttl, int(time.time() * 1000)
        self.messages: dict[tuple, Message] = {}
        self.waiting: dict[tuple, list] = {}       # key -> [event, readers waiting on it]

    @staticmethod
    def valid(box: str, slot: str) -> bool:
        return bool(BOX_ID.fullmatch(box)) and slot in SLOTS

    def _purge(self) -> None:
        now = time.time()
        for k in [k for k, m in self.messages.items() if m.expires < now]:
            del self.messages[k]

    def put(self, box: str, slot: str, data: bytes) -> int:
        if len(data) > MAX_BYTES:
            raise ValueError("message too large")
        self._purge()
        key = (box, slot)
        if key not in self.messages and len(self.messages) >= MAX_KEYS:
            raise ValueError("relay full")
        self.counter += 1                  # global, so a sequence never goes backwards
        self.messages[key] = Message(self.counter, data, time.time() + self.ttl)
        if key in self.waiting:
            self.waiting.pop(key)[0].set()
        return self.counter

    async def get(self, box: str, slot: str, after: int, wait: float) -> Message | None:
        """The latest message if its seq > after, waiting up to `wait` s for one to arrive."""
        key, deadline = (box, slot), time.time() + wait
        while True:
            m = self.messages.get(key)
            if m and m.seq > after and m.expires >= time.time():
                return m
            left = deadline - time.time()
            if left <= 0:
                return None
            if key not in self.waiting and len(self.waiting) >= MAX_KEYS:
                raise ValueError("relay busy")
            w = self.waiting.setdefault(key, [asyncio.Event(), 0])
            w[1] += 1
            try:
                await asyncio.wait_for(w[0].wait(), left)
            except asyncio.TimeoutError:
                return None
            finally:                       # forget the event only once no reader still uses it
                w[1] -= 1
                if w[1] == 0 and self.waiting.get(key) is w:
                    del self.waiting[key]
