"""Read-only end-to-end check against the real website and installed asp CLI.

Run with a populated coupon, a different format and an empty coupon, for example:
    python scripts/verify_pool_csv_live.py 18291 18749 18687
No fixtures, mock HTTP responses, accounts or predictions are created.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx
import xlrd


def main() -> None:
    ids = [int(value) for value in sys.argv[1:]]
    if not ids:
        raise SystemExit("Supply coupon IDs to verify against the live website")
    origin = os.environ.get("ASP_BASE_URL", "https://agentsports.io").rstrip("/")
    evidence = []
    with tempfile.TemporaryDirectory(prefix="asp-csv-review-") as temporary:
        root = Path(temporary)
        env = {**os.environ, "ASP_DATA_DIR": str(root / "state")}

        def run(*args: str, code: int = 0) -> dict:
            process = subprocess.run(
                [sys.executable, "-m", "asp.cli", *args], env=env,
                capture_output=True, text=True, timeout=90,
            )
            assert process.returncode == code, (args, process.returncode, process.stdout, process.stderr)
            result = json.loads(process.stdout or process.stderr)
            assert len(process.stdout) < 4096, "Export rows leaked into stdout"
            return result

        for cid in ids:
            target = root / f"pool {cid}.csv"
            result = run("pool-csv", str(cid), "--output", str(target))
            with httpx.Client(timeout=60) as http:
                response = http.get(f"{origin}/couponReport/{cid}/xls")
                response.raise_for_status()
            book = xlrd.open_workbook(file_contents=response.content)
            sheet = book.sheet_by_index(0)
            with target.open(encoding="utf-8", newline="") as source:
                rows = list(csv.reader(source))
            assert len(rows) == sheet.nrows
            assert all(len(row) == sheet.ncols for row in rows)
            compared = 0
            for r, row in enumerate(rows):
                for c, value in enumerate(row):
                    cell = sheet.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        assert datetime.fromisoformat(value) == xlrd.xldate_as_datetime(cell.value, book.datemode)
                    elif cell.ctype == xlrd.XL_CELL_NUMBER:
                        assert float(value) == cell.value
                    else:
                        assert value == str(cell.value), (r, c)
                    compared += 1
            assert result["bets"] == sheet.nrows - 2
            assert result["header_rows"] == 2 and result["columns"] == sheet.ncols
            assert result["bytes"] == target.stat().st_size
            assert result["source_url"] == f"{origin}/couponReport/{cid}/xls"
            assert target.stat().st_mode & 0o777 == 0o600
            original = hashlib.sha256(target.read_bytes()).hexdigest()
            duplicate = run("pool-csv", str(cid), "--output", str(target), code=1)
            assert duplicate["error"] == "output_exists"
            assert hashlib.sha256(target.read_bytes()).hexdigest() == original
            # Actually consume the CSV for analysis, including merged headers.
            groups = {}
            event = ""
            for index in range(1, len(rows[0])):
                event = rows[0][index] or event
                counts = Counter(row[index] for row in rows[2:])
                groups[f"{index}: {event} / {rows[1][index]}"] = dict(counts)
            evidence.append({"coupon_id": cid, "bets": result["bets"], "cells_compared": compared,
                             "analyzed_columns": len(groups), "overwrite_protected": True})

        # A route path is accepted, not only an ID.
        path_export = root / "from-path.csv"
        assert run("pool-csv", f"/BASKETBALL/nBAPreseason/{ids[0]}", "--output", str(path_export))["coupon_id"] == ids[0]
        for bad in ("0", "2147483648", "../secret", "abc"):
            target = root / "invalid.csv"
            assert run("pool-csv", bad, "--output", str(target), code=3)["error"] == "invalid_argument"
            assert not target.exists()
        missing = root / "missing.csv"
        assert run("pool-csv", "2147483647", "--output", str(missing), code=1)["error"] == "report_unavailable"
        assert not missing.exists()
        for target in (root / "report.txt", root / "absent" / "report.csv"):
            assert run("pool-csv", str(ids[0]), "--output", str(target), code=3)["error"] == "invalid_argument"
            assert not target.exists()
        link = root / "symlink.csv"
        link.symlink_to(root / "nonexistent.csv")
        assert run("pool-csv", str(ids[0]), "--output", str(link), code=1)["error"] == "output_exists"
        assert not link.resolve().exists()
        locked = root / "read-only"
        locked.mkdir(mode=0o500)
        try:
            target = locked / "report.csv"
            assert run("pool-csv", str(ids[0]), "--output", str(target), code=1)["error"] == "output_write_failed"
            assert not target.exists()
        finally:
            locked.chmod(0o700)
    print(json.dumps({"live_exports": evidence, "argument_and_file_checks": "passed", "temporary_files_removed": True}, indent=2))


if __name__ == "__main__":
    main()
