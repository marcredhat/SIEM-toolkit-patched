#!/usr/bin/env python3
"""Send N Stormshield events with current timestamps, varied src IPs/users,
so they appear as a recognizable cluster in the SDL console under
parser="stormshield"."""
import json, time, uuid, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

CFG = json.load(open("./config.json"))
BASE = CFG["base_url"].rstrip("/")
WRITE_KEY = CFG["log_write_key"]
PARSER = "stormshield"

# A handful of plausible variations
USERS  = ["aimee.ndzodo", "luc.martin", "claire.dubois", "fatima.khelifi"]
SRCS   = ["10.200.0.82",  "10.200.0.91", "10.200.1.14",  "10.200.2.55"]
DSTS   = [("192.168.10.7","53","dns_udp","53"),
          ("192.168.10.7","53","dns_udp","53"),
          ("8.8.8.8","53","dns_udp","53"),
          ("1.1.1.1","443","https","443")]
ACTIONS = ["pass", "pass", "pass", "block"]


def _local_now():
    tz = datetime.now(timezone.utc).astimezone().tzinfo
    return datetime.now(tz).replace(microsecond=0)


def _ts(now):
    syslog = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    syslog = syslog[:-2] + ":" + syslog[-2:]
    time_   = now.strftime("%Y-%m-%d %H:%M:%S")
    return syslog, time_


def build_line(i):
    now = _local_now() + timedelta(seconds=i)
    syslog, time_ = _ts(now)
    start = (now - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
    u, src, (dst, dport, dpname, dportname), act = USERS[i % 4], SRCS[i % 4], DSTS[i % 4], ACTIONS[i % 4]
    sport = 50000 + i * 137
    return (
        f'<14>1 {syslog} stormshield-v.univ-evry.fr asqd - - - '
        f'?id=firewall time="{time_}" fw="stormshield-v.univ-evry.fr" '
        f'tz=+0200 startime="{start}" pri=5 confid=01 slotlevel=2 ruleid={34+i} '
        f'rulename="17209b9db27_{i+1}" user="{u}" domain="ueve.local" '
        f'srcif="sslvpn0" srcifname="sslvpn" ipproto=udp dstif="Ethernet1" dstifname="in" '
        f'proto={dpname} src={src} srcport={sport} srcportname=ephemeral_fw_udp '
        f'dst={dst} dstport={dport} dstportname={dportname} dstname=resolver.example.com '
        f'modsrc={src} modsrcport={sport} origdst={dst} origdstport={dport} '
        f'ipv=4 sent={80+i*8} rcvd={196+i*16} duration=0.0{i} action={act} logtype="connection"'
    )


def send_one(body, idx):
    nonce = str(uuid.uuid4())
    req = urllib.request.Request(
        f"{BASE}/api/uploadLogs",
        method="POST",
        data=body.encode(),
        headers={
            "Authorization": f"Bearer {WRITE_KEY}",
            "Content-Type":  "text/plain",
            "parser":        PARSER,
            "Nonce":         nonce,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"[{idx}] HTTP {r.status}  nonce={nonce[:8]}…  body=`{body[:90]}...`")
            return r.status
    except urllib.error.HTTPError as e:
        print(f"[{idx}] HTTP {e.code} {e.read().decode()[:120]}")
        return e.code


def main():
    n = 4
    print(f"Sending {n} Stormshield events to {BASE} ...")
    for i in range(n):
        send_one(build_line(i), i)
        time.sleep(1)
    print(f"\nDone. Wait ~30-60s, then in https://demo.sentinelone.net search:")
    print(f"   parser=\"stormshield\"")
    print("or run:")
    print(f"   parser='stormshield' | sort -timestamp | limit 10")


if __name__ == "__main__":
    main()
