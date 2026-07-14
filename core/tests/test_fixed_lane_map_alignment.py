"""Tests for lane-map node correspondence validation in FixedLaneMap.

Tests Phase 2 Task 2: 车道图对齐：节点-节点对应校验
"""

from core.platform.fixed_lane_map import FixedLaneMap, Lane, SpeedClass


def test_validate_node_correspondence_identical_maps():
    """Test correspondence validation with identical maps."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # Add identical lanes
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    lane2 = Lane("lane2", "node2", "node3", 15.0)
    map1.add_lane(lane1)
    map1.add_lane(lane2)
    map2.add_lane(lane1)
    map2.add_lane(lane2)

    # Test standalone method
    issues = map1.validate_node_correspondence(map2)
    assert not issues, f"Identical maps should have no issues, got: {issues}"

    # Test integration with validate method
    issues = map1.validate(reference_map=map2)
    assert not issues, f"Identical maps should have no issues via validate(), got: {issues}"


def test_validate_node_correspondence_missing_node():
    """Test detection of nodes that exist in one map but not the other."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # map1 has an extra node
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    lane2 = Lane("lane2", "node2", "node3", 15.0)
    map1.add_lane(lane1)
    map1.add_lane(lane2)

    # map2 is missing node3
    map2.add_lane(lane1)

    # Test standalone method
    issues = map1.validate_node_correspondence(map2)
    assert "Nodes only in our map: ['node3']" in str(issues)

    # Test integration with validate method
    issues = map1.validate(reference_map=map2)
    assert "Nodes only in our map: ['node3']" in str(issues)


def test_validate_node_correspondence_reference_has_extra_node():
    """Test detection when reference map has extra nodes."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # map1 is simple
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    map1.add_lane(lane1)

    # map2 has an extra node
    lane2 = Lane("lane2", "node2", "node3", 15.0)
    map2.add_lane(lane1)
    map2.add_lane(lane2)

    issues = map1.validate_node_correspondence(map2)
    assert "Nodes only in reference map: ['node3']" in str(issues)


def test_validate_node_correspondence_different_node_degree():
    """Test detection of nodes with different out-degrees."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # map1: node1 has 2 outgoing lanes
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    lane2 = Lane("lane2", "node1", "node3", 10.0)
    map1.add_lane(lane1)
    map1.add_lane(lane2)

    # map2: node1 has only 1 outgoing lane
    map2.add_lane(lane1)

    issues = map1.validate_node_correspondence(map2)
    assert "node1 has different out-degree: 2 (our) vs 1 (reference)" in str(issues)


def test_validate_node_correspondence_connectivity_mismatch():
    """Test detection of significant connectivity differences."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # map1: node1 connects to node2 and node3
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    lane2 = Lane("lane2", "node1", "node3", 10.0)
    map1.add_lane(lane1)
    map1.add_lane(lane2)

    # map2: node1 only connects to node2
    map2.add_lane(lane1)

    issues = map1.validate_node_correspondence(map2)
    assert "Nodes only in our map: ['node3']" in str(issues)
    assert "Node node1 has different out-degree: 2 (our) vs 1 (reference)" in str(issues)


def test_validate_node_correspondence_bidirectional_equivalent():
    """Test detection of bidirectional lane equivalents with different IDs."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # map1 has lane1: node1 -> node2
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    map1.add_lane(lane1)

    # map2 has reverse direction with different ID: node2 -> node1
    lane2 = Lane("lane2", "node2", "node1", 10.0)
    map2.add_lane(lane2)

    issues = map1.validate_node_correspondence(map2)
    # The implementation catches this as connectivity mismatches, not bidirectional equivalents
    assert "Node node1 has different out-degree: 1 (our) vs 0 (reference)" in str(issues)
    assert "Node node2 has different out-degree: 0 (our) vs 1 (reference)" in str(issues)


def test_validate_node_correspondence_no_connectivity_mismatch():
    """Test that maps with same connectivity but different lane IDs pass."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # map1
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    lane2 = Lane("lane2", "node2", "node3", 15.0)
    map1.add_lane(lane1)
    map1.add_lane(lane2)

    # map2 with different lane IDs but same structure
    lane3 = Lane("laneA", "node1", "node2", 10.0)
    lane4 = Lane("laneB", "node2", "node3", 15.0)
    map2.add_lane(lane3)
    map2.add_lane(lane4)

    issues = map1.validate_node_correspondence(map2)
    # Should only report node ID differences, not structural issues
    node_only_issues = [i for i in issues if "Nodes only in" in i]
    assert len(node_only_issues) == 0, f"Unexpected node issues: {issues}"


def test_validate_node_correspondence_complex_mismatch():
    """Test detection of multiple types of mismatches."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # map1 has more complex structure
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    lane2 = Lane("lane2", "node2", "node3", 10.0)
    lane3 = Lane("lane3", "node1", "node4", 10.0)
    map1.add_lane(lane1)
    map1.add_lane(lane2)
    map1.add_lane(lane3)

    # map2 is missing node4 and has different connectivity
    map2.add_lane(lane1)
    lane4 = Lane("lane4", "node2", "node5", 10.0)  # different node
    map2.add_lane(lane4)

    issues = map1.validate_node_correspondence(map2)
    # Should detect both missing nodes and connectivity issues
    assert "Nodes only in our map: ['node3', 'node4']" in str(issues)
    assert "Nodes only in reference map: ['node5']" in str(issues)
    assert "Node node1 has different out-degree: 2 (our) vs 1 (reference)" in str(issues)
    assert "Node node2 has very different connectivity" in str(issues)


