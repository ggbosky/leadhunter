"""Příkazová řádka: python -m app.cli <příkaz>

Příklady:
  python -m app.cli migrate
  python -m app.cli worker              # samostatný worker + plánovač (bez API)
  python -m app.cli run-daily           # spustí denní pipeline synchronně
  python -m app.cli discover --segment interior_design --region CZ-64 --limit 30
  python -m app.cli analyze 12
  python -m app.cli import firmy.csv --segment premium_florist
  python -m app.cli sources             # kontrola dostupnosti zdrojů
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import signal
import sys
import time

from .db import SessionLocal
from .jobs import handlers  # noqa: F401
from .jobs.queue import Worker, enqueue, run_pending_sync
from .main import bootstrap, run_migrations

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="leadhunter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("worker")
    sub.add_parser("run-daily")
    sub.add_parser("sources")
    d = sub.add_parser("discover")
    d.add_argument("--segment")
    d.add_argument("--region")
    d.add_argument("--city")
    d.add_argument("--country", default="CZ")
    d.add_argument("--keyword")
    d.add_argument("--limit", type=int, default=40)
    d.add_argument("--analyze", action="store_true")
    a = sub.add_parser("analyze")
    a.add_argument("company_id", type=int)
    i = sub.add_parser("import")
    i.add_argument("path")
    i.add_argument("--segment")
    args = ap.parse_args(argv)

    run_migrations()
    bootstrap()
    if args.cmd == "migrate":
        print("Databáze je aktuální.")
        return 0
    if args.cmd == "worker":
        from .jobs.scheduler import start_scheduler

        w = Worker()
        w.start()
        start_scheduler()
        print("Worker a plánovač běží. Ukončete Ctrl+C.")
        stop = {"v": False}
        signal.signal(signal.SIGTERM, lambda *_: stop.update(v=True))
        try:
            while not stop["v"]:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        w.stop()
        return 0
    with SessionLocal() as db:
        if args.cmd == "run-daily":
            enqueue(db, "daily_pipeline", {}, trigger="manual")
        elif args.cmd == "sources":
            from .connectors.registry import check_all

            for r in check_all(db):
                print(f"{r['status']:15} {r['name']}: {r['detail']}")
            db.commit()
            return 0
        elif args.cmd == "discover":
            enqueue(db, "discover", {"segment_key": args.segment, "region_code": args.region, "city": args.city,
                                     "country": args.country, "keyword": args.keyword, "limit": args.limit,
                                     "auto_analyze": args.analyze, "require_website": True})
        elif args.cmd == "analyze":
            enqueue(db, "analyze", {"company_id": args.company_id})
        elif args.cmd == "import":
            from .services.discovery import import_rows

            with open(args.path, encoding="utf-8-sig") as f:
                sample = f.read(2000)
                f.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f, dialect=dialect)]
            stats = import_rows(db, rows, segment_key=args.segment)
            print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
            return 0
        db.commit()
    n = run_pending_sync(max_jobs=500)
    print(f"Dokončeno {n} úloh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
