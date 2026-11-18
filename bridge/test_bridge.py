"""Testy mostu OPC UA -> MQTT bez sterownika. Uruchomienie: python bridge/test_bridge.py (albo pytest)."""
from asyncua import ua

import opcua_mqtt_bridge as bridge
from opcua_mqtt_bridge import missing_signals, publish_status


def test_wszystkie_zmienne_sa():
    assert missing_signals(["a", "b"], [11, 12]) == []


def test_brak_jednej_zmiennej():
    bad = ua.StatusCode(ua.StatusCodes.BadNodeIdUnknown)
    assert missing_signals(["a", "b", "c"], [11, bad, 13]) == ["b"]


def test_brak_wszystkich():
    bad = ua.StatusCode(ua.StatusCodes.BadNodeIdUnknown)
    assert missing_signals(["a", "b"], [bad, bad]) == ["a", "b"]


def test_status_tylko_przy_zmianie():
    class MQ:
        sent = []

        def publish(self, topic, payload, **kw):
            self.sent.append(payload)
    bridge._last_status = None
    mq = MQ()
    for s in ["offline", "online", "offline", "offline", "offline", "online"]:
        publish_status(mq, s)
    assert mq.sent == ["offline", "online", "offline", "online"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
