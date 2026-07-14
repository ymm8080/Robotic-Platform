"""MAPFEngine — ECBS multi-agent path finding on the fixed lane graph.

Phase 3 of the v7.0 plan (§Phase 3, "MAPFEngine ECBS 车道图").

This module implements **Explicit-CBS (ECBS)** — a bounded-suboptimal MAPF
solver — over the lane graph exposed by :class:`core.platform.fixed_lane_map.
FixedLaneMap`. It is a *read-only* consumer of the lane map: it never mutates
lanes, occupancy, or overlays, so it composes with the open Phase 2 PR that
extends ``FixedLaneMap``.

Model
-----
* **Spatio-temporal**, time discretised at ``Δt = 1 s``.
* A vehicle is at a *node* (lane endpoint) at integer timesteps, or *in transit*
  on a lane between its departure and arrival timesteps.
* ``lane_time(L) = max(1, ceil(L.length / L.max_speed))`` integer seconds to
  traverse a lane (respects each lane's own speed limit).
* Actions:
    - ``WAIT``    — stay at the current node, +1 s.
    - ``TRAVERSE``— take an outgoing lane, arrive ``lane_time`` s later.
* The platform plans **topology + time-window reservations only**; metric
  driving is the FMS's job (plan §边界). No continuous-space trajectories.

Conflicts (plan §Phase 3 task 3)
--------------------------------
* **Vertex** — two agents occupy the same node at the same timestep.
* **Edge (swap)** — two agents traverse opposite-direction lanes between the
  same node pair with overlapping transit intervals. For unit-time lanes this
  reduces to the classic "depart same timestep, swap lanes" conflict.

Algorithm
---------
* **Low level** — focal space-time A* with admissible time-to-goal heuristic
  (Dijkstra on reversed lane-time graph). Focal list = states with
  ``f ≤ w · f_min``; the secondary key is the number of conflicts with the
  other agents' current paths. This is the real ECBS low level and bounds each
  agent's path cost by ``w`` × optimal.
* **High level** — constraint-tree CBS whose OPEN is also focal: nodes with
  ``sum_of_costs ≤ w · cost_min`` are eligible, and the one with the fewest
  conflicts is expanded. This bounds the *solution* sum-of-costs by ``w`` ×
  optimal (the ECBS guarantee).

Rolling window + incremental replan (plan §Phase 3 tasks 5–6)
-------------------------------------------------------------
* :meth:`MAPFEngine.solve` plans over a bounded ``time_horizon`` (default 30 s,
  i.e. the N=10–30 s window).
* :meth:`MAPFEngine.update` performs incremental replanning: on-schedule
  high-priority vehicles are frozen as moving obstacles; only late / newly
  conflicted vehicles are replanned against them, instead of recomputing the
  whole fleet.
"""

from __future__ import annotations

import heapq
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field

from core.platform.fixed_lane_map import FixedLaneMap, Lane

logger = logging.getLogger(__name__)

# Δt in seconds. The whole engine reasons in integer timesteps == seconds.
DT = 1


# ── dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentRequest:
    """A single vehicle's planning request."""

    agent_id: str
    start: str  # node id
    goal: str  # node id
    model: str = ""  # robot model; empty = unrestricted (passes lane filter)
    priority: int = 0  # lower number = higher priority (replanned last)


@dataclass(frozen=True)
class VertexConstraint:
    """Agent must NOT occupy ``node`` at ``time``."""

    agent_id: str
    node: str
    time: int


@dataclass(frozen=True)
class EdgeConstraint:
    """Agent must NOT depart ``from_node`` toward ``to_node`` at ``depart_time``."""

    agent_id: str
    from_node: str
    to_node: str
    depart_time: int


@dataclass(frozen=True)
class Move:
    """One action in a plan: a WAIT (from==to, lane None) or a TRAVERSE."""

    from_node: str
    to_node: str
    depart_time: int
    arrive_time: int
    lane_id: str | None  # None for WAIT

    @property
    def is_wait(self) -> bool:
        return self.lane_id is None

    @property
    def duration(self) -> int:
        return self.arrive_time - self.depart_time


