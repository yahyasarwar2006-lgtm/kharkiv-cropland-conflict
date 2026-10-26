from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


def test_dashboard_runs_and_switches_layers():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    for layer in ["Conflict exposure group", "Exposure history 2022–24", "Peak greenness", "Cropland share",
                  "Anomaly vs pre-war average (no weather)", "Weather-adjusted anomaly"]:
        at.radio[0].set_value(layer).run()
        assert not at.exception, layer
    at.radio[1].set_value("late").run()
    assert not at.exception
