#!/usr/bin/env python3
"""E3-05: most OPC UA -> MQTT. Subskrybuje zmiany zmiennych sterownika i publikuje je do brokera.

Laptop, kontener `bridge` z infra/docker-compose.yml (albo ręcznie: python bridge/opcua_mqtt_bridge.py).

- OPC UA: subskrypcja (serwer sam zgłasza zmianę wartości) zamiast odpytywania w pętli – mniej ruchu,
  żadna zmiana między odpytaniami nie ginie. Okres próbkowania = cykl zadania PLC (200 ms).
- MQTT: temat <prefix>/<nazwa zmiennej>, np. linesight/plc/iStateCurrent; QoS 1, retained
  (nowy odbiorca od razu dostaje ostatni stan). Treść: {"t": <czas odbioru, epoka UTC>, "value": ...,
  "t_src": <czas ze sterownika lub null>}.
- Znacznik czasu `t` nadaje most (zegar laptopa), nie sterownik: zegara PLC nie synchronizujemy,
  a t_src zostaje tylko do diagnostyki.
- Zerwane połączenie z PLC: status "offline", ponowne łączenie co RETRY_S sekund; po połączeniu serwer
  wysyła bieżące wartości wszystkich zmiennych, więc stan w brokerze sam się odświeża.
- <prefix>/status (retained): "online" gdy most ma połączenie z PLC, "offline" gdy nie ma albo gdy
  most padł (Last Will).
- E7-02: strażnik połączenia czyta węzeł samego serwera (Server.ServerStatus.CurrentTime, i=2258), nie zmienną
  aplikacji – brak zmiennej nie udaje już zerwanego łącza (wcześniej: status co 5 s online/offline, gdy w sterowniku
  nie było aplikacji). Zmienne, których nie ma na serwerze, trafiają do logu jako ostrzeżenie; gdy nie ma żadnej
  (aplikacja niewgrana, brak Symbol Configuration) – status zostaje "offline", ponowna próba co RETRY_S.

Konfiguracja przez zmienne środowiskowe – patrz stałe poniżej.
"""
import asyncio
import datetime
import json
import logging
import os
import time

import paho.mqtt.client as mqtt
from asyncua import Client, ua

OPCUA_URL = os.environ.get("OPCUA_URL", "opc.tcp://192.168.0.244:4840")
# Przestrzeń nazw zmiennych IEC w CODESYS; indeks (ns=4) bierzemy z serwera po URI, bo może się zmienić
OPCUA_NS_URI = os.environ.get("OPCUA_NS_URI", "CODESYSSPV3/3S/IecVarAccess")
NODE_PREFIX = os.environ.get("OPCUA_NODE_PREFIX",
                             "|var|JUMO ARM Cortex A7 Linux iMX6ULL ARM32.Application.GVL_Line.")
SIGNALS = os.environ.get(
    "OPCUA_SIGNALS",
    "iStateCurrent,iStopReason,udiProdProcessed,udiCycleTime_ms,rMachSpeed,"
    "xInjJam,xInjNoProduct,xInjFault,xInjSlow,"
    "rTorqueMean_Nm,rTorquePeak_Nm,rCurrent_A,rMotorTemp_C,xInjWear,rSimWear").split(",")   # E4-06: napęd
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_PREFIX = os.environ.get("MQTT_PREFIX", "linesight/plc")
PERIOD_MS = int(os.environ.get("OPCUA_PERIOD_MS", "200"))
RETRY_S = float(os.environ.get("RETRY_S", "5"))
WATCHDOG_S = float(os.environ.get("WATCHDOG_S", "5"))


# asyncua przy zerwaniu połączenia wypisuje kilka własnych błędów; nasz komunikat wystarcza
logging.getLogger("asyncua").setLevel(logging.CRITICAL)


