"""Exercise resizable columns in the embedded browser with synthetic recordings."""

import os

import pytest
from qt_helpers import javascript, wait_until

from trial_cruncher.gui.web_shell import WebShell

pytestmark = pytest.mark.skipif(
    os.environ.get("TRIAL_CRUNCHER_WEBENGINE_TESTS") != "1",
    reason="WebEngine integration requires a working Chromium runtime",
)


def test_resize_columns_and_preserve_width_after_selection_and_sort(app, phase_input):
    recording = phase_input(name="very-long-synthetic-recording-identifier.txt")
    shell = WebShell()
    shell.resize(1100, 720)
    shell.show()
    try:
        wait_until(app, lambda: javascript(app, shell.page, "Boolean(window.trialReady)"))
        shell.controller.add_paths([str(recording)])
        wait_until(app, lambda: shell.controller._worker is None)
        shell.controller.import_selected_files()
        wait_until(app, lambda: shell.controller._import_worker is None)
        wait_until(
            app,
            lambda: javascript(
                app, shell.page, "!!document.querySelector('#batch-table tbody tr')"
            ),
        )

        def width():
            return javascript(
                app,
                shell.page,
                "document.querySelector('#batch-table th').getBoundingClientRect().width",
            )

        def drag(delta):
            javascript(
                app,
                shell.page,
                """(() => {
                  const grip = document.querySelector('#batch-table th .column-grip');
                  grip.setPointerCapture = () => {};
                  grip.dispatchEvent(new PointerEvent('pointerdown', {pointerId: 1, clientX: 100}));
                  grip.dispatchEvent(new PointerEvent(
                    'pointermove', {pointerId: 1, clientX: 100 + DELTA}));
                  grip.dispatchEvent(new PointerEvent('pointerup', {pointerId: 1}));
                })()""".replace("DELTA", str(delta)),
            )

        initial = width()
        drag(-45)
        narrow = width()
        assert narrow < initial - 35
        drag(85)
        wide = width()
        assert wide > narrow + 75
        javascript(app, shell.page, "document.querySelector('#batch-table tbody tr').click()")
        javascript(app, shell.page, "document.querySelector('#batch-table th').click()")
        wait_until(app, lambda: abs(width() - wide) < 1)
        assert javascript(
            app, shell.page, "document.querySelector('#batch-table tbody td').textContent"
        ).startswith("very-long-synthetic")
    finally:
        shell.close()
