"""Shared synthetic exports; no research recordings are bundled."""

import pytest


@pytest.fixture
def write_export(tmp_path):
    def write(text=None, *, program="PRL_BO"):
        if text is None:
            # Four hand-constructed choices: one of each outcome, at known times.
            text = f"""File: C:\\Synthetic\\example.txt
Start Date: 01/01/26
End Date: 01/01/26
Subject: 0007
Experiment: synthetic
Group: 00
Box: 1
Start Time: 09:00:00
End Time: 10:00:00
MSN: {program}
D: 1.00
M: 60.00
S: 10.00
A:
  0: 2.00 2.00 4.00 24.00 0.00
  5: 0.50
B:
  0: 1.00 1.00 1.00 1.00
C:
  0: 0.01 1.22 2.36 4.57
F:
  0: 0.50
J:
"""
        path = tmp_path / "synthetic.txt"
        path.write_bytes(text.encode("utf-8"))
        return path

    return write