def to_epoch(dt):
    """Znacznik czasu OPC UA (UTC, zależnie od wersji asyncua ze strefą lub bez) -> epoka w sekundach."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return round(dt.timestamp(), 3)


class Handler(object):
    """Wołany przez asyncua przy każdej zmianie wartości subskrybowanej zmiennej."""

    def __init__(self, mq, names):
        self.mq, self.names = mq, names

    def datachange_notification(self, node, val, data):
        payload = {"t": round(time.time(), 3), "value": val,
                   "t_src": to_epoch(data.monitored_item.Value.SourceTimestamp)}
        self.mq.publish("{}/{}".format(MQTT_PREFIX, self.names[node.nodeid.Identifier]),
                        json.dumps(payload), qos=1, retain=True)


def make_mqtt():
    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="linesight-bridge")
    mq.will_set(MQTT_PREFIX + "/status", "offline", qos=1, retain=True)
    mq.on_connect = lambda c, u, f, rc, p=None: print("MQTT: połączono" if rc == 0 else "MQTT: błąd {}".format(rc),
                                                      flush=True)
    mq.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    mq.loop_start()  # wątek w tle: wysyłka, potwierdzenia, ponowne łączenie z brokerem
    return mq


_last_status = None


def publish_status(mq, status):
    """Status łącza tylko przy zmianie: przy odłączonym PLC każda nieudana próba (co ok. 10 s) nie dopisuje
    kolejnego "offline" do link_status (E7-02)."""
    global _last_status
    if status != _last_status:
        mq.publish(MQTT_PREFIX + "/status", status, qos=1, retain=True)
        _last_status = status


def missing_signals(signals, results):
    """Nazwy zmiennych, których subskrypcja się nie udała.

    asyncua dla listy węzłów zwraca listę w tej samej kolejności: uchwyt (int) albo ua.StatusCode, gdy serwer
    odrzucił węzeł (np. BadNodeIdUnknown) – bez wyjątku, dlatego trzeba to sprawdzić samemu."""
    return [name for name, r in zip(signals, results) if isinstance(r, ua.StatusCode)]


async def run_once(mq):
    """Jedno połączenie z PLC: subskrypcja i pilnowanie, czy serwer żyje. Wyjątek = zerwane połączenie."""
    async with Client(url=OPCUA_URL, timeout=5) as client:
        ns = await client.get_namespace_index(OPCUA_NS_URI)
        names = {NODE_PREFIX + s: s for s in SIGNALS}
        nodes = [client.get_node(ua.NodeId(ident, ns)) for ident in names]
        handler = Handler(mq, names)
        sub = await client.create_subscription(PERIOD_MS, handler)
        missing = missing_signals(list(names.values()), await sub.subscribe_data_change(nodes))
        if len(missing) == len(nodes):
            raise RuntimeError("żadnej z {} zmiennych nie ma na serwerze – czy aplikacja jest wgrana "
                               "i ma Symbol Configuration?".format(len(nodes)))
        if missing:
            print("OPC UA: UWAGA – brak na serwerze {} zmiennych: {}".format(len(missing), ", ".join(missing)),
                  flush=True)
        publish_status(mq, "online")
        print("OPC UA: połączono z {} (ns={}), subskrypcja {} z {} zmiennych co {} ms".format(
            OPCUA_URL, ns, len(nodes) - len(missing), len(nodes), PERIOD_MS), flush=True)
        server_time = client.get_node(ua.ObjectIds.Server_ServerStatus_CurrentTime)  # i=2258, jest zawsze
        while True:  # strażnik: odczyt czasu serwera co WATCHDOG_S; brak odpowiedzi rzuca wyjątek
            await asyncio.sleep(WATCHDOG_S)
            await asyncio.wait_for(server_time.read_value(), timeout=WATCHDOG_S)


async def main():
    mq = make_mqtt()
    publish_status(mq, "offline")  # do pierwszego połączenia z PLC
    try:
        while True:
            try:
                await run_once(mq)
            except Exception as e:  # sieć, restart sterownika, wgranie programu, błędny NodeId
                print("OPC UA: brak połączenia ({}: {}), ponawiam co {} s".format(
                    type(e).__name__, e, RETRY_S), flush=True)
                publish_status(mq, "offline")
            await asyncio.sleep(RETRY_S)
    finally:
        mq.publish(MQTT_PREFIX + "/status", "offline", qos=1, retain=True)
        time.sleep(0.3)
        mq.disconnect()
        mq.loop_stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
