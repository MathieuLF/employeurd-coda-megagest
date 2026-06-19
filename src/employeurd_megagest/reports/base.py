from __future__ import annotations

from pathlib import Path
from typing import Protocol

from employeurd_megagest.models import PayrollReportTotals


class PayrollReportParser(Protocol):
    report_type: str

    def parse(self, path: Path) -> PayrollReportTotals:
        """Parse a local payroll report into aggregate totals."""
