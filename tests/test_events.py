from __future__ import annotations

import unittest

from core.events import EventBus


class EventBusTests(unittest.TestCase):
    def test_publish_delivers_payload_to_subscribers(self) -> None:
        bus = EventBus()
        received: list[object] = []
        bus.subscribe("exercise.completed", received.append)

        bus.publish("exercise.completed", {"score": 5})

        self.assertEqual(received, [{"score": 5}])

    def test_unsubscribe_stops_delivery(self) -> None:
        bus = EventBus()
        received: list[object] = []
        callback = received.append
        bus.subscribe("event", callback)
        bus.unsubscribe("event", callback)
        bus.publish("event", "ignored")

        self.assertEqual(received, [])


if __name__ == "__main__":
    unittest.main()