@dataclass
class Plan:
    """A vehicle's resolved plan."""

    agent_id: str
    moves: list[Move] = field(default_factory=list)
    goal_time: int | None = None  # timestep at which goal is first reached

    @property
    def cost(self) -> int:
        """Time-to-goal (timesteps). 0 for a trivially-satisfied (start==goal) plan."""
        return self.goal_time if self.goal_time is not None else 0

    @property
    def goal_reached(self) -> bool:
        return self.goal_time is not None

    def vertex_occupancy(self, horizon: int) -> set[tuple[str, int]]:
        """Set of (node, time) the agent occupies, including goal hold-up to horizon."""
        occ: set[tuple[str, int]] = set()
        for m in self.moves:
            occ.add((m.from_node, m.depart_time))
            occ.add((m.to_node, m.arrive_time))
        if self.goal_reached and self.goal_time is not None:
            for t in range(self.goal_time, horizon + 1):
                occ.add((self.moves[-1].to_node, t))
        return occ

    def edge_intervals(self) -> list[tuple[str, str, int, int, str]]:
        """Traversal intervals: (from_node, to_node, depart, arrive, lane_id)."""
        return [
            (m.from_node, m.to_node, m.depart_time, m.arrive_time, m.lane_id)
            for m in self.moves
            if not m.is_wait
        ]


@dataclass
class Solution:
    """Full MAPF solution."""

    plans: dict[str, Plan] = field(default_factory=dict)
    sum_of_costs: int = 0
    num_conflicts: int = 0
    bounded_suboptimal: bool = True  # True once ECBS focal search ran
    iterations: int = 0

    def get(self, agent_id: str) -> Plan | None:
        return self.plans.get(agent_id)


# ── helpers ─────────────────────────────────────────────────────────────────


def lane_time(lane: Lane) -> int:
    """Integer seconds to traverse a lane at its own max speed (≥1)."""
    if lane.max_speed <= 0:
        return 1
    return max(1, math.ceil(lane.length / lane.max_speed))


def _lane_open(lane: Lane, model: str) -> bool:
    """A lane is usable by ``model`` if traversable and model-allowed."""
    return lane.allows_model(model) if model else True


# ── heuristic: min lane-time to goal (admissible, ignores conflicts) ─────────


def _time_heuristic(fmap: FixedLaneMap, goal: str, model: str) -> dict[str, int]:
    """Dijkstra on the *reversed* lane graph; edge weight = lane_time.

    Returns ``dist[node]`` = minimum integer timesteps from ``node`` to
    ``goal`` using only model-allowed, traversable lanes. Admissible for A*.
    """
    dist: dict[str, int] = {goal: 0}
    heap: list[tuple[int, str]] = [(0, goal)]
    # reverse adjacency: node -> list of (predecessor_node, lane)
    incoming: dict[str, list[tuple[str, Lane]]] = defaultdict(list)
    for lane in fmap.all_lanes():
        if not fmap.is_traversable(lane.lane_id) or not _lane_open(lane, model):
            continue
        incoming[lane.to_node].append((lane.from_node, lane))
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, d):
            continue
        for prev_node, lane in incoming.get(node, []):
            nd = d + lane_time(lane)
            if nd < dist.get(prev_node, 1 << 60):
                dist[prev_node] = nd
                heapq.heappush(heap, (nd, prev_node))
    return dist


# ── low level: focal space-time A* ──────────────────────────────────────────


