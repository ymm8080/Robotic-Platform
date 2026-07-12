"""Apply AI review fixes to cli.py, traffic_coordinator_main.py, and test_zewm_robco_client.py."""
import pathlib

# Fix cli.py - add import threading and SimulatedRobot
p = pathlib.Path("traffic_coordinator_v5/simulator/cli.py")
c = p.read_text(encoding="utf-8")
if "import threading" not in c:
    c = c.replace(
        "import signal\nimport sys\nimport time",
        "import signal\nimport sys\nimport threading\nimport time",
    )
if "SimulatedRobot" not in c:
    c = c.replace(
        "from traffic_coordinator_v5.simulator.robot import RobotConfig",
        "from traffic_coordinator_v5.simulator.robot import RobotConfig, SimulatedRobot",
    )
p.write_text(c, encoding="utf-8")
print(f"cli.py: threading={'import threading' in c}, SimulatedRobot={'SimulatedRobot' in c}")

# Fix traffic_coordinator_main.py - add import logging, concurrent.futures, _logger definition
p2 = pathlib.Path("traffic_coordinator_v5/traffic_coordinator_main.py")
c2 = p2.read_text(encoding="utf-8")
if "import concurrent.futures" not in c2:
    c2 = c2.replace(
        "import json\nimport os",
        "import concurrent.futures\nimport json\nimport logging\nimport os",
    )
if "_logger = logging.getLogger" not in c2:
    c2 = c2.replace(
        "from traffic_coordinator_v5.maps.loader import load_facility_map\n",
        "from traffic_coordinator_v5.maps.loader import load_facility_map\n\n_logger = logging.getLogger(__name__)\n",
    )
p2.write_text(c2, encoding="utf-8")
print(f"tcm.py: logging={'import logging' in c2}, _logger={'_logger = logging.getLogger' in c2}, concurrent={'import concurrent.futures' in c2}")

# Fix test_zewm_robco_client.py - remove unused top-level raise_for_error_code
p3 = pathlib.Path("sap-bridge/tests/test_zewm_robco_client.py")
c3 = p3.read_text(encoding="utf-8")
# Only remove from top-level import, not from local imports inside test methods
c3 = c3.replace(
    "    WhtNotConfirmedError,\n    raise_for_error_code,\n)",
    "    WhtNotConfirmedError,\n)",
)
p3.write_text(c3, encoding="utf-8")
# Verify local import still has it
has_local = "from clients.zewm_robco_exceptions import (\n            RobcoError,\n            raise_for_error_code,\n        )" in c3
print(f"test.py: top-level removed={'    raise_for_error_code,\n)' not in c3}, local import present={has_local}")
