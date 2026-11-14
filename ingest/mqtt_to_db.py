#!/usr/bin/env python3
"""E3-06: zapis z MQTT do TimescaleDB – sygnały PLC (most E3-05) i zdarzenia z kamery (Jetson, E2-07).

Laptop, kontener `ingest` z infra/docker-compose.yml.

Tematy:
    linesight/plc/<zmienna>      {"t", "value", "t_src"}  -> plc_signal
    linesight/vision/events      zdarzenie zliczania       -> vision_event (time = t_cross)
    linesight/<plc|vision>/status  online/offline         -> link_status

Niezawodność:
- Sesja trwała (clean_session=False, stały client_id): gdy ingest nie działa, broker przechowuje
  wiadomości QoS 1 dla tej subskrypcji i oddaje je po powrocie.
- Wiadomość jest potwierdzana (PUBACK) dopiero po powrocie z on_message, czyli po zapisie do bazy.
  Gdy baza nie odpowiada, on_message czeka i ponawia zapis – nic nie przepada.
- Duplikaty (QoS 1, wiadomości retained po każdym połączeniu) odrzuca UNIQUE + ON CONFLICT DO NOTHING.
"""
import json
import os
import time

import paho.mqtt.client as mqtt
import psycopg
from psycopg.types.json import Jsonb

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
DB_DSN = os.environ.get("DB_DSN", "postgresql://linesight:linesight@localhost:5432/linesight")
RETRY_S = float(os.environ.get("RETRY_S", "5"))

SQL_SIGNAL = ("INSERT INTO plc_signal (time, name, value, t_src) "
              "VALUES (to_timestamp(%s), %s, %s, to_timestamp(%s)) ON CONFLICT DO NOTHING")
SQL_EVENT = ("INSERT INTO vision_event (time, t_decided, track_id, class, direction, clip, votes, raw) "
             "VALUES (to_timestamp(%s), to_timestamp(%s), %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING")
SQL_LINK = ("INSERT INTO link_status (time, source, online) "
            "VALUES (to_timestamp(%s), %s, %s) ON CONFLICT DO NOTHING")


def to_row(topic, payload, now):
    """(SQL, parametry) dla wiadomości albo None, gdy temat nas nie interesuje. Bez bazy – łatwe do testów."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "linesight":
        return None
    _, source, leaf = parts
    if leaf == "status":
        return SQL_LINK, (now, source, payload.strip() == "online")
    if source == "plc":
        m = json.loads(payload)
        v = m["value"]
        value = float(v) if v is not None else None  # bool -> 0.0 / 1.0
        return SQL_SIGNAL, (m["t"], leaf, value, m.get("t_src"))
    if source == "vision" and leaf == "events":
        ev = json.loads(payload)
        t_cross = ev.get("t_cross", ev["t"])  # zdarzenia sprzed E2-07 nie mają t_cross
        return SQL_EVENT, (t_cross, ev["t"], ev["track_id"], ev["class"], ev.get("direction"),
                           ev.get("clip"), Jsonb(ev.get("votes")), Jsonb(ev))
    return None


class Writer(object):
    """Połączenie z bazą, które samo się odnawia. write() wraca dopiero po udanym zapisie."""

    def __init__(self, dsn):
        self.dsn, self.conn, self.n = dsn, None, 0

    def write(self, sql, params):
        while True:
            try:
                if self.conn is None or self.conn.closed:
                    self.conn = psycopg.connect(self.dsn, autocommit=True, connect_timeout=5)
                    print("DB: połączono", flush=True)
                self.conn.execute(sql, params)
                self.n += 1
                return
            except psycopg.OperationalError as e:  # baza niedostępna / zerwane połączenie
                print("DB: błąd ({}), ponawiam za {} s".format(str(e).strip().splitlines()[0], RETRY_S), flush=True)
                self.conn = None
                time.sleep(RETRY_S)


def main():
    writer = Writer(DB_DSN)

    def on_connect(client, _u, _flags, rc, _props=None):
        print("MQTT: połączono (kod {})".format(rc), flush=True)
        client.subscribe([("linesight/plc/+", 1), ("linesight/vision/+", 1)])

    def on_message(_client, _u, msg):
        try:
            row = to_row(msg.topic, msg.payload.decode("utf-8"), time.time())
        except (ValueError, KeyError, TypeError) as e:  # uszkodzona wiadomość: pomijamy, nie blokujemy kolejki
            print("Pominięto {}: {} ({})".format(msg.topic, msg.payload[:200], e), flush=True)
            return
        if row:
            writer.write(*row)
            if writer.n % 500 == 0:
                print("DB: zapisano {} wierszy".format(writer.n), flush=True)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="linesight-ingest", clean_session=False)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