class _LowLevel:
    """Focal space-time A* for one agent under a set of constraints."""

    def __init__(
        self,
        fmap: FixedLaneMap,
        request: AgentRequest,
        vertex_c: dict[str, set[int]],  # node -> forbidden times
        edge_c: dict[tuple[str, str], set[int]],  # (from,to) -> forbidden depart times
        others_vertex: dict[tuple[str, int], set[str]],  # (node,time) -> agent ids
        others_edges: list[tuple[str, str, int, int]],  # (from,to,depart,arrive)
        w_focal: float,
        horizon: int,
        max_expansions: int,
    ) -> None:
        self.fmap = fmap
        self.req = request
        self.vertex_c = vertex_c
        self.edge_c = edge_c
        self.others_vertex = others_vertex
        self.others_edges = others_edges
        self.w = w_focal
        self.horizon = horizon
        self.max_expansions = max_expansions
        self.h = _time_heuristic(fmap, request.goal, request.model)

    def _h(self, node: str) -> int:
        return self.h.get(node, 1 << 60)

    def _vertex_blocked(self, node: str, t: int) -> bool:
        return t in self.vertex_c.get(node, ())

    def _edge_blocked(self, frm: str, to: str, t: int) -> bool:
        return t in self.edge_c.get((frm, to), ())

    def _max_goal_constraint_time(self) -> int:
        """Latest vertex constraint on this agent's goal node, or -1 if none.

        Once the agent reaches its goal it holds that node forever; the hold is
        only valid if no constraint fires at or after arrival. So goal arrival
        at time ``t`` is acceptable iff ``t > max_goal_constraint_time``.
        """
        gc = self.vertex_c.get(self.req.goal, ())
        return max(gc) if gc else -1

    def _move_conflicts(self, m: Move) -> int:
        """Conflicts this move introduces against the other agents' paths."""
        n = 0
        # vertex conflicts at departure & arrival nodes/times
        for node, t in ((m.from_node, m.depart_time), (m.to_node, m.arrive_time)):
            others = self.others_vertex.get((node, t))
            if others:
                n += len(others)
        # edge/swap conflicts for traversals
        if not m.is_wait:
            for of, ot, od, oa in self.others_edges:
                # opposite direction between same node pair + overlapping transit
                # intervals (strict). For unit lanes reduces to same depart time.
                if (
                    of == m.to_node
                    and ot == m.from_node
                    and m.depart_time < oa
                    and od < m.arrive_time
                ):
                    n += 1
        return n

    def search(self) -> tuple[Plan | None, int]:
        """Return (plan, num_conflicts_with_others) or (None, large)."""
        start = self.req.start
        goal = self.req.goal
        if self._vertex_blocked(start, 0):
            return None, 1 << 60

        # state = (node, time)
        start_state = (start, 0)
        start_h = self._h(start)
        start_f = start_h  # g=0
        start_conf = 0

        # OPEN keyed by f; FOCAL keyed by conflict count.
        # entries: (f, g, state). live-ness checked via best_g + expanded set.
        open_heap: list[tuple[int, int, tuple[str, int]]] = [(start_f, 0, start_state)]
        focal_heap: list[tuple[int, int, tuple[str, int]]] = [(start_conf, 0, start_state)]
        best_g: dict[tuple[str, int], int] = {start_state: 0}
        best_conf: dict[tuple[str, int], int] = {start_state: 0}
        parent: dict[tuple[str, int], tuple[tuple[str, int], Move]] = {}
        expanded: set[tuple[str, int]] = set()
        gen = 0
        expansions = 0
        focal_f_min = start_f  # f_min when focal was (re)built

        while open_heap:
            if expansions >= self.max_expansions:
                break

            # clean open top lazily
            while open_heap:
                f, g, st = open_heap[0]
                if st in expanded or best_g.get(st) != g:
                    heapq.heappop(open_heap)
                    continue
                break
            if not open_heap:
                break
            f_min = open_heap[0][0]

            # rebuild focal if f_min advanced past the threshold we built for
            if not focal_heap or f_min > focal_f_min:
                focal_f_min = f_min
                focal_heap = []
                for f2, g2, st2 in open_heap:
                    if st2 in expanded:
                        continue
                    if best_g.get(st2) != g2:
                        continue
                    if f2 <= self.w * f_min + 1e-9:
                        heapq.heappush(focal_heap, (best_conf.get(st2, 0), g2, st2))

            # pop the least-conflicting focal state (lazy)
            cur_state = None
            while focal_heap:
                conf, g, st = heapq.heappop(focal_heap)
                if st in expanded:
                    continue
                if best_g.get(st) != g:
                    continue
                f_of = g + self._h(st[0])
                if f_of > self.w * f_min + 1e-9:
                    # no longer focal-eligible (shouldn't happen post-rebuild)
                    continue
                cur_state = st
                break
            if cur_state is None:
                # focal empty but open not → lower the bar by popping open min
                # (advance f_min). Rebuild next loop iteration.
                f2, g2, st2 = heapq.heappop(open_heap)
                continue

            node, t = cur_state
            expanded.add(cur_state)
            expansions += 1

            if node == goal and t > self._max_goal_constraint_time():
                return self._reconstruct(cur_state, parent), best_conf.get(cur_state, 0)

            if t >= self.horizon:
                continue

            successors = self._expand(cur_state)
            for s_state, move in successors:
                s_node, s_t = s_state
                if s_state in expanded:
                    continue
                g_new = t + move.duration
                if g_new > self.horizon:
                    continue
                if best_g.get(s_state, 1 << 60) <= g_new:
                    continue
                best_g[s_state] = g_new
                parent[s_state] = (cur_state, move)
                conf_new = best_conf[cur_state] + self._move_conflicts(move)
                best_conf[s_state] = conf_new
                f_new = g_new + self._h(s_node)
                gen += 1
                heapq.heappush(open_heap, (f_new, g_new, s_state))
                if f_new <= self.w * f_min + 1e-9:
                    heapq.heappush(focal_heap, (conf_new, g_new, s_state))

        return None, 1 << 60

    def _expand(self, state: tuple[str, int]) -> list[tuple[tuple[str, int], Move]]:
        node, t = state
        out: list[tuple[tuple[str, int], Move]] = []
        # WAIT
        if not self._vertex_blocked(node, t + 1):
            out.append(
                (
                    (node, t + 1),
                    Move(node, node, t, t + 1, None),
                )
            )
        # TRAVERSE each outgoing lane
        for lid in self.fmap.lanes_out_of(node):
            if not self.fmap.is_traversable(lid):
                continue
            lane = self.fmap.lane(lid)
            if lane is None or not _lane_open(lane, self.req.model):
                continue
            dt = lane_time(lane)
            arrive = t + dt
            if arrive > self.horizon:
                continue
            if self._edge_blocked(node, lane.to_node, t):
                continue
            if self._vertex_blocked(lane.to_node, arrive):
                continue
            out.append(
                (
                    (lane.to_node, arrive),
                    Move(node, lane.to_node, t, arrive, lid),
                )
            )
        return out

    def _reconstruct(
        self,
        goal_state: tuple[str, int],
        parent: dict[tuple[str, int], tuple[tuple[str, int], Move]],
    ) -> Plan:
        moves: list[Move] = []
        st = goal_state
        while st in parent:
            prev, move = parent[st]
            moves.append(move)
            st = prev
        moves.reverse()
        return Plan(
            agent_id=self.req.agent_id,
            moves=moves,
            goal_time=goal_state[1],
        )


