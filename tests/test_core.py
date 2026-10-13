import io
import json
import logging
import subprocess
import sys

from trial_cruncher import __version__
from trial_cruncher.logging_config import JsonFormatter
from trial_cruncher.models import Event, MetricResult, Session


def test_cli_help_and_version():
    for arguments, expected in [
        ([], "--gui"),
        (["--help"], "--version"),
        (["--version"], __version__),
    ]:
        result = subprocess.run(
            [sys.executable, "-m", "trial_cruncher", *arguments],
            check=True,
            text=True,
            capture_output=True,
        )
        assert expected in result.stdout


def test_cli_does_not_import_qt():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from trial_cruncher.cli import main; main([]); "
            "assert not any(name.startswith('PySide6') for name in sys.modules)",
        ],
        check=True,
        capture_output=True,
    )


def test_session_supports_non_trial_tasks_and_missing_ids(tmp_path):
    session = Session(source_file=tmp_path / "source.txt", events=(Event("press", None),))
    assert session.subject_id is None
    assert session.session_id is None
    assert session.trials == ()
    assert session.events[0].timestamp_s is None
    assert MetricResult("example", "1", None, "count").value is None
    assert MetricResult("example", "1", 0, "count").value == 0


def test_structured_logging():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.Logger("test")
    logger.addHandler(handler)
    logger.warning("Cannot read %s", "file", extra={"path": "input.mat", "operation": "discover"})
    payload = json.loads(stream.getvalue())
    assert payload["level"] == "WARNING"
    assert payload["path"] == "input.mat"
    assert payload["operation"] == "discover"
    assert payload["message"] == "Cannot read file"
