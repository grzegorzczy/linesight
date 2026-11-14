#!/usr/bin/env python3
"""E3-04: sprawdzenie serwera OPC UA sterownika – wypisuje zmienne (NodeId, wartość) pasujące do filtra.

Laptop, .venv z pakietem asyncua:
    python tools\\opcua_browse.py                                  (domyślnie sterownik 192.168.0.244, filtr GVL_Line)
    python tools\\opcua_browse.py --url opc.tcp://host:4840 --filter PLC_PRG

NodeId wypisane tutaj wklejamy potem do mostu OPC UA -> MQTT (E3-05).
"""
import argparse
import asyncio

from asyncua import Client, ua

SERVER_NODE = "i=2253"  # gałąź diagnostyki samego serwera – pomijamy, jest duża i nas nie interesuje


async def walk(node, flt, depth, max_depth, found):
    for child in await node.get_children():
        nid = child.nodeid.to_string()
        if nid == SERVER_NODE:
            continue
        if await child.read_node_class() == ua.NodeClass.Variable:
            if flt in nid:
                try:
                    val = await child.read_value()
                except ua.UaError as e:  # np. brak prawa odczytu
                    val = "<{}>".format(e)
                print("{:<70} = {!r}".format(nid, val))
                found.append(nid)
        elif depth < max_depth:
            await walk(child, flt, depth + 1, max_depth, found)


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="opc.tcp://192.168.0.244:4840")
    ap.add_argument("--filter", default="GVL_Line", help="fragment NodeId (domyślnie GVL_Line)")
    ap.add_argument("--depth", type=int, default=8, help="maksymalna głębokość przeglądania")
    args = ap.parse_args()
    print("Łączę z", args.url)
    async with Client(url=args.url, timeout=10) as client:
        print("Połączono. Przestrzenie nazw:", await client.get_namespace_array())
        found = []
        await walk(client.nodes.objects, args.filter, 0, args.depth, found)
        print("Znaleziono zmiennych: {}".format(len(found)))
        if not found:
            print("Brak zmiennych z '{}' – sprawdź Symbol Configuration (zaznaczone symbole, "
                  "'Support OPC UA features', wgrany program).".format(args.filter))


if __name__ == "__main__":
    asyncio.run(main())