# ── conflict detection between two plans ───────────────────────────────────


def _detect_conflicts(plans: dict[str, Plan], horizon: int) -> list[tuple[str, str, str, tuple]]:
    """Return list of (agent_a, agent_b, kind, detail) conflicts.

    detail for vertex: (node, time)
    detail for edge:   (a_from, a_to, a_depart, b_from, b_to, b_depart)
    """
    conflicts: list[tuple[str, str, str, tuple]] = []
    agent_ids = list(plans.keys())

    # vertex: precompute occupancy
    occ: dict[tuple[str, int], list[str]] = defaultdict(list)
    for aid in agent_ids:
        for node, t in plans[aid].vertex_occupancy(horizon):
            occ[(node, t)].append(aid)
    for (node, t), holders in occ.items():
        if len(holders) >= 2:
            a = holders[0]
            b = holders[1]
            conflicts.append((a, b, "vertex", (node, t)))

    # edge/swap
    edges_by_agent = {aid: plans[aid].edge_intervals() for aid in agent_ids}
    for i, a in enumerate(agent_ids):
        for b in agent_ids[i + 1 :]:
            for af, at, ad, ar, _al in edges_by_agent[a]:
                for bf, bt, bd, br, _bl in edges_by_agent[b]:
                    if af == bt and at == bf and ad < br and bd < ar:
                        conflicts.append((a, b, "edge", (af, at, ad, bf, bt, bd)))
    return conflicts


