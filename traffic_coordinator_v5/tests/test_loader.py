"""Tests for the facility map YAML loader."""

import tempfile
from pathlib import Path

from core.platform.fixed_lane_map import FixedLaneMap, Lane, SpeedClass
from traffic_coordinator_v5.maps.loader import (
    FacilityMap,
    _parse_env,
    _parse_speed_class,
    load_facility_map,
)


class TestParseEnv:
    """Tests for _parse_env helper."""

    def test_none_returns_default(self):
        env = _parse_env(None)
        assert env.max_grade == 0.0
        assert env.floor_threshold == 0.0
        assert env.min_friction == 0.0

    def test_partial_dict(self):
        env = _parse_env({"max_grade": 0.1})
        assert env.max_grade == 0.1
        assert env.floor_threshold == 0.0

    def test_full_dict(self):
        env = _parse_env({"max_grade": 0.05, "floor_threshold": 0.02, "min_friction": 0.5})
        assert env.max_grade == 0.05
        assert env.floor_threshold == 0.02
        assert env.min_friction == 0.5


class TestParseSpeedClass:
    """Tests for _parse_speed_class helper."""

    def test_none_defaults_to_fast(self):
        assert _parse_speed_class(None) == SpeedClass.FAST

    def test_valid_values(self):
        assert _parse_speed_class("slow") == SpeedClass.SLOW
        assert _parse_speed_class("SLOW") == SpeedClass.SLOW
        assert _parse_speed_class("fast") == SpeedClass.FAST
        assert _parse_speed_class("FAST") == SpeedClass.FAST

    def test_invalid_falls_back_to_fast(self):
        assert _parse_speed_class("supersonic") == SpeedClass.FAST
        assert _parse_speed_class("") == SpeedClass.FAST


class TestFacilityMap:
    """Tests for the FacilityMap dataclass."""

    def test_defaults(self):
        fm = FacilityMap()
        assert isinstance(fm.fmap, FixedLaneMap)
        assert fm.intersections == []
        assert fm.charger_ids == []
        assert fm.lift_ids == []
        assert fm.warnings == []

    def test_with_data(self):
        lane = Lane("L1", "A", "B", length=5.0)
        fmap = FixedLaneMap()
        fmap.add_lane(lane)
        fm = FacilityMap(
            fmap=fmap,
            intersections=["X1"],
            charger_ids=["C1"],
            facility_name="test_facility",
        )
        assert len(fm.fmap.all_lanes()) == 1
        assert fm.intersections == ["X1"]
        assert fm.charger_ids == ["C1"]
        assert fm.facility_name == "test_facility"


class TestLoadFacilityMap:
    """Tests for load_facility_map function."""

    def test_missing_file_returns_warning(self):
        result = load_facility_map("/nonexistent/path/map.yaml")
        assert len(result.warnings) >= 1
        assert "not found" in result.warnings[0].lower()

    def test_empty_yaml_produces_empty_map(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("{}")
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)
        assert result.facility_name != ""
        assert len(result.fmap.all_lanes()) == 0
        assert result.intersections == []

    def test_minimal_map_with_one_lane(self):
        yaml_content = """
facility:
  name: test_facility
lanes:
  - lane_id: L_A_B
    from_node: A
    to_node: B
    length: 12.5
    max_speed: 2.0
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)

        assert result.facility_name == "test_facility"
        lanes = result.fmap.all_lanes()
        assert len(lanes) == 1
        lane = lanes[0]
        assert lane.lane_id == "L_A_B"
        assert lane.from_node == "A"
        assert lane.to_node == "B"
        assert lane.length == 12.5
        assert lane.max_speed == 2.0

    def test_map_with_intersections(self):
        yaml_content = """
lanes:
  - lane_id: L1
    from_node: A
    to_node: B
