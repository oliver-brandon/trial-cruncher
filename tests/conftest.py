"""Shared synthetic exports; no research recordings are bundled."""

from collections import Counter

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


@pytest.fixture
def phase_input(tmp_path):
    """Small invented recorded sequences with matching saved counters."""

    def make(codes=(7, 6, 1, 7, 1, 2, 1, 7, 1, 7), *, name="phase.txt", program="PRL_OPTO"):
        counts = Counter(codes)
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        values = " ".join(f"{i}.{code:02}" for i, code in enumerate(codes))
        c = f"C:\n  0: {values}\n" if codes else "C:\n"
        path.write_text(
            f"File: synthetic\nMSN: {program}\nSubject: 0007\nS: {len(codes) + 1}\n"
            f"A:\n  0: {counts[1] + counts[2]} {counts[6] + counts[7]} {len(codes)}\n"
            f"B:\n  0: {counts[1]} {counts[2]} {counts[6]} {counts[7]}\n{c}"
        )
        return path

    return make