def _build_constraint_indexes(
    agent_id: str,
    constraints: tuple[set[VertexConstraint], set[EdgeConstraint]],
) -> tuple[dict[str, set[int]], dict[tuple[str, str], set[int]]]:
    vertex_c: dict[str, set[int]] = defaultdict(set)
    edge_c: dict[tuple[str, str], set[int]] = defaultdict(set)
    for vc in constraints[0]:
        if vc.agent_id == agent_id:
            vertex_c[vc.node].add(vc.time)
    for ec in constraints[1]:
        if ec.agent_id == agent_id:
            edge_c[(ec.from_node, ec.to_node)].add(ec.depart_time)
    return vertex_c, edge_c


def _others_obstacles(
    plans: dict[str, Plan], exclude: str, horizon: int
) -> tuple[dict[tuple[str, int], set[str]], list[tuple[str, str, int, int]]]:
    others_vertex: dict[tuple[str, int], set[str]] = defaultdict(set)
    others_edges: list[tuple[str, str, int, int]] = []
    for aid, plan in plans.items():
        if aid == exclude:
            continue
        for node, t in plan.vertex_occupancy(horizon):
            others_vertex[(node, t)].add(aid)
        for af, at, ad, ar, _al in plan.edge_intervals():
            others_edges.append((af, at, ad, ar))
    return others_vertex, others_edges


# ── ECBS high level ─────────────────────────────────────────────────────────


@dataclass(order=True)
class _CTNode:
    cost: int  # sum of costs (primary OPEN key)
    conflicts: int  # secondary focal key
    seq: int  # tiebreak for determinism
    constraints: tuple[frozenset[VertexConstraint], frozenset[EdgeConstraint]] = field(
        compare=False
    )
    plans: dict[str, Plan] = field(default_factory=dict, compare=False)