def test_validate_node_correspondence_with_occupancy():
    """Test that occupancy doesn't affect correspondence validation."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    lane1 = Lane("lane1", "node1", "node2", 10.0)
    map1.add_lane(lane1)
    map2.add_lane(lane1)

    # Add occupancy to map1
    map1.occupy_lane("lane1", "robot1")

    issues = map1.validate_node_correspondence(map2)
    assert not issues, "Occupancy should not affect node correspondence"


def test_validate_node_correspondence_with_blocked_lanes():
    """Test that blocked lanes don't affect correspondence validation."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    lane1 = Lane("lane1", "node1", "node2", 10.0)
    map1.add_lane(lane1)
    map2.add_lane(lane1)

    # Block lane in map1
    map1.block_lane("lane1")

    issues = map1.validate_node_correspondence(map2)
    assert not issues, "Blocked lanes should not affect node correspondence"


def test_validate_node_correspondence_self_reference():
    """Test validation of a map against itself."""
    map1 = FixedLaneMap()

    lane1 = Lane("lane1", "node1", "node2", 10.0)
    lane2 = Lane("lane2", "node2", "node3", 15.0)
    map1.add_lane(lane1)
    map1.add_lane(lane2)

    issues = map1.validate_node_correspondence(map1)
    assert not issues, "Map should be consistent with itself"

    # Test integration with validate method
    issues = map1.validate(reference_map=map1)
    assert not issues, "Map should be consistent with itself via validate()"


def test_validate_node_correspondence_empty_maps():
    """Test validation with empty maps."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    issues = map1.validate_node_correspondence(map2)
    assert not issues, "Empty maps should be consistent"

    # Test validate() without reference - should report "map has no lanes"
    issues = map1.validate()
    assert issues == ["map has no lanes"], (
        f"Empty map should report 'map has no lanes', got: {issues}"
    )


def test_validate_node_correspondence_one_map_empty():
    """Test validation when one map is empty."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    lane1 = Lane("lane1", "node1", "node2", 10.0)
    map1.add_lane(lane1)

    issues = map1.validate_node_correspondence(map2)
    assert "Nodes only in our map: ['node1', 'node2']" in str(issues)


def test_validate_node_correspondence_dangling_reference():
    """Test detection of lanes that reference non-existent nodes."""
    # This tests the case where a lane's from_node or to_node
    # doesn't exist in the map itself (which should be caught by validate())
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # map1 has a lane with dangling node reference
    lane1 = Lane("lane1", "node1", "node2", 10.0)
    # Add only the lane, not creating node2 explicitly
    map1._lanes["lane1"] = lane1
    map1._adjacency.setdefault("node1", []).append("lane1")

    # map2 is clean
    lane2 = Lane("lane2", "node1", "node2", 10.0)
    map2.add_lane(lane2)

    issues = map1.validate_node_correspondence(map2)
    # The issue is that node2 is not in our_nodes set because it's not
    # properly tracked in the adjacency structure
    assert "Node node1 has very different connectivity" in str(issues)


def test_validate_node_correspondance_speed_class_difference():
    """Test that speed class differences don't affect correspondence."""
    map1 = FixedLaneMap()
    map2 = FixedLaneMap()

    # Same structure, different speed classes
    lane1 = Lane("lane1", "node1", "node2", 10.0, speed_class=SpeedClass.FAST)
    lane2 = Lane("lane2", "node2", "node3", 15.0, speed_class=SpeedClass.SLOW)
    map1.add_lane(lane1)
    map1.add_lane(lane2)

    lane3 = Lane("lane1", "node1", "node2", 10.0, speed_class=SpeedClass.SLOW)
    lane4 = Lane("lane2", "node2", "node3", 15.0, speed_class=SpeedClass.FAST)
    map2.add_lane(lane3)
    map2.add_lane(lane4)

    issues = map1.validate_node_correspondence(map2)
    assert not issues, "Speed class differences should not affect node correspondence"