intersections:
  - id: X1
    node: B
  - id: X2
    node: C
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)
        assert result.intersections == ["X1", "X2"]

    def test_map_with_chargers(self):
        yaml_content = """
lanes:
  - lane_id: L1
    from_node: A
    to_node: B
chargers:
  - id: CHG1
    node: A
  - id: CHG2
    node: B
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)
        assert result.charger_ids == ["CHG1", "CHG2"]

    def test_map_with_lifts(self):
        yaml_content = """
lanes:
  - lane_id: L1
    from_node: A
    to_node: B
lifts:
  - id: ELEV1
    lanes: [L_UP, L_DOWN]
    floors: [1, 2]
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)
        assert len(result.lift_ids) == 1
        assert result.lift_ids[0]["id"] == "ELEV1"
        assert result.lift_ids[0]["lanes"] == ["L_UP", "L_DOWN"]
        assert result.lift_ids[0]["floors"] == [1, 2]

    def test_lane_with_optional_fields(self):
        yaml_content = """
lanes:
  - lane_id: L_COMPLEX
    from_node: D
    to_node: E
    length: 20.0
    width: 2.0
    speed_class: slow
    allowed_models: [mir, otto]
    max_speed: 0.8
    no_reverse: true
    charger: true
    floor: 2
    direction: 1
    env:
      max_grade: 0.03
      floor_threshold: 0.01
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)

        lanes = result.fmap.all_lanes()
        assert len(lanes) == 1
        lane = lanes[0]
        assert lane.lane_id == "L_COMPLEX"
        assert lane.width == 2.0
        assert lane.speed_class == SpeedClass.SLOW
        assert lane.allowed_models == ["mir", "otto"]
        assert lane.max_speed == 0.8
        assert lane.no_reverse is True
        assert lane.charger is True
        assert lane.floor == 2
        assert lane.direction == 1

    def test_bad_lane_entry_generates_warning(self):
        """A lane missing required fields triggers a warning, not a crash."""
        yaml_content = """
lanes:
  - lane_id: L_BAD
    # missing from_node and to_node
  - lane_id: L_GOOD
    from_node: A
    to_node: B
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)

        # L_GOOD should load, L_BAD produces a warning
        lanes = result.fmap.all_lanes()
        assert len(lanes) == 1
        assert lanes[0].lane_id == "L_GOOD"
        assert any("L_BAD" in w for w in result.warnings)

    def test_bad_intersection_generates_warning(self):
        yaml_content = """
lanes:
  - lane_id: L1
    from_node: A
    to_node: B
intersections:
  - wrong_key: no_id_here
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)
        assert len(result.intersections) == 0
        assert len(result.warnings) >= 1

    def test_lift_id_on_lane(self):
        """Lane with lift_id field should parse."""
        yaml_content = """
lanes:
  - lane_id: L_ELEV
    from_node: F1
    to_node: F2
    lift_id: ELEV_MAIN
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)

        lanes = result.fmap.all_lanes()
        assert len(lanes) == 1
        assert lanes[0].lift_id == "ELEV_MAIN"

    def test_intersection_id_on_lane(self):
        """Lane with intersection_id field should parse."""
        yaml_content = """
lanes:
  - lane_id: L_X
    from_node: A
    to_node: B
    intersection_id: X1
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            result = load_facility_map(f.name)
        Path(f.name).unlink(missing_ok=True)

        lanes = result.fmap.all_lanes()
        assert lanes[0].intersection_id == "X1"

    def test_default_map_loads(self):
        """The bundled facility_map.yaml should load without errors."""
        result = load_facility_map()  # uses default path
        assert len(result.warnings) == 0, f"warnings={result.warnings}"
        assert result.facility_name == "demo_facility"
        lanes = result.fmap.all_lanes()
        assert len(lanes) == 2
        lane_ids = {lane.lane_id for lane in lanes}
        assert "L_A_B" in lane_ids
        assert "L_B_C" in lane_ids
        assert "X1" in result.intersections
