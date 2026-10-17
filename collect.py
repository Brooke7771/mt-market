# -*- coding: utf-8 -*-
"""Раз в сутки собирает цены Маркетплейса Majestic RP со всех серверов (официальное API) и
выкладывает их в релиз «data» этого репозитория. Программа Majestic Tools читает отсюда,
поэтому пользователям не нужен свой ключ API. Ключ - только в секрете MAJESTIC_API_KEY."""
import os
import sys
import json
import gzip
import time
import urllib.request
import urllib.error

KEY = os.environ.get("MAJESTIC_API_KEY", "").strip()
HOST = "https://api.majestic-files.net"
SERVERS = [f"ru{i}" for i in range(1, 20)]
CATS = {"items": ("itemStatistics", "itemName"), "vehicles": ("vehicleStatistics", "modelName"),
        "clothes": ("clothesStatistics", "itemName"), "houses": ("houseStatistics", "itemName"),
        "apartments": ("apartmentStatistics", "itemName"), "warehouses": ("warehouseStatistics", "itemName"),
        "offices": ("officeStatistics", "itemName")}
PACE = 12.5                     # лимит API: 5 запросов в 60 с
KEEP_DAYS = 35
PREV, OUT = "prev", "out"
_last = [0.0]


def get(cat, srv):
    for attempt in range(4):
        wait = _last[0] + PACE - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(f"{HOST}/v1/ext/marketplace/{cat}/{srv}", headers={
            "X-API-KEY": KEY, "X-LANGUAGE": "ru", "Accept": "application/json", "User-Agent": "MajesticTools-collector/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.load(r)
            res = j.get("result", j)
            if isinstance(res, dict) and CATS[cat][0] in res:
                return res
            print("  неожиданный ответ", cat, srv)
        except urllib.error.HTTPError as e:
            print("  HTTP", e.code, cat, srv)
            if e.code == 401:
                sys.exit("ключ API не принят (401)")
            if e.code == 429:
                time.sleep(65)
        except Exception as ex:
            print("  ошибка", cat, srv, ex)
            time.sleep(10)
    return None


def key_of(cat, r):
    """Так же, как market.rows_of в программе."""
    namef = CATS[cat][1]
    if cat == "clothes":
        return f"{r.get('component')}:{r.get('drawable')}:{r.get('texture')}:{r.get('gender')}:{r.get('isProp')}"
    return str(r.get("itemId", r.get("model", r.get("houseId", r.get("apartmentId", r.get("warehouseId",
                                                                                       r.get("officeId", r.get(namef))))))))


def load_gz(path, default):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_gz(path, data):
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def main():
    if not KEY:
        sys.exit("нет секрета MAJESTIC_API_KEY")
    os.makedirs(OUT, exist_ok=True)
    index = {"generated": time.time(), "cats": {}}
    ok_n = fail_n = 0
    for cat, (lst, _) in CATS.items():
        prev = load_gz(os.path.join(PREV, f"{cat}.json.gz"), {}).get("servers", {})
        servers = {}
        for srv in SERVERS:
            res = get(cat, srv)
            if res is None:
                fail_n += 1
                if srv in prev:
                    servers[srv] = prev[srv]          # не удалось - оставляем вчерашнее
                continue
            ok_n += 1
            servers[srv] = res
            day = (res.get("lastUpdated") or "")[:10]
            hname = f"hist_{cat}_{srv}.json.gz"
            h = load_gz(os.path.join(PREV, hname), {"days": {}})
            if day:
                h["days"][day] = {key_of(cat, r): [int(r.get("averagePrice") or 0), int(r.get("minPrice") or 0),
                                                   int(r.get("maxPrice") or 0), int(r.get("soldCount") or 0),
                                                   int(r.get("totalCount") or 0)] for r in res.get(lst) or []}
                for d in sorted(h["days"])[:-KEEP_DAYS]:
                    del h["days"][d]
            save_gz(os.path.join(OUT, hname), h)
        save_gz(os.path.join(OUT, f"{cat}.json.gz"), {"generated": index["generated"], "servers": servers})
        index["cats"][cat] = {s: (v.get("lastUpdated") or "") for s, v in servers.items()}
        print(cat, "серверов:", len(servers))
    index["ok"], index["failed"] = ok_n, fail_n
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    with open("status.json", "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "ok": ok_n, "failed": fail_n}, f)
    print("готово: успешно", ok_n, "ошибок", fail_n)
    if ok_n == 0:
        sys.exit("ни одного ответа API")


if __name__ == "__main__":
    main()
