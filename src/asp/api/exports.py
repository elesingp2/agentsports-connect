"""Download the site's existing coupon report as a local CSV file."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import xlrd

from .predictions import _coupon_id


class ExportMixin:
    """Report export methods mixed into AspClient."""

    def pool_csv(self, path_or_id: str, output: str) -> dict[str, Any]:
        cid = _coupon_id(path_or_id)
        if not 0 < cid <= 2147483647:
            raise ValueError("Coupon ID must be a positive 32-bit integer")
        destination = Path(output).expanduser().absolute()
        if destination.suffix.lower() != ".csv":
            raise ValueError("Output path must end in .csv")
        if destination.exists() or destination.is_symlink():
            return {"error": "output_exists", "path": str(destination)}
        if not destination.parent.is_dir():
            raise ValueError("Output directory does not exist")

        # Reuse the report behind the site's download button, including its
        # access rules and session handling. No second prediction query.
        path = f"/couponReport/{cid}/xls"
        response = self._do_request("GET", path, headers={"Accept": "application/xls"})
        if not response.is_success:
            return {"error": "report_unavailable", "status": response.status_code, "coupon_id": cid}
        if not response.content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return {"error": "invalid_report", "status": response.status_code}

        try:
            workbook = xlrd.open_workbook(file_contents=response.content, on_demand=True)
        except xlrd.XLRDError:
            return {"error": "invalid_report", "status": response.status_code}
        created = False
        try:
            # The site exports one worksheet with two header rows. Fail if
            # that changes instead of silently discarding additional sheets.
            if workbook.nsheets != 1:
                return {"error": "unsupported_report", "detail": "Expected one worksheet"}
            sheet = workbook.sheet_by_index(0)
            if sheet.nrows < 2:
                return {"error": "invalid_report", "detail": "Missing report headers"}
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                for row in sheet.get_rows():
                    writer.writerow([_cell_value(cell, workbook.datemode) for cell in row])
            return {
                "coupon_id": cid,
                "path": str(destination),
                "bytes": destination.stat().st_size,
                "bets": sheet.nrows - 2,
                "columns": sheet.ncols,
                "header_rows": 2,
                "sheet": sheet.name,
                "encoding": "utf-8",
                "source_url": self._base_url + path,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }
        except FileExistsError:
            return {"error": "output_exists", "path": str(destination)}
        except (xlrd.XLRDError, ValueError, OverflowError):
            if created:
                destination.unlink(missing_ok=True)
            return {"error": "invalid_report", "status": response.status_code}
        except OSError:
            if created:
                destination.unlink(missing_ok=True)
            return {"error": "output_write_failed", "path": str(destination)}
        finally:
            workbook.release_resources()


def _cell_value(cell: xlrd.sheet.Cell, datemode: int) -> str:
    """Keep cell values; expose Excel dates as readable ISO timestamps."""
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode).isoformat()
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        return str(int(cell.value)) if cell.value.is_integer() else repr(cell.value)
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return xlrd.error_text_from_code[cell.value]
    return str(cell.value)