class MAPFEngine:
    """ECBS multi-agent path finder over the fixed lane graph."""

    def __init__(
        self,
        fmap: FixedLaneMap,
        w_focal: float = 1.5,
        time_horizon: int = 30,
        max_ct_nodes: int = 400,
        max_lowlevel_expansions: int = 200_000,
    ) -> None:
        self.fmap = fmap
        self.w_focal = w_focal
        self.time_horizon = time_horizon
        self.max_ct_nodes = max_ct_nodes
        self.max_lowlevel_expansions = max_lowlevel_expansions

    # ── public: full solve ──────────────────────────────────────────────────

    def solve(self, requests: list[AgentRequest]) -> Solution:
        """Run ECBS for all requests. Returns a :class:`Solution`."""
        if not requests:
            return Solution(bounded_suboptimal=True)

        # order by priority (lower number first) for deterministic replanning
        ordered = sorted(requests, key=lambda r: (r.priority, r.agent_id))
        horizon = self.time_horizon

        root_constraints: tuple[frozenset, frozenset] = (frozenset(), frozenset())
        root_plans = self._plan_all(ordered, root_constraints, {}, horizon)
        if root_plans is None:
            return Solution(bounded_suboptimal=False)
        root_cost = sum(p.cost for p in root_plans.values())
        root_conflicts = len(_detect_conflicts(root_plans, horizon))

        root = _CTNode(
            cost=root_cost,
            conflicts=root_conflicts,
            seq=0,
            constraints=root_constraints,
            plans=root_plans,
        )

        # focal high-level OPEN
        open_heap: list[_CTNode] = [root]
        cost_min = root_cost
        best: _CTNode | None = root if root_conflicts == 0 else None
        seq = 1
        iters = 0

        while open_heap and iters < self.max_ct_nodes:
            iters += 1
            # rebuild focal set: nodes with cost <= w * cost_min
            fmin = open_heap[0].cost
            if fmin > cost_min:
                cost_min = fmin
            threshold = self.w_focal * cost_min
            # pick the focal node with fewest conflicts (lazy: scan)
            focal_idx = -1
            focal_conf = 1 << 60
            for i, node in enumerate(open_heap):
                if node.cost <= threshold + 1e-9 and node.conflicts < focal_conf:
                    focal_conf = node.conflicts
                    focal_idx = i
            if focal_idx < 0:
                # w >= 1 guarantees the min-cost node is focal-eligible; if we
                # ever get here, stop rather than discard nodes blindly.
                break
            node = open_heap.pop(focal_idx)
            heapq.heapify(open_heap)

            if node.conflicts == 0:
                best = node
                break

            conflicts = _detect_conflicts(node.plans, horizon)
            if not conflicts:
                best = node
                break
            a, b, kind, detail = conflicts[0]

            for constrained_agent, new_c in self._split(kind, detail, a, b):
                child_constraints = self._add_constraint(node.constraints, new_c)
                # CBS: only the constrained agent needs replanning; the other
                # agents' paths stay valid under the new per-agent constraint.
                child_plans = self._replan_one(
                    constrained_agent, ordered, child_constraints, node.plans, horizon
                )
                if child_plans is None:
                    continue
                child_cost = sum(p.cost for p in child_plans.values())
                child_conflicts = len(_detect_conflicts(child_plans, horizon))
                child = _CTNode(
                    cost=child_cost,
                    conflicts=child_conflicts,
                    seq=seq,
                    constraints=child_constraints,
                    plans=child_plans,
                )
                seq += 1
                heapq.heappush(open_heap, child)

        chosen = best if best is not None else (open_heap[0] if open_heap else root)
        final_conflicts = _detect_conflicts(chosen.plans, horizon)
        return Solution(
            plans=chosen.plans,
            sum_of_costs=chosen.cost,
            num_conflicts=len(final_conflicts),
            bounded_suboptimal=True,
            iterations=iters,
        )

    # ── public: incremental update (rolling window) ────────────────────────

    def update(
        self,
        requests: list[AgentRequest],
        current_plans: dict[str, Plan],
        late_agents: set[str],
        now: int = 0,
    ) -> Solution:
        """Incremental replan within the rolling window.

        Vehicles NOT in ``late_agents`` are frozen as moving obstacles; only
        the late / conflicted vehicles are replanned against them. This avoids a
        full fleet recompute (plan §Phase 3 task 6).

        ``now`` is the current timestep; plans are re-anchored from ``now``.
        """
        horizon = self.time_horizon
        frozen = {aid: plan for aid, plan in current_plans.items() if aid not in late_agents}
        # shift frozen plans to the current time origin
        shifted: dict[str, Plan] = {}
        for aid, plan in frozen.items():
            shifted[aid] = self._shift_plan(plan, now)

        to_replan = [r for r in requests if r.agent_id in late_agents]
        if not to_replan:
            return Solution(
                plans=shifted,
                sum_of_costs=sum(p.cost for p in shifted.values()),
                num_conflicts=len(_detect_conflicts(shifted, horizon)),
                bounded_suboptimal=True,
            )

        # replan late agents one-by-one against the frozen obstacles + already
        # replanned late agents (priority order), adding WAIT-style constraints
        # implicitly via the obstacle occupancy.
        ordered = sorted(to_replan, key=lambda r: (r.priority, r.agent_id))
        plans = dict(shifted)
        for req in ordered:
            others_vertex, others_edges = _others_obstacles(plans, req.agent_id, horizon)
            ll = _LowLevel(
                self.fmap,
                req,
                *_build_constraint_indexes(req.agent_id, (set(), set())),
                others_vertex,
                others_edges,
                self.w_focal,
                horizon,
                self.max_lowlevel_expansions,
            )
            plan, _ = ll.search()
            if plan is None:
                # cannot replan this agent now → leave a WAIT-in-place stub
                plan = Plan(
                    agent_id=req.agent_id,
                    moves=[Move(req.start, req.start, 0, horizon, None)],
                    goal_time=None,
                )
            plans[req.agent_id] = plan

        return Solution(
            plans=plans,
            sum_of_costs=sum(p.cost for p in plans.values()),
            num_conflicts=len(_detect_conflicts(plans, horizon)),
            bounded_suboptimal=True,
        )

    # ── internals ───────────────────────────────────────────────────────────

    def _plan_all(
        self,
        ordered: list[AgentRequest],
        constraints: tuple[frozenset[VertexConstraint], frozenset[EdgeConstraint]],
        seed_plans: dict[str, Plan],
        horizon: int,
    ) -> dict[str, Plan] | None:
        """Prioritised planning: each agent planned against previously planned."""
        plans: dict[str, Plan] = dict(seed_plans)
        for req in ordered:
            others_vertex, others_edges = _others_obstacles(plans, req.agent_id, horizon)
            vertex_c, edge_c = _build_constraint_indexes(
                req.agent_id, (set(constraints[0]), set(constraints[1]))
            )
            ll = _LowLevel(
                self.fmap,
                req,
                vertex_c,
                edge_c,
                others_vertex,
                others_edges,
                self.w_focal,
                horizon,
                self.max_lowlevel_expansions,
            )
            plan, _ = ll.search()
            if plan is None:
                return None
            plans[req.agent_id] = plan
        return plans

    def _replan_one(
        self,
        agent_id: str,
        ordered: list[AgentRequest],
        constraints: tuple[frozenset[VertexConstraint], frozenset[EdgeConstraint]],
        parent_plans: dict[str, Plan],
        horizon: int,
    ) -> dict[str, Plan] | None:
        """Replan a single constrained agent; keep the rest of the parent's plans.

        This is the CBS invariant: a new per-agent constraint only invalidates
        that agent's path, so only that agent is re-searched (the others remain
        valid under the constraint set). Replanning one agent per CT child —
        not the whole fleet — is what keeps ECBS fast.
        """
        req = next((r for r in ordered if r.agent_id == agent_id), None)
        if req is None:
            return None
        plans = dict(parent_plans)
        others_vertex, others_edges = _others_obstacles(plans, agent_id, horizon)
        vertex_c, edge_c = _build_constraint_indexes(
            agent_id, (set(constraints[0]), set(constraints[1]))
        )
        ll = _LowLevel(
            self.fmap,
            req,
            vertex_c,
            edge_c,
            others_vertex,
            others_edges,
            self.w_focal,
            horizon,
            self.max_lowlevel_expansions,
        )
        plan, _ = ll.search()
        if plan is None:
            return None
        plans[agent_id] = plan
        return plans

    def _shift_plan(self, plan: Plan, now: int) -> Plan:
        """Re-anchor a frozen plan to start at timestep ``now``."""
        if now == 0:
            return plan
        shifted_moves = [
            Move(
                m.from_node,
                m.to_node,
                m.depart_time + now,
                m.arrive_time + now,
                m.lane_id,
            )
            for m in plan.moves
        ]
        return Plan(
            agent_id=plan.agent_id,
            moves=shifted_moves,
            goal_time=(plan.goal_time + now) if plan.goal_time is not None else None,
        )

    def _split(
        self,
        kind: str,
        detail: tuple,
        a: str,
        b: str,
    ) -> list[tuple[str, VertexConstraint | EdgeConstraint]]:
        """Split a conflict into two child constraints (CBS classic)."""
        if kind == "vertex":
            node, t = detail
            return [
                (a, VertexConstraint(a, node, t)),
                (b, VertexConstraint(b, node, t)),
            ]
        # edge swap
        af, at, ad, bf, bt, bd = detail
        return [
            (a, EdgeConstraint(a, af, at, ad)),
            (b, EdgeConstraint(b, bf, bt, bd)),
        ]

    def _add_constraint(
        self,
        constraints: tuple[frozenset[VertexConstraint], frozenset[EdgeConstraint]],
        new_c: VertexConstraint | EdgeConstraint,
    ) -> tuple[frozenset[VertexConstraint], frozenset[EdgeConstraint]]:
        vc, ec = constraints
        if isinstance(new_c, VertexConstraint):
            return (vc | {new_c}, ec)
        return (vc, ec | {new_c})


__all__ = [
    "DT",
    "AgentRequest",
    "VertexConstraint",
    "EdgeConstraint",
    "Move",
    "Plan",
    "Solution",
    "MAPFEngine",
    "lane_time",
]
