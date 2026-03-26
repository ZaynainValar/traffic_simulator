from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, fields
from io import BytesIO
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Rectangle, FancyBboxPatch

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk


# =========================
# Configuration data model
# =========================


@dataclass
class VehicleTypeSpec:
    length: float
    height: float
    spawn_weight: float
    speed_factor: float


@dataclass
class DriverStyleSpec:
    spawn_weight: float
    desired_speed_bias: float
    front_gap_scale: float
    rear_gap_scale: float
    lane_change_threshold_scale: float
    left_pass_scale: float
    stay_put_scale: float
    alignment_scale: float
    right_return_scale: float
    yield_rear_gap_scale: float
    yield_speed_advantage_scale: float
    yield_target_min_gap_scale: float
    yield_speedup_scale: float
    cooldown_scale: float


@dataclass
class SimulatorConfig:
    num_lanes: int = 5
    base_road_length: float = 100.0
    zoom: float = 3.0
    horizontal_zoom: float = 1.0
    base_x_padding: float = 1.0
    base_y_padding: float = 0.25

    spawn_prob: float = 0.18
    spawn_clearance: float = 12.0
    min_desired_speed: float = 1.2
    max_desired_speed: float = 3.2

    safe_gap: float = 8.0
    hard_brake_gap: float = 4.5
    front_check_gap: float = 10.0
    rear_check_gap: float = 7.0
    merge_reserve_gap: float = 8.0

    accel: float = 0.08
    brake: float = 0.20
    lane_change_smoothing: float = 0.28
    normal_lane_change_time_factor: float = 2.0

    blocked_gap_buffer: float = 2.0
    lane_alignment_weight: float = 0.85
    stay_in_lane_bonus: float = 1.10
    left_pass_bonus: float = 1.35
    right_return_bonus: float = 0.70
    lane_change_threshold: float = 1.80

    yield_rear_gap: float = 12.0
    yield_speed_advantage: float = 0.55
    yield_target_min_gap: float = 11.0
    yield_speed_match_buffer: float = 0.25

    yield_speedup_step: float = 0.16
    yield_speedup_decay: float = 0.10
    yield_speedup_max_extra: float = 0.95

    lane_settle_tol: float = 0.08
    lane_change_cooldown_frames: int = 10
    aggressive_weaver_prob: float = 0.003
    cruise_move_min_gap: float = 12.0

    semi_right_lane_bonus: float = 3.4
    semi_middle_lane_penalty: float = 1.0
    semi_left_lane_penalty: float = 2.3

    base_interval_ms: int = 80
    simulation_fps: float = 12.5
    display_fps: float = 24.0
    simulation_time: float = 45.0
    num_simulations: int = 1
    seed: Optional[int] = 7

    vehicle_types: Dict[str, VehicleTypeSpec] = field(default_factory=lambda: {
        "sedan": VehicleTypeSpec(length=3.8, height=0.34, spawn_weight=0.62, speed_factor=1.05),
        "truck": VehicleTypeSpec(length=5.8, height=0.42, spawn_weight=0.28, speed_factor=0.92),
        "semi": VehicleTypeSpec(length=8.8, height=0.50, spawn_weight=0.10, speed_factor=0.82),
    })
    semi_spawn_lane_multipliers: Dict[int, float] = field(default_factory=lambda: {
        0: 1.55,
        1: 1.30,
        2: 0.30,
        3: 0.08,
        4: 0.03,
    })
    driver_styles: Dict[str, DriverStyleSpec] = field(default_factory=lambda: {
        "timid": DriverStyleSpec(
            spawn_weight=0.18,
            desired_speed_bias=-0.25,
            front_gap_scale=1.18,
            rear_gap_scale=1.22,
            lane_change_threshold_scale=1.15,
            left_pass_scale=0.80,
            stay_put_scale=1.20,
            alignment_scale=1.15,
            right_return_scale=1.15,
            yield_rear_gap_scale=1.18,
            yield_speed_advantage_scale=0.95,
            yield_target_min_gap_scale=1.10,
            yield_speedup_scale=0.85,
            cooldown_scale=1.20,
        ),
        "patient": DriverStyleSpec(
            spawn_weight=0.27,
            desired_speed_bias=-0.08,
            front_gap_scale=1.08,
            rear_gap_scale=1.06,
            lane_change_threshold_scale=1.05,
            left_pass_scale=0.95,
            stay_put_scale=1.10,
            alignment_scale=1.05,
            right_return_scale=1.10,
            yield_rear_gap_scale=1.05,
            yield_speed_advantage_scale=1.00,
            yield_target_min_gap_scale=1.05,
            yield_speedup_scale=0.95,
            cooldown_scale=1.10,
        ),
        "balanced": DriverStyleSpec(
            spawn_weight=0.40,
            desired_speed_bias=0.00,
            front_gap_scale=1.00,
            rear_gap_scale=1.00,
            lane_change_threshold_scale=1.00,
            left_pass_scale=1.00,
            stay_put_scale=1.00,
            alignment_scale=1.00,
            right_return_scale=1.00,
            yield_rear_gap_scale=1.00,
            yield_speed_advantage_scale=1.00,
            yield_target_min_gap_scale=1.00,
            yield_speedup_scale=1.00,
            cooldown_scale=1.00,
        ),
        "assertive": DriverStyleSpec(
            spawn_weight=0.15,
            desired_speed_bias=0.18,
            front_gap_scale=0.88,
            rear_gap_scale=0.88,
            lane_change_threshold_scale=0.82,
            left_pass_scale=1.18,
            stay_put_scale=0.88,
            alignment_scale=0.92,
            right_return_scale=0.92,
            yield_rear_gap_scale=0.90,
            yield_speed_advantage_scale=1.08,
            yield_target_min_gap_scale=0.90,
            yield_speedup_scale=1.12,
            cooldown_scale=0.82,
        ),
    })

    def refreshed(self) -> "SimulatorConfig":
        cfg = SimulatorConfig(
            **{
                f.name: getattr(self, f.name)
                for f in fields(SimulatorConfig)
                if f.name not in {"vehicle_types", "semi_spawn_lane_multipliers", "driver_styles"}
            }
        )
        cfg.vehicle_types = dict(self.vehicle_types)
        cfg.semi_spawn_lane_multipliers = dict(self.semi_spawn_lane_multipliers)
        cfg.driver_styles = dict(self.driver_styles)
        return cfg

    @property
    def road_length(self) -> float:
        return self.base_road_length * self.zoom * self.horizontal_zoom

    @property
    def visible_road_height(self) -> float:
        return (self.num_lanes + 2 * self.base_y_padding) * self.zoom

    @property
    def road_x_min(self) -> float:
        return 0.0

    @property
    def road_x_max(self) -> float:
        return self.road_length

    @property
    def road_y_min(self) -> float:
        return 0.0

    @property
    def road_y_max(self) -> float:
        return float(self.num_lanes)

    @property
    def camera_center_y(self) -> float:
        return self.num_lanes / 2.0

    @property
    def x_view_min(self) -> float:
        return self.road_x_min - self.base_x_padding

    @property
    def x_view_max(self) -> float:
        return self.road_x_max + self.base_x_padding

    @property
    def y_view_min(self) -> float:
        return self.camera_center_y - self.visible_road_height / 2.0

    @property
    def y_view_max(self) -> float:
        return self.camera_center_y + self.visible_road_height / 2.0

    @property
    def base_simulation_dt(self) -> float:
        return self.base_interval_ms / 1000.0

    @property
    def simulation_dt(self) -> float:
        return 1.0 / self.simulation_fps

    @property
    def display_dt(self) -> float:
        return 1.0 / self.display_fps

    @property
    def interval_ms(self) -> float:
        return 1000.0 / self.display_fps

    @property
    def sim_steps_per_sim(self) -> int:
        return max(1, int(math.ceil(self.simulation_time * self.simulation_fps)))

    @property
    def display_frames_per_sim(self) -> int:
        return max(2, int(round(self.simulation_time * self.display_fps)) + 1)

    @property
    def total_display_frames(self) -> int:
        return self.display_frames_per_sim * self.num_simulations

    @property
    def simulation_time_scale(self) -> float:
        return self.simulation_dt / self.base_simulation_dt

    @property
    def spawn_prob_per_step(self) -> float:
        return 1 - (1 - self.spawn_prob) ** self.simulation_time_scale

    @property
    def accel_per_step(self) -> float:
        return self.accel * self.simulation_time_scale

    @property
    def brake_per_step(self) -> float:
        return self.brake * self.simulation_time_scale

    @property
    def normal_lane_change_smoothing_per_step(self) -> float:
        base = 1 - (1 - self.lane_change_smoothing) ** self.simulation_time_scale
        return max(0.01, min(0.99, base / max(1.0, self.normal_lane_change_time_factor)))

    @property
    def weaver_lane_change_smoothing_per_step(self) -> float:
        return 1 - (1 - self.lane_change_smoothing) ** self.simulation_time_scale

    @property
    def yield_speedup_step_per_step(self) -> float:
        return self.yield_speedup_step * self.simulation_time_scale

    @property
    def yield_speedup_decay_per_step(self) -> float:
        return self.yield_speedup_decay * self.simulation_time_scale

    @property
    def lane_change_cooldown_steps_scaled(self) -> int:
        return max(1, int(round(self.lane_change_cooldown_frames / max(1e-6, self.simulation_time_scale))))


# =========================
# Simulation engine
# =========================


class TrafficSimulatorEngine:
    def __init__(self, config: Optional[SimulatorConfig] = None):
        self.config = config.refreshed() if config else SimulatorConfig()
        self.active_seed: Optional[int] = None
        self.rng = self._make_rng(self.config.seed)
        self.cars: List[Dict] = []
        self.next_car_id = 0
        self.precomputed_runs: Optional[List[Dict]] = None
        self.precomputed_cache_ready = False

    def _make_rng(self, seed: Optional[int]):
        if seed is None:
            resolved_seed = int(np.random.SeedSequence().entropy)
        else:
            resolved_seed = int(seed)
        self.active_seed = resolved_seed
        return np.random.default_rng(resolved_seed)

    def set_config(self, config: SimulatorConfig) -> None:
        self.config = config.refreshed()
        self.rng = self._make_rng(self.config.seed)
        self.reset_simulation()
        self.precomputed_runs = None
        self.precomputed_cache_ready = False

    def reset_simulation(self) -> None:
        self.cars = []
        self.next_car_id = 0

    def choose_vehicle_type(self) -> str:
        names = list(self.config.vehicle_types.keys())
        weights = np.array([self.config.vehicle_types[n].spawn_weight for n in names], dtype=float)
        weights /= weights.sum()
        return str(self.rng.choice(names, p=weights))

    def choose_driver_style(self) -> str:
        names = list(self.config.driver_styles.keys())
        weights = np.array([self.config.driver_styles[n].spawn_weight for n in names], dtype=float)
        weights /= weights.sum()
        return str(self.rng.choice(names, p=weights))

    def get_driver_profile(self, driver_style: str) -> DriverStyleSpec:
        return self.config.driver_styles.get(driver_style, self.config.driver_styles["balanced"])

    @staticmethod
    def snapshot_cars(cars_list: List[Dict]) -> List[Dict]:
        return [dict(car) for car in cars_list]

    @staticmethod
    def interpolate_cars(previous_snapshot: List[Dict], current_snapshot: List[Dict], alpha: float) -> List[Dict]:
        prev_map = {car["id"]: car for car in previous_snapshot}
        curr_map = {car["id"]: car for car in current_snapshot}
        draw_cars = []
        for car_id, curr in curr_map.items():
            prev = prev_map.get(car_id)
            if prev is None:
                draw_cars.append(dict(curr))
                continue
            blended = dict(curr)
            for key in ("x", "y", "speed"):
                blended[key] = prev[key] + alpha * (curr[key] - prev[key])
            draw_cars.append(blended)
        return draw_cars

    def speed_to_color(self, speed: float) -> Tuple[float, float, float]:
        scaled = np.clip((speed - self.config.min_desired_speed) / max(1e-6, (self.config.max_desired_speed - self.config.min_desired_speed)), 0.0, 1.0)
        red = 0.85 - 0.45 * scaled
        green = 0.25 + 0.35 * scaled
        blue = 0.20 + 0.70 * scaled
        return float(red), float(green), float(blue)

    def preferred_lane_center(self, vehicle_type: str, desired_speed: float) -> float:
        cfg = self.config
        if vehicle_type == "semi":
            return 0.65
        frac = (desired_speed - cfg.min_desired_speed) / max(1e-6, (cfg.max_desired_speed - cfg.min_desired_speed))
        frac = float(np.clip(frac, 0.0, 1.0))
        return frac * max(0, cfg.num_lanes - 1)

    def lane_suitability(self, vehicle_type: str, desired_speed: float, lane: int) -> float:
        cfg = self.config
        preferred = self.preferred_lane_center(vehicle_type, desired_speed)
        distance_penalty = abs(lane - preferred) / max(1.0, cfg.num_lanes - 1)
        score = max(0.03, 1.0 - 0.95 * distance_penalty)
        if vehicle_type == "semi":
            score *= cfg.semi_spawn_lane_multipliers.get(lane, 0.02)
        return float(np.clip(score, 0.0, 1.0))

    def gap_ahead(self, snapshot: List[Dict], lane: int, x: float, current_length: float, ignore_index: Optional[int] = None) -> Tuple[float, Optional[Dict]]:
        nearest_gap = math.inf
        leader = None
        for j, other in enumerate(snapshot):
            if ignore_index is not None and j == ignore_index:
                continue
            if other["lane"] != lane:
                continue
            if other["x"] <= x:
                continue
            gap = other["x"] - (x + current_length)
            if gap < nearest_gap:
                nearest_gap = gap
                leader = other
        return nearest_gap, leader

    def gap_behind(self, snapshot: List[Dict], lane: int, x: float, ignore_index: Optional[int] = None) -> Tuple[float, Optional[Dict]]:
        nearest_gap = math.inf
        follower = None
        for j, other in enumerate(snapshot):
            if ignore_index is not None and j == ignore_index:
                continue
            if other["lane"] != lane:
                continue
            if other["x"] >= x:
                continue
            gap = x - (other["x"] + other["length"])
            if gap < nearest_gap:
                nearest_gap = gap
                follower = other
        return nearest_gap, follower

    def lane_is_safe(
        self,
        snapshot: List[Dict],
        target_lane: int,
        x: float,
        current_length: float,
        ignore_index: Optional[int] = None,
        reserved_merges: Optional[List[Tuple[int, float]]] = None,
        front_gap_required: Optional[float] = None,
        rear_gap_required: Optional[float] = None,
    ) -> bool:
        cfg = self.config
        if target_lane < 0 or target_lane >= cfg.num_lanes:
            return False

        front_gap_required = cfg.front_check_gap if front_gap_required is None else front_gap_required
        rear_gap_required = cfg.rear_check_gap if rear_gap_required is None else rear_gap_required

        front_gap, _ = self.gap_ahead(snapshot, target_lane, x, current_length, ignore_index)
        rear_gap, _ = self.gap_behind(snapshot, target_lane, x, ignore_index)

        if front_gap < front_gap_required or rear_gap < rear_gap_required:
            return False

        if reserved_merges:
            for reserved_lane, reserved_x in reserved_merges:
                if reserved_lane == target_lane and abs(reserved_x - x) < cfg.merge_reserve_gap:
                    return False

        return True

    def lane_choice_score(
        self,
        state: Dict,
        candidate_lane: int,
        current_lane: int,
        candidate_gap: float,
        current_gap: float,
        profile: DriverStyleSpec,
    ) -> float:
        cfg = self.config
        preferred = self.preferred_lane_center(state["vehicle_type"], state["desired_speed"])
        usable_gap = min(candidate_gap, 22.0)
        gap_gain = min(candidate_gap - current_gap, 12.0)
        alignment_penalty = profile.alignment_scale * cfg.lane_alignment_weight * abs(candidate_lane - preferred)

        score = 0.75 * usable_gap + 1.10 * gap_gain - alignment_penalty

        if candidate_lane == current_lane:
            score += cfg.stay_in_lane_bonus * profile.stay_put_scale
        if candidate_lane > current_lane:
            score += cfg.left_pass_bonus * profile.left_pass_scale
        if candidate_lane < current_lane:
            score += cfg.right_return_bonus * profile.right_return_scale

        if state["vehicle_type"] == "semi":
            if candidate_lane <= 1:
                score += cfg.semi_right_lane_bonus
            elif candidate_lane == 2:
                score -= cfg.semi_middle_lane_penalty
            else:
                score -= cfg.semi_left_lane_penalty

        return float(score)

    def try_spawn_car(self) -> None:
        cfg = self.config
        for lane in range(cfg.num_lanes):
            if self.rng.random() >= cfg.spawn_prob_per_step:
                continue

            vehicle_type = self.choose_vehicle_type()
            driver_style = self.choose_driver_style()
            driver_profile = self.get_driver_profile(driver_style)
            vehicle = cfg.vehicle_types[vehicle_type]

            base_desired_speed = self.rng.uniform(cfg.min_desired_speed, cfg.max_desired_speed)
            base_desired_speed *= vehicle.speed_factor
            base_desired_speed += driver_profile.desired_speed_bias
            base_desired_speed = float(np.clip(base_desired_speed, cfg.min_desired_speed * 0.75, cfg.max_desired_speed))

            if self.rng.random() > self.lane_suitability(vehicle_type, base_desired_speed, lane):
                continue

            blocked = any(car["lane"] == lane and car["x"] < cfg.spawn_clearance + vehicle.length for car in self.cars)
            if blocked:
                continue

            is_weaver = bool(self.rng.random() < cfg.aggressive_weaver_prob)
            self.cars.append({
                "id": self.next_car_id,
                "vehicle_type": vehicle_type,
                "driver_style": driver_style,
                "length": vehicle.length,
                "height": vehicle.height,
                "x": 0.0,
                "lane": lane,
                "y": lane + 0.5,
                "speed": 0.65 * base_desired_speed,
                "desired_speed": base_desired_speed,
                "base_desired_speed": base_desired_speed,
                "yield_speed_boost": 0.0,
                "yielding_for_backup": False,
                "lane_change_cooldown": 0,
                "is_weaver": is_weaver,
            })
            self.next_car_id += 1

    def update_cars(self) -> None:
        cfg = self.config
        if not self.cars:
            return

        snapshot = [
            {
                "vehicle_type": car["vehicle_type"],
                "driver_style": car.get("driver_style", "balanced"),
                "length": car["length"],
                "height": car["height"],
                "x": car["x"],
                "lane": car["lane"],
                "y": car["y"],
                "speed": car["speed"],
                "desired_speed": car["desired_speed"],
                "base_desired_speed": car.get("base_desired_speed", car["desired_speed"]),
                "lane_change_cooldown": car.get("lane_change_cooldown", 0),
                "is_weaver": car.get("is_weaver", False),
                "id": car.get("id"),
            }
            for car in self.cars
        ]

        order = sorted(range(len(snapshot)), key=lambda i: snapshot[i]["x"], reverse=True)
        reserved_merges: List[Tuple[int, float]] = []

        for idx in order:
            state = snapshot[idx]
            car = self.cars[idx]
            profile = self.get_driver_profile(state.get("driver_style", "balanced"))

            current_lane = int(state["lane"])
            current_length = state["length"]
            x = state["x"]
            current_center_y = current_lane + 0.5
            mid_merge = abs(car["y"] - current_center_y) > cfg.lane_settle_tol
            is_weaver = bool(state.get("is_weaver", False))
            base_desired_speed = state.get("base_desired_speed", state["desired_speed"])
            yield_speed_boost = float(car.get("yield_speed_boost", 0.0))

            front_gap_required = cfg.front_check_gap * profile.front_gap_scale
            rear_gap_required = cfg.rear_check_gap * profile.rear_gap_scale
            effective_lane_change_threshold = cfg.lane_change_threshold * profile.lane_change_threshold_scale
            effective_yield_rear_gap = cfg.yield_rear_gap * profile.yield_rear_gap_scale
            effective_yield_speed_advantage = cfg.yield_speed_advantage * profile.yield_speed_advantage_scale
            effective_yield_target_min_gap = cfg.yield_target_min_gap * profile.yield_target_min_gap_scale

            desired_speed = float(np.clip(base_desired_speed + yield_speed_boost, cfg.min_desired_speed * 0.75, cfg.max_desired_speed))
            car["desired_speed"] = desired_speed

            current_gap, _ = self.gap_ahead(snapshot, current_lane, x, current_length, ignore_index=idx)
            blocked = current_gap < cfg.safe_gap + cfg.blocked_gap_buffer
            rear_gap, follower = self.gap_behind(snapshot, current_lane, x, ignore_index=idx)

            follower_wants_more_speed = (
                follower is not None and follower["desired_speed"] > desired_speed + effective_yield_speed_advantage
            )
            current_is_slower = (
                follower is not None
                and (
                    car["speed"] < follower["desired_speed"] - cfg.yield_speed_match_buffer
                    or desired_speed < follower["desired_speed"] - effective_yield_speed_advantage
                )
            )

            causing_backup = (
                (not is_weaver)
                and follower is not None
                and current_lane > 0
                and rear_gap < effective_yield_rear_gap
                and follower_wants_more_speed
                and current_is_slower
            )

            wants_to_yield_right = (
                (not is_weaver)
                and current_lane > 0
                and (causing_backup or car.get("yielding_for_backup", False))
            )

            cooldown_ready = car.get("lane_change_cooldown", 0) <= 0
            can_ignore_cooldown = is_weaver
            best_lane = current_lane
            lane_changed_for_backup = False
            blocked_right_yield = False

            if (not mid_merge) and (cooldown_ready or can_ignore_cooldown):
                if wants_to_yield_right:
                    candidate_lane = current_lane - 1
                    if self.lane_is_safe(
                        snapshot,
                        candidate_lane,
                        x,
                        current_length,
                        ignore_index=idx,
                        reserved_merges=reserved_merges,
                        front_gap_required=front_gap_required,
                        rear_gap_required=rear_gap_required,
                    ):
                        candidate_gap, _ = self.gap_ahead(snapshot, candidate_lane, x, current_length, ignore_index=idx)
                        if candidate_gap >= effective_yield_target_min_gap:
                            best_lane = candidate_lane
                            lane_changed_for_backup = True
                        else:
                            blocked_right_yield = True
                    else:
                        blocked_right_yield = True
                elif blocked:
                    candidate_lanes: List[int] = []
                    if current_lane + 1 < cfg.num_lanes:
                        candidate_lanes.append(current_lane + 1)
                    if current_lane - 1 >= 0:
                        candidate_lanes.append(current_lane - 1)

                    best_score = self.lane_choice_score(state, current_lane, current_lane, current_gap, current_gap, profile)
                    for candidate_lane in candidate_lanes:
                        if not self.lane_is_safe(
                            snapshot,
                            candidate_lane,
                            x,
                            current_length,
                            ignore_index=idx,
                            reserved_merges=reserved_merges,
                            front_gap_required=front_gap_required,
                            rear_gap_required=rear_gap_required,
                        ):
                            continue

                        candidate_gap, _ = self.gap_ahead(snapshot, candidate_lane, x, current_length, ignore_index=idx)
                        score = self.lane_choice_score(state, candidate_lane, current_lane, candidate_gap, current_gap, profile)
                        if score > best_score + effective_lane_change_threshold:
                            best_lane = candidate_lane
                            best_score = score
                elif is_weaver:
                    target_lane = self.preferred_lane_center(state["vehicle_type"], desired_speed)
                    lane_offset = target_lane - current_lane
                    if lane_offset > 0.55 and current_lane + 1 < cfg.num_lanes:
                        candidate_lane = current_lane + 1
                        if self.lane_is_safe(snapshot, candidate_lane, x, current_length, ignore_index=idx, reserved_merges=reserved_merges, front_gap_required=front_gap_required, rear_gap_required=rear_gap_required):
                            candidate_gap, _ = self.gap_ahead(snapshot, candidate_lane, x, current_length, ignore_index=idx)
                            if candidate_gap >= cfg.cruise_move_min_gap and car["speed"] >= 0.72 * desired_speed:
                                best_lane = candidate_lane
                    elif lane_offset < -0.55 and current_lane - 1 >= 0:
                        candidate_lane = current_lane - 1
                        if self.lane_is_safe(snapshot, candidate_lane, x, current_length, ignore_index=idx, reserved_merges=reserved_merges, front_gap_required=front_gap_required, rear_gap_required=rear_gap_required):
                            candidate_gap, _ = self.gap_ahead(snapshot, candidate_lane, x, current_length, ignore_index=idx)
                            if candidate_gap >= cfg.cruise_move_min_gap and car["speed"] >= 0.72 * desired_speed:
                                best_lane = candidate_lane

            if is_weaver:
                car["yielding_for_backup"] = False
                car["yield_speed_boost"] = 0.0
                desired_speed = base_desired_speed
                car["desired_speed"] = desired_speed
            else:
                if lane_changed_for_backup:
                    car["yielding_for_backup"] = False
                elif blocked_right_yield or causing_backup:
                    car["yielding_for_backup"] = current_lane > 0
                else:
                    car["yielding_for_backup"] = False

                if car["yielding_for_backup"] and (not lane_changed_for_backup):
                    follower_target_speed = follower["desired_speed"] if follower is not None else base_desired_speed
                    desired_cap = min(
                        cfg.max_desired_speed,
                        max(base_desired_speed, follower_target_speed - cfg.yield_speed_match_buffer, car["speed"] + 0.25),
                    )
                    requested_extra = min(
                        cfg.yield_speedup_max_extra * profile.yield_speedup_scale,
                        max(0.0, desired_cap - base_desired_speed),
                    )
                    yield_speed_boost = min(
                        requested_extra,
                        yield_speed_boost + cfg.yield_speedup_step_per_step * profile.yield_speedup_scale,
                    )
                else:
                    yield_speed_boost = max(0.0, yield_speed_boost - cfg.yield_speedup_decay_per_step)

                car["yield_speed_boost"] = yield_speed_boost
                desired_speed = float(np.clip(base_desired_speed + yield_speed_boost, cfg.min_desired_speed * 0.75, cfg.max_desired_speed))
                car["desired_speed"] = desired_speed

            if best_lane != current_lane:
                reserved_merges.append((best_lane, x))
                car["lane"] = best_lane
                if not is_weaver:
                    scaled_cooldown = max(1, int(round(cfg.lane_change_cooldown_steps_scaled * profile.cooldown_scale)))
                    car["lane_change_cooldown"] = scaled_cooldown
            else:
                car["lane"] = current_lane

            chosen_gap, chosen_lead = self.gap_ahead(snapshot, car["lane"], x, current_length, ignore_index=idx)
            if chosen_lead is None:
                target_speed = desired_speed
            else:
                target_speed = min(desired_speed, chosen_lead["speed"] + 0.10, max(0.0, 0.55 * chosen_gap))
                if chosen_gap < cfg.hard_brake_gap:
                    target_speed = min(target_speed, 0.25 * chosen_gap)

            if car["speed"] < target_speed:
                car["speed"] = min(target_speed, car["speed"] + cfg.accel_per_step)
            else:
                car["speed"] = max(target_speed, car["speed"] - cfg.brake_per_step)
            car["speed"] = max(0.0, car["speed"])

        for car in self.cars:
            car["x"] += car["speed"] * cfg.simulation_time_scale
            target_y = car["lane"] + 0.5
            smoothing = cfg.weaver_lane_change_smoothing_per_step if car.get("is_weaver", False) else cfg.normal_lane_change_smoothing_per_step
            car["y"] += smoothing * (target_y - car["y"])
            if car.get("lane_change_cooldown", 0) > 0:
                car["lane_change_cooldown"] -= 1

        self.cars = [car for car in self.cars if car["x"] <= cfg.road_x_max]

    def precompute_simulation_cache(self, progress_callback: Optional[Callable[[int, int, str], None]] = None) -> None:
        cfg = self.config
        self.precomputed_runs = []
        self.precomputed_cache_ready = False

        total_steps = cfg.sim_steps_per_sim * cfg.num_simulations
        completed = 0

        for sim_number in range(1, cfg.num_simulations + 1):
            self.reset_simulation()
            snapshots = [self.snapshot_cars(self.cars)]
            times = [0.0]
            sim_elapsed = 0.0

            for _ in range(cfg.sim_steps_per_sim):
                self.try_spawn_car()
                self.update_cars()
                sim_elapsed += cfg.simulation_dt
                snapshots.append(self.snapshot_cars(self.cars))
                times.append(sim_elapsed)
                completed += 1
                if progress_callback is not None:
                    progress_callback(completed, total_steps, f"Precomputing simulation {sim_number}/{cfg.num_simulations}")

            self.precomputed_runs.append({
                "sim_number": sim_number,
                "snapshots": snapshots,
                "times": times,
            })

        self.precomputed_cache_ready = True

    def get_precomputed_frame_state(self, frame: int) -> Dict:
        cfg = self.config
        if not self.precomputed_cache_ready or self.precomputed_runs is None:
            raise RuntimeError("Simulation cache is not ready.")

        sim_index = min(cfg.num_simulations - 1, frame // cfg.display_frames_per_sim)
        frame_in_sim = frame % cfg.display_frames_per_sim
        run = self.precomputed_runs[sim_index]
        target_time = frame_in_sim * cfg.display_dt
        times = run["times"]
        upper_idx = min(len(times) - 1, int(np.searchsorted(times, target_time, side="left")))
        lower_idx = max(0, upper_idx - 1)

        if upper_idx == lower_idx:
            alpha = 0.0
        else:
            dt = times[upper_idx] - times[lower_idx]
            alpha = 0.0 if dt <= 1e-12 else (target_time - times[lower_idx]) / dt
            alpha = float(np.clip(alpha, 0.0, 1.0))

        draw_cars = self.interpolate_cars(run["snapshots"][lower_idx], run["snapshots"][upper_idx], alpha)
        return {
            "draw_cars": draw_cars,
            "frame_in_sim": frame_in_sim,
            "sim_number": run["sim_number"],
            "target_time": target_time,
            "sim_step_display": upper_idx,
        }

    def draw_vehicle(self, ax, car: Dict, clip_path=None) -> None:
        x = car["x"]
        y_center = car["y"]
        length = car["length"]
        height = car["height"]
        body_color = self.speed_to_color(car["speed"])
        y0 = y_center - height / 2

        if car["vehicle_type"] == "sedan":
            body = FancyBboxPatch((x, y0), length, height, boxstyle="round,pad=0.02,rounding_size=0.10", linewidth=0.8, edgecolor="black", facecolor=body_color, zorder=3)
            ax.add_patch(body)
            window = Rectangle((x + 0.55 * length, y0 + 0.17 * height), 0.24 * length, 0.50 * height, facecolor="lightsteelblue", edgecolor="none", zorder=4)
            ax.add_patch(window)
            patches = [body, window]
        elif car["vehicle_type"] == "truck":
            cargo = Rectangle((x, y0), 0.72 * length, height, facecolor=body_color, edgecolor="black", linewidth=0.8, zorder=3)
            cab = Rectangle((x + 0.72 * length, y0 + 0.08 * height), 0.28 * length, 0.84 * height, facecolor=body_color, edgecolor="black", linewidth=0.8, zorder=3)
            window = Rectangle((x + 0.80 * length, y0 + 0.45 * height), 0.11 * length, 0.24 * height, facecolor="lightsteelblue", edgecolor="none", zorder=4)
            for patch in (cargo, cab, window):
                ax.add_patch(patch)
            patches = [cargo, cab, window]
        else:
            trailer = Rectangle((x, y0), 0.72 * length, height, facecolor=body_color, edgecolor="black", linewidth=0.8, zorder=3)
            hitch = Rectangle((x + 0.72 * length, y0 + 0.40 * height), 0.06 * length, 0.20 * height, facecolor="black", edgecolor="black", linewidth=0.6, zorder=4)
            cab = Rectangle((x + 0.78 * length, y0 + 0.08 * height), 0.22 * length, 0.84 * height, facecolor=body_color, edgecolor="black", linewidth=0.8, zorder=3)
            window = Rectangle((x + 0.86 * length, y0 + 0.46 * height), 0.08 * length, 0.22 * height, facecolor="lightsteelblue", edgecolor="none", zorder=4)
            for patch in (trailer, hitch, cab, window):
                ax.add_patch(patch)
            patches = [trailer, hitch, cab, window]

        if clip_path is not None:
            for patch in patches:
                patch.set_clip_path(clip_path)

    def render_frame(self, ax, frame: int) -> None:
        cfg = self.config
        frame_state = self.get_precomputed_frame_state(frame)
        draw_cars = frame_state["draw_cars"]
        frame_in_sim = frame_state["frame_in_sim"]
        target_time = frame_state["target_time"]
        sim_step_display = frame_state["sim_step_display"]
        current_simulation = frame_state["sim_number"]

        ax.clear()
        ax.set_facecolor("darkolivegreen")

        road_patch = Rectangle((cfg.road_x_min, cfg.road_y_min), cfg.road_x_max - cfg.road_x_min, cfg.road_y_max - cfg.road_y_min, facecolor="dimgray", edgecolor="none", zorder=0)
        ax.add_patch(road_patch)

        for lane in range(cfg.num_lanes + 1):
            ax.plot([cfg.road_x_min, cfg.road_x_max], [lane, lane], color="white", linewidth=2, zorder=1)

        for car in draw_cars:
            self.draw_vehicle(ax, car, clip_path=road_patch)

        ax.set_xlim(cfg.x_view_min, cfg.x_view_max)
        ax.set_ylim(cfg.y_view_min, cfg.y_view_max)
        ax.set_aspect("auto")
        ax.set_xticks([])
        ax.set_yticks([lane + 0.5 for lane in range(cfg.num_lanes)])
        ax.set_yticklabels([f"L{lane + 1}" for lane in range(cfg.num_lanes)])
        ax.set_title(
            f"{cfg.num_lanes}-Lane Traffic Sim | Display {cfg.display_fps:.0f} FPS | Sim {cfg.simulation_fps:.2f} FPS | "
            f"Zoom {cfg.zoom:.2f}x / HZoom {cfg.horizontal_zoom:.2f}x | Road {cfg.road_length:.0f} | "
            f"Run {current_simulation}/{cfg.num_simulations} | Frame {frame_in_sim + 1}/{cfg.display_frames_per_sim} | "
            f"Step {sim_step_display}/{cfg.sim_steps_per_sim} | t={target_time:.2f}s",
            fontsize=8,
            pad=10,
        )


    def prerender_frame_png_bytes(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        target_pixel_size: Optional[Tuple[int, int]] = None,
    ) -> List[bytes]:
        if not self.precomputed_cache_ready:
            self.precompute_simulation_cache(progress_callback=progress_callback)

        cfg = self.config
        if target_pixel_size is None:
            pixel_width, pixel_height = 1320, 506
        else:
            pixel_width = max(960, int(target_pixel_size[0]))
            pixel_height = max(420, int(target_pixel_size[1]))

        dpi = 100
        fig = Figure(figsize=(pixel_width / dpi, pixel_height / dpi), dpi=dpi)
        ax = fig.add_subplot(111)
        fig.subplots_adjust(left=0.06, right=0.995, top=0.90, bottom=0.12)

        rendered_frames: List[bytes] = []
        total = cfg.total_display_frames

        for frame in range(total):
            self.render_frame(ax, frame)
            buffer = BytesIO()
            fig.savefig(buffer, format="png", dpi=dpi)
            rendered_frames.append(buffer.getvalue())
            if progress_callback is not None:
                progress_callback(frame + 1, total, "Prerendering display frames")

        return rendered_frames

    def export_html(self, output_path: Path, progress_callback: Optional[Callable[[int, int, str], None]] = None) -> None:
        if not self.precomputed_cache_ready:
            self.precompute_simulation_cache(progress_callback=progress_callback)

        cfg = self.config
        fig = Figure(figsize=(12, 3.5))
        ax = fig.add_subplot(111)
        html_chunks = [
            "<html><head><meta charset='utf-8'><title>Traffic Simulator HTML Player</title></head><body>",
            "<h2>Traffic Simulator HTML Player</h2>",
            f"<p>Lanes: {cfg.num_lanes} | Simulation time: {cfg.simulation_time:.1f}s | Display FPS: {cfg.display_fps:.0f}</p>",
        ]

        png_dir = output_path.with_suffix("")
        png_dir.mkdir(parents=True, exist_ok=True)
        total = cfg.total_display_frames
        import base64
        from io import BytesIO

        for frame in range(total):
            self.render_frame(ax, frame)
            buffer = BytesIO()
            fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            html_chunks.append(f"<img src='data:image/png;base64,{encoded}' style='width:100%;max-width:1200px;display:block;margin:0 auto 10px auto;'>")
            if progress_callback is not None:
                progress_callback(frame + 1, total, "Building HTML player")

        html_chunks.append("</body></html>")
        output_path.write_text("\n".join(html_chunks), encoding="utf-8")


# =========================
# Desktop UI
# =========================



class TrafficSimulatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Traffic Simulator UI")

        self.engine = TrafficSimulatorEngine()
        self.current_frame = 0
        self.playing = False
        self.after_id = None
        self.param_vars: Dict[str, tk.Variable] = {}
        self.controls: Dict[str, ttk.Entry] = {}
        self._updating_scrubber = False
        self._playback_start_wall: Optional[float] = None
        self._playback_start_frame: int = 0
        self._stage_progress_state: Dict[str, Dict[str, Optional[float]]] = {}

        self.rendered_frame_png_bytes: List[bytes] = []
        self._display_ready_photos: List[ImageTk.PhotoImage] = []
        self._display_cache_size: Tuple[int, int] = (0, 0)
        self._decoded_frame_cache: Dict[int, Image.Image] = {}
        self._decoded_cache_order: List[int] = []
        self._decoded_cache_limit = 18
        self._photo_cache: Dict[Tuple[int, int, int], ImageTk.PhotoImage] = {}
        self._photo_cache_order: List[Tuple[int, int, int]] = []
        self._photo_cache_limit = 18
        self._current_photo: Optional[ImageTk.PhotoImage] = None
        self._resize_redraw_after_id = None
        self._screen_width = max(1, int(self.winfo_screenwidth()))
        self._screen_height = max(1, int(self.winfo_screenheight()))
        self._monitor_refresh_hz = self._detect_monitor_refresh_rate()
        self._preview_playback_fps = float(self.engine.config.display_fps)
        self._last_preview_profile_text = ""
        self._apply_display_aware_window_geometry()

        self._build_layout()
        self._bind_default_values()
        self.status_var.set("Adjust settings, then click Generate / Apply.")
        self.reset_stage_progress("sim", "Precomputing traffic states: not started")
        self.reset_stage_progress("render", "Rendering display frames: not started")

    def _detect_monitor_refresh_rate(self) -> float:
        try:
            import ctypes
            VREFRESH = 116
            hdc = ctypes.windll.user32.GetDC(0)
            try:
                refresh_hz = float(ctypes.windll.gdi32.GetDeviceCaps(hdc, VREFRESH))
            finally:
                ctypes.windll.user32.ReleaseDC(0, hdc)
            if refresh_hz > 1.0:
                return refresh_hz
        except Exception:
            pass
        return 60.0

    def _apply_display_aware_window_geometry(self) -> None:
        screen_w = self._screen_width
        screen_h = self._screen_height
        target_w = max(1320, min(1900, int(screen_w * 0.88)))
        target_h = max(820, min(1080, int(screen_h * 0.86)))
        pos_x = max(0, (screen_w - target_w) // 2)
        pos_y = max(0, (screen_h - target_h) // 3)
        self.geometry(f"{target_w}x{target_h}+{pos_x}+{pos_y}")
        self.minsize(min(target_w, 1280), min(target_h, 780))

    def _get_target_prerender_size(self) -> Tuple[int, int]:
        self.update_idletasks()
        viewer_w = int(self.viewer_label.winfo_width()) if hasattr(self, "viewer_label") else 0
        viewer_h = int(self.viewer_label.winfo_height()) if hasattr(self, "viewer_label") else 0

        if viewer_w <= 1 or viewer_h <= 1:
            viewer_w = max(960, int(self._screen_width * 0.62))
            viewer_h = max(420, int(self._screen_height * 0.58))

        max_w = max(1100, min(1680, int(self._screen_width * 0.80)))
        max_h = max(520, min(920, int(self._screen_height * 0.72)))

        target_w = max(960, min(viewer_w, max_w))
        target_h = max(420, min(viewer_h, max_h))
        return target_w, target_h

    def _compute_preview_playback_fps(self, requested_fps: float) -> float:
        viewer_w, viewer_h = self._get_viewer_display_size()
        area = max(1, viewer_w * viewer_h)
        refresh_hz = max(30.0, float(self._monitor_refresh_hz))

        if refresh_hz <= 60.0:
            hz_cap = 24.0
        elif refresh_hz <= 90.0:
            hz_cap = 30.0
        elif refresh_hz <= 120.0:
            hz_cap = 36.0
        elif refresh_hz <= 165.0:
            hz_cap = 48.0
        else:
            hz_cap = 60.0

        if area >= 2_300_000:
            area_cap = 24.0
        elif area >= 1_600_000:
            area_cap = 30.0
        elif area >= 1_100_000:
            area_cap = 36.0
        elif area >= 800_000:
            area_cap = 48.0
        else:
            area_cap = 60.0

        return max(12.0, min(float(requested_fps), hz_cap, area_cap))

    def _refresh_preview_profile(self, requested_fps: float) -> str:
        target_w, target_h = self._get_target_prerender_size()
        self._preview_playback_fps = self._compute_preview_playback_fps(requested_fps)
        self._last_preview_profile_text = (
            f"Display {self._screen_width}x{self._screen_height} @ {self._monitor_refresh_hz:.0f} Hz | "
            f"Preview {target_w}x{target_h} | Playback cap {self._preview_playback_fps:.0f} FPS"
        )
        return self._last_preview_profile_text

    def _build_layout(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        controls = ttk.Frame(self, padding=10)
        controls.grid(row=0, column=0, sticky="nsw")
        controls.rowconfigure(99, weight=1)

        viewer = ttk.Frame(self, padding=(0, 10, 10, 10))
        viewer.grid(row=0, column=1, sticky="nsew")
        viewer.columnconfigure(0, weight=1)
        viewer.rowconfigure(0, weight=1)
        self.viewer_frame = viewer

        ttk.Label(controls, text="Traffic Simulator Controls", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

        groups = [
            ("Layout", [
                ("num_lanes", "Lanes"),
                ("base_road_length", "Base road length"),
                ("zoom", "Zoom"),
                ("horizontal_zoom", "Horizontal zoom"),
            ]),
            ("Traffic", [
                ("spawn_prob", "Spawn probability"),
                ("spawn_clearance", "Spawn clearance"),
                ("min_desired_speed", "Min desired speed"),
                ("max_desired_speed", "Max desired speed"),
            ]),
            ("Behavior", [
                ("safe_gap", "Safe gap"),
                ("lane_change_threshold", "Lane change threshold"),
                ("yield_rear_gap", "Yield rear gap"),
                ("aggressive_weaver_prob", "Weaver probability"),
            ]),
            ("Timing", [
                ("simulation_fps", "Simulation FPS"),
                ("display_fps", "Display FPS"),
                ("simulation_time", "Run time (s)"),
                ("seed", "Random seed (optional)"),
            ]),
        ]

        row = 1
        for group_name, params in groups:
            lf = ttk.LabelFrame(controls, text=group_name, padding=8)
            lf.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            lf.columnconfigure(1, weight=1)
            for r, (attr, label) in enumerate(params):
                ttk.Label(lf, text=label).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
                if attr == "num_lanes":
                    var: tk.Variable = tk.IntVar()
                elif attr == "seed":
                    var = tk.StringVar()
                else:
                    var = tk.DoubleVar()
                ent = ttk.Entry(lf, textvariable=var, width=12)
                ent.grid(row=r, column=1, sticky="ew", pady=2)
                self.param_vars[attr] = var
                self.controls[attr] = ent
            row += 1

        button_bar = ttk.Frame(controls)
        button_bar.grid(row=row, column=0, sticky="ew", pady=(4, 8))
        button_bar.columnconfigure((0, 1), weight=1)
        ttk.Button(button_bar, text="Generate / Apply", command=self.generate_simulation).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(button_bar, text="Reset Defaults", command=self.reset_defaults).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        row += 1

        playback_bar = ttk.Frame(controls)
        playback_bar.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        playback_bar.columnconfigure((0, 1, 2), weight=1)
        self.play_button = ttk.Button(playback_bar, text="Play", command=self.toggle_play)
        self.play_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(playback_bar, text="Step", command=self.step_once).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(playback_bar, text="Restart", command=self.restart_playback).grid(row=0, column=2, sticky="ew", padx=(4, 0))
        row += 1

        export_bar = ttk.Frame(controls)
        export_bar.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        export_bar.columnconfigure(0, weight=1)
        ttk.Button(export_bar, text="Export GIF / MP4 / HTML Player", command=self.export_animation).grid(row=0, column=0, sticky="ew")
        row += 1



        self.viewer_label = tk.Label(viewer, bd=0, highlightthickness=0, bg="black")
        self.viewer_label.grid(row=0, column=0, sticky="nsew")
        self.viewer_label.bind("<Configure>", self.on_viewer_resize)

        self.scrubber = ttk.Scale(viewer, from_=0, to=1, orient="horizontal", command=self.on_scrub)
        self.scrubber.grid(row=1, column=0, sticky="ew", pady=(8, 4))

        status = ttk.Frame(viewer)
        status.grid(row=2, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

        self.sim_stage_var = tk.StringVar(value="Precomputing traffic states: not started")
        ttk.Label(status, textvariable=self.sim_stage_var).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.sim_progress = ttk.Progressbar(status, mode="determinate")
        self.sim_progress.grid(row=2, column=0, sticky="ew", pady=(2, 0))

        self.render_stage_var = tk.StringVar(value="Rendering display frames: not started")
        ttk.Label(status, textvariable=self.render_stage_var).grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.render_progress = ttk.Progressbar(status, mode="determinate")
        self.render_progress.grid(row=4, column=0, sticky="ew", pady=(2, 0))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _bind_default_values(self) -> None:
        defaults = SimulatorConfig()
        for attr, var in self.param_vars.items():
            value = getattr(defaults, attr)
            if attr == "seed":
                var.set("" if value is None else str(value))
            else:
                var.set(value)

    def reset_defaults(self) -> None:
        self.stop_playback()
        self._bind_default_values()
        self.current_frame = 0
        self.status_var.set("Defaults restored. Click Generate / Apply to build the simulation.")
        self.reset_stage_progress("sim", "Precomputing traffic states: not started")
        self.reset_stage_progress("render", "Rendering display frames: not started")

    def collect_config(self) -> SimulatorConfig:
        cfg = SimulatorConfig()
        for attr, var in self.param_vars.items():
            setattr(cfg, attr, var.get())

        cfg.num_lanes = max(2, int(cfg.num_lanes))
        seed_raw = self.param_vars["seed"].get().strip()
        cfg.seed = None if seed_raw == "" else int(seed_raw)
        cfg.simulation_fps = max(1.0, float(cfg.simulation_fps))
        cfg.display_fps = max(1.0, float(cfg.display_fps))
        cfg.simulation_time = max(2.0, float(cfg.simulation_time))
        cfg.spawn_prob = float(np.clip(cfg.spawn_prob, 0.0, 0.95))
        cfg.zoom = max(0.6, float(cfg.zoom))
        cfg.horizontal_zoom = max(0.4, float(cfg.horizontal_zoom))
        cfg.base_road_length = max(20.0, float(cfg.base_road_length))
        cfg.spawn_clearance = max(1.0, float(cfg.spawn_clearance))
        cfg.min_desired_speed = max(0.1, float(cfg.min_desired_speed))
        cfg.max_desired_speed = max(cfg.min_desired_speed + 0.1, float(cfg.max_desired_speed))
        cfg.safe_gap = max(0.5, float(cfg.safe_gap))
        cfg.lane_change_threshold = max(0.1, float(cfg.lane_change_threshold))
        cfg.yield_rear_gap = max(0.5, float(cfg.yield_rear_gap))
        cfg.aggressive_weaver_prob = float(np.clip(cfg.aggressive_weaver_prob, 0.0, 0.25))

        if cfg.num_lanes != 5:
            fallback = {lane: 1.0 for lane in range(cfg.num_lanes)}
            if cfg.num_lanes >= 1:
                fallback[0] = 1.55
            if cfg.num_lanes >= 2:
                fallback[1] = 1.30
            if cfg.num_lanes >= 3:
                fallback[min(2, cfg.num_lanes - 1)] = 0.30
            for lane in range(3, cfg.num_lanes):
                fallback[lane] = 0.08 if lane == 3 else 0.03
            cfg.semi_spawn_lane_multipliers = fallback
        return cfg

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _new_stage_progress_state(self, start_wall: Optional[float] = None) -> Dict[str, Optional[float]]:
        return {
            "start_wall": start_wall,
            "last_wall": start_wall,
            "last_value": 0.0,
            "ema_seconds_per_unit": None,
            "samples": 0.0,
        }

    def _estimate_eta_seconds(self, stage: str, value: int, total: int, now: float) -> Optional[float]:
        stage_state = self._stage_progress_state.setdefault(stage, self._new_stage_progress_state())
        start_wall = stage_state.get("start_wall")
        if start_wall is None:
            return None

        elapsed = max(0.0, now - float(start_wall))
        if value <= 0:
            return None
        if value >= total:
            return 0.0

        units_per_second = value / elapsed if elapsed > 0 else 0.0
        if units_per_second <= 0:
            return None

        remaining_units = max(0, total - value)
        return max(0.0, remaining_units / units_per_second)

    def reset_stage_progress(self, stage: str, message: str, total: int = 1) -> None:
        progress_widget = self.sim_progress if stage == "sim" else self.render_progress
        status_var = self.sim_stage_var if stage == "sim" else self.render_stage_var
        progress_widget["maximum"] = max(1, total)
        progress_widget["value"] = 0
        status_var.set(message)
        self._stage_progress_state[stage] = self._new_stage_progress_state()
        self.update_idletasks()
        self.update()

    def begin_stage_progress(self, stage: str, total: int, message: str) -> None:
        progress_widget = self.sim_progress if stage == "sim" else self.render_progress
        status_var = self.sim_stage_var if stage == "sim" else self.render_stage_var
        start_wall = time.perf_counter()
        progress_widget["maximum"] = max(1, total)
        progress_widget["value"] = 0
        status_var.set(f"{message}: 0/{max(1, total)} | Elapsed 00:00 | ETA --:--")
        self._stage_progress_state[stage] = self._new_stage_progress_state(start_wall=start_wall)
        self.update_idletasks()
        self.update()

    def update_stage_progress(self, stage: str, value: int, total: int, message: str) -> None:
        progress_widget = self.sim_progress if stage == "sim" else self.render_progress
        status_var = self.sim_stage_var if stage == "sim" else self.render_stage_var

        total = max(1, total)
        value = min(max(0, value), total)
        now = time.perf_counter()
        stage_state = self._stage_progress_state.setdefault(stage, self._new_stage_progress_state(start_wall=now))

        if stage_state["start_wall"] is None:
            stage_state["start_wall"] = now
        if stage_state["last_wall"] is None:
            stage_state["last_wall"] = now

        previous_value = int(stage_state.get("last_value") or 0)
        previous_wall = float(stage_state.get("last_wall") or now)
        delta_value = value - previous_value
        delta_time = now - previous_wall

        if delta_value > 0 and delta_time >= 0:
            instant_seconds_per_unit = delta_time / delta_value
            ema_seconds_per_unit = stage_state.get("ema_seconds_per_unit")
            if ema_seconds_per_unit is None:
                stage_state["ema_seconds_per_unit"] = instant_seconds_per_unit
            else:
                alpha = 0.18
                stage_state["ema_seconds_per_unit"] = (
                    alpha * instant_seconds_per_unit
                    + (1.0 - alpha) * float(ema_seconds_per_unit)
                )
            stage_state["samples"] = float(stage_state.get("samples") or 0.0) + float(delta_value)
            stage_state["last_value"] = float(value)
            stage_state["last_wall"] = now

        elapsed = now - float(stage_state["start_wall"])
        eta_seconds = self._estimate_eta_seconds(stage, value, total, now)

        if eta_seconds is None:
            eta_text = "--:--"
        else:
            eta_text = self._format_duration(eta_seconds)

        progress_widget["maximum"] = total
        progress_widget["value"] = value
        status_var.set(
            f"{message}: {value}/{total} | Elapsed {self._format_duration(elapsed)} | ETA {eta_text}"
        )
        self.update_idletasks()
        self.update()

    def complete_stage_progress(self, stage: str, total: int, message: str) -> None:
        progress_widget = self.sim_progress if stage == "sim" else self.render_progress
        status_var = self.sim_stage_var if stage == "sim" else self.render_stage_var
        stage_state = self._stage_progress_state.get(stage, self._new_stage_progress_state())
        start_wall = stage_state.get("start_wall")
        elapsed = 0.0 if start_wall is None else time.perf_counter() - float(start_wall)
        progress_widget["maximum"] = max(1, total)
        progress_widget["value"] = max(1, total)
        status_var.set(
            f"{message}: {max(1, total)}/{max(1, total)} | Elapsed {self._format_duration(elapsed)} | ETA 00:00"
        )
        self.update_idletasks()
        self.update()

    def clear_render_cache(self) -> None:
        self.rendered_frame_png_bytes = []
        self._display_ready_photos = []
        self._display_cache_size = (0, 0)
        self._decoded_frame_cache.clear()
        self._decoded_cache_order.clear()
        self._photo_cache.clear()
        self._photo_cache_order.clear()
        self._current_photo = None
        self.viewer_label.configure(image="", text="")

    def _cache_decoded_frame(self, frame_index: int, image: Image.Image) -> Image.Image:
        self._decoded_frame_cache[frame_index] = image
        self._decoded_cache_order = [idx for idx in self._decoded_cache_order if idx != frame_index]
        self._decoded_cache_order.append(frame_index)

        while len(self._decoded_cache_order) > self._decoded_cache_limit:
            oldest = self._decoded_cache_order.pop(0)
            if oldest in self._decoded_frame_cache and oldest != frame_index:
                del self._decoded_frame_cache[oldest]

        return image

    def _cache_photo(self, cache_key: Tuple[int, int, int], photo: ImageTk.PhotoImage) -> ImageTk.PhotoImage:
        self._photo_cache[cache_key] = photo
        self._photo_cache_order = [key for key in self._photo_cache_order if key != cache_key]
        self._photo_cache_order.append(cache_key)

        while len(self._photo_cache_order) > self._photo_cache_limit:
            oldest = self._photo_cache_order.pop(0)
            if oldest in self._photo_cache and oldest != cache_key:
                del self._photo_cache[oldest]

        return photo

    def _clear_photo_cache(self) -> None:
        self._photo_cache.clear()
        self._photo_cache_order.clear()

    def _get_viewer_display_size(self) -> Tuple[int, int]:
        self.update_idletasks()
        width = max(1, int(self.viewer_label.winfo_width()))
        height = max(1, int(self.viewer_label.winfo_height()))
        if width <= 1 or height <= 1:
            width = max(width, 1100)
            height = max(height, 620)
        return width, height

    def on_viewer_resize(self, _event=None) -> None:
        if self._resize_redraw_after_id is not None:
            self.after_cancel(self._resize_redraw_after_id)
        self._resize_redraw_after_id = self.after(80, self._finish_viewer_resize)

    def _finish_viewer_resize(self) -> None:
        self._resize_redraw_after_id = None
        self._clear_photo_cache()
        self._preview_playback_fps = self._compute_preview_playback_fps(self.engine.config.display_fps)
        if self.engine.precomputed_cache_ready and self.rendered_frame_png_bytes:
            target_size = self._get_viewer_display_size()
            if target_size != self._display_cache_size:
                was_playing = self.playing
                self.stop_playback()
                self.status_var.set("Resizing preview cache for the current viewer size...")
                self.build_display_ready_preview_cache("Preparing display-ready preview frames")
                if was_playing:
                    self.playing = True
                    self.play_button.configure(text="Pause")
                    self._playback_start_wall = time.perf_counter()
                    self._playback_start_frame = self.current_frame
                    self.schedule_next_frame()
            self.draw_current_frame()

    def get_decoded_frame_image(self, frame_index: int) -> Image.Image:
        if frame_index in self._decoded_frame_cache:
            image = self._decoded_frame_cache[frame_index]
            self._decoded_cache_order = [idx for idx in self._decoded_cache_order if idx != frame_index]
            self._decoded_cache_order.append(frame_index)
            return image

        if not self.rendered_frame_png_bytes:
            raise RuntimeError("Rendered frame cache is empty.")

        png_data = self.rendered_frame_png_bytes[frame_index]
        with Image.open(BytesIO(png_data)) as image:
            decoded = image.convert("RGBA").copy()
        return self._cache_decoded_frame(frame_index, decoded)

    def _fit_image_to_size(self, image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        if target_width <= 1 or target_height <= 1:
            return image

        scale = min(target_width / image.width, target_height / image.height)
        scale = max(scale, 1e-6)

        new_width = max(1, int(round(image.width * scale)))
        new_height = max(1, int(round(image.height * scale)))
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
        resized = image.resize((new_width, new_height), resample)

        background = Image.new("RGBA", (target_width, target_height), "black")
        offset_x = (target_width - new_width) // 2
        offset_y = (target_height - new_height) // 2
        background.paste(resized, (offset_x, offset_y))
        return background

    def _fit_image_to_viewer(self, image: Image.Image) -> Image.Image:
        target_width, target_height = self._get_viewer_display_size()
        return self._fit_image_to_size(image, target_width, target_height)

    def build_display_ready_preview_cache(self, progress_message: str = "Preparing display-ready preview frames") -> None:
        if not self.rendered_frame_png_bytes:
            self._display_ready_photos = []
            self._display_cache_size = (0, 0)
            return

        target_width, target_height = self._get_viewer_display_size()
        total = len(self.rendered_frame_png_bytes)
        photos: List[ImageTk.PhotoImage] = []
        self.begin_stage_progress("render", total, progress_message)
        for frame_index in range(total):
            decoded = self.get_decoded_frame_image(frame_index)
            fitted = self._fit_image_to_size(decoded, target_width, target_height)
            photos.append(ImageTk.PhotoImage(fitted))
            self.update_stage_progress("render", frame_index + 1, total, progress_message)

        self._display_ready_photos = photos
        self._display_cache_size = (target_width, target_height)
        self.complete_stage_progress("render", total, progress_message)

    def generate_simulation(self) -> None:
        try:
            self.stop_playback()
            self.clear_render_cache()

            cfg = self.collect_config()
            self.engine.set_config(cfg)
            target_pixel_size = self._get_target_prerender_size()
            preview_profile_text = self._refresh_preview_profile(cfg.display_fps)

            total_sim_work = cfg.sim_steps_per_sim * cfg.num_simulations
            total_render_work = cfg.total_display_frames

            self.status_var.set("Precomputing traffic states...")
            self.begin_stage_progress("sim", total_sim_work, "Precomputing traffic states")
            self.reset_stage_progress("render", "Rendering display frames: waiting for precompute stage")

            def sim_progress(value: int, total: int, message: str) -> None:
                self.update_stage_progress("sim", value, total, message)

            def render_progress(value: int, total: int, message: str) -> None:
                self.update_stage_progress("render", value, total, message)

            self.engine.precompute_simulation_cache(progress_callback=sim_progress)
            self.complete_stage_progress("sim", total_sim_work, "Precomputing traffic states")

            self.status_var.set("Rendering display frames...")
            self.update_idletasks()
            self.update()
            self.begin_stage_progress("render", total_render_work, "Rendering display frames")
            self.rendered_frame_png_bytes = self.engine.prerender_frame_png_bytes(
                progress_callback=render_progress,
                target_pixel_size=target_pixel_size,
            )
            self.complete_stage_progress("render", total_render_work, "Rendering display frames")
            self.build_display_ready_preview_cache("Preparing display-ready preview frames")

            self.current_frame = 0
            self.scrubber.configure(to=max(1, cfg.total_display_frames - 1))
            self._updating_scrubber = True
            try:
                self.scrubber.set(0)
            finally:
                self._updating_scrubber = False

            self.draw_current_frame()
            seed_text = str(self.engine.active_seed)
            if cfg.seed is None:
                seed_text += " (randomized)"
            self.status_var.set(f"Simulation ready | Seed {seed_text} | {preview_profile_text}")
        except Exception as exc:
            messagebox.showerror("Simulation error", str(exc))
            self.status_var.set("Simulation failed")
            self.reset_stage_progress("sim", "Precomputing traffic states: failed")
            self.reset_stage_progress("render", "Rendering display frames: failed")

    def get_frame_photo(self, frame_index: int) -> ImageTk.PhotoImage:
        if self._display_ready_photos and self._display_cache_size == self._get_viewer_display_size():
            return self._display_ready_photos[frame_index]

        target_width, target_height = self._get_viewer_display_size()
        cache_key = (frame_index, target_width, target_height)

        if cache_key in self._photo_cache:
            photo = self._photo_cache[cache_key]
            self._photo_cache_order = [key for key in self._photo_cache_order if key != cache_key]
            self._photo_cache_order.append(cache_key)
            return photo

        decoded = self.get_decoded_frame_image(frame_index)
        fitted = self._fit_image_to_size(decoded, target_width, target_height)
        photo = ImageTk.PhotoImage(fitted)
        return self._cache_photo(cache_key, photo)

    def warm_nearby_frames(self, center_frame: int, look_ahead: int = 3) -> None:
        if not self.rendered_frame_png_bytes:
            return
        start = max(0, center_frame)
        stop = min(len(self.rendered_frame_png_bytes), center_frame + look_ahead + 1)
        for frame_index in range(start, stop):
            try:
                self.get_frame_photo(frame_index)
            except Exception:
                break

    def draw_current_frame(self) -> None:
        if not self.engine.precomputed_cache_ready or not self.rendered_frame_png_bytes:
            return
        max_frame = max(0, self.engine.config.total_display_frames - 1)
        self.current_frame = int(np.clip(self.current_frame, 0, max_frame))

        photo = self.get_frame_photo(self.current_frame)
        self._current_photo = photo
        self.viewer_label.configure(image=photo)

        self._updating_scrubber = True
        try:
            self.scrubber.set(self.current_frame)
        finally:
            self._updating_scrubber = False


    def toggle_play(self) -> None:
        if self.playing:
            self.stop_playback()
        else:
            if not self.engine.precomputed_cache_ready or not self.rendered_frame_png_bytes:
                return
            self.playing = True
            self.play_button.configure(text="Pause")
            self._playback_start_wall = time.perf_counter()
            self._playback_start_frame = self.current_frame
            self.schedule_next_frame()

    def stop_playback(self) -> None:
        self.playing = False
        self.play_button.configure(text="Play")
        self._playback_start_wall = None
        if self.after_id is not None:
            self.after_cancel(self.after_id)
            self.after_id = None

    def schedule_next_frame(self) -> None:
        if not self.playing or not self.engine.precomputed_cache_ready or not self.rendered_frame_png_bytes:
            return

        cfg = self.engine.config
        if self._playback_start_wall is None:
            self._playback_start_wall = time.perf_counter()
            self._playback_start_frame = self.current_frame

        playback_fps = max(1.0, float(self._preview_playback_fps))
        elapsed = time.perf_counter() - self._playback_start_wall
        target_frame = self._playback_start_frame + int(elapsed * playback_fps)
        max_frame = cfg.total_display_frames - 1
        self.current_frame = min(target_frame, max_frame)
        self.draw_current_frame()

        if self.current_frame >= max_frame:
            self.stop_playback()
            return

        next_target_time = (self.current_frame + 1 - self._playback_start_frame) / playback_fps
        delay_sec = max(0.001, next_target_time - (time.perf_counter() - self._playback_start_wall))
        self.after_id = self.after(max(1, int(round(delay_sec * 1000.0))), self.schedule_next_frame)

    def step_once(self) -> None:
        self.stop_playback()
        if not self.engine.precomputed_cache_ready or not self.rendered_frame_png_bytes:
            return
        self.current_frame = min(self.current_frame + 1, self.engine.config.total_display_frames - 1)
        self.draw_current_frame()

    def restart_playback(self) -> None:
        self.stop_playback()
        self.current_frame = 0
        self.draw_current_frame()

    def on_scrub(self, value: str) -> None:
        if not self.engine.precomputed_cache_ready or self._updating_scrubber or not self.rendered_frame_png_bytes:
            return
        self.stop_playback()
        self.current_frame = int(float(value))
        self.draw_current_frame()

    
    def _decode_rendered_frames_to_pil(self, progress_message: str) -> list[Image.Image]:
        if not self.rendered_frame_png_bytes:
            raise RuntimeError("No rendered frames are available. Generate the simulation first.")
        total = len(self.rendered_frame_png_bytes)
        frames: list[Image.Image] = []
        self.reset_stage_progress("sim", "Precomputing traffic states: not used for export")
        self.begin_stage_progress("render", total, progress_message)
        for frame_index, png_bytes in enumerate(self.rendered_frame_png_bytes, start=1):
            with Image.open(BytesIO(png_bytes)) as image:
                frames.append(image.convert("RGBA").copy())
            self.update_stage_progress("render", frame_index, total, progress_message)
        self.complete_stage_progress("render", total, progress_message)
        return frames

    def _write_playable_html(self, output_path: Path) -> None:
        if not self.rendered_frame_png_bytes:
            raise RuntimeError("No rendered frames are available. Generate the simulation first.")

        import base64
        total = len(self.rendered_frame_png_bytes)
        fps = max(1.0, float(self.engine.config.display_fps))
        self.reset_stage_progress("sim", "Precomputing traffic states: not used for export")
        self.begin_stage_progress("render", total, "Building HTML player")

        encoded_frames: list[str] = []
        for frame_index, png_bytes in enumerate(self.rendered_frame_png_bytes, start=1):
            encoded_frames.append(base64.b64encode(png_bytes).decode("ascii"))
            self.update_stage_progress("render", frame_index, total, "Building HTML player")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Traffic Simulator HTML Player</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: Segoe UI, Arial, sans-serif; background: #111; color: #eee; margin: 0; }}
  .wrap {{ max-width: 1280px; margin: 0 auto; padding: 18px; }}
  h2 {{ margin: 0 0 8px 0; }}
  .meta {{ color: #bbb; margin-bottom: 12px; }}
  .player {{ background: #000; padding: 12px; border-radius: 10px; box-shadow: 0 0 0 1px #333 inset; }}
  img {{ width: 100%; height: auto; display: block; background: #000; }}
  .controls {{ display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }}
  button {{ font: inherit; padding: 8px 14px; border-radius: 8px; border: 1px solid #555; background: #222; color: #eee; cursor: pointer; }}
  button:hover {{ background: #2d2d2d; }}
  input[type=range] {{ flex: 1 1 350px; }}
  .status {{ min-width: 210px; color: #ccc; }}
</style>
</head>
<body>
<div class="wrap">
  <h2>Traffic Simulator HTML Player</h2>
  <div class="meta">Lanes: {self.engine.config.num_lanes} | Simulation time: {self.engine.config.simulation_time:.1f}s | Display FPS: {self.engine.config.display_fps:.0f}</div>
  <div class="player">
    <img id="frame" alt="Traffic simulator animation frame">
    <div class="controls">
      <button id="playBtn" type="button">Play</button>
      <input id="scrubber" type="range" min="0" max="{max(0, total - 1)}" value="0" step="1">
      <div id="status" class="status">Frame 1/{total}</div>
    </div>
  </div>
</div>
<script>
const frames = [{",".join("'" + s + "'" for s in encoded_frames)}];
const fps = {fps:.8f};
const frameEl = document.getElementById("frame");
const scrubber = document.getElementById("scrubber");
const playBtn = document.getElementById("playBtn");
const statusEl = document.getElementById("status");
let current = 0;
let playing = false;
let timer = null;

function showFrame(index) {{
  current = Math.max(0, Math.min(index, frames.length - 1));
  frameEl.src = "data:image/png;base64," + frames[current];
  scrubber.value = current;
  statusEl.textContent = `Frame ${'{'}current + 1{'}'}/${'{'}frames.length{'}'}`;
}}

function stopPlayback() {{
  playing = false;
  playBtn.textContent = "Play";
  if (timer !== null) {{
    clearInterval(timer);
    timer = null;
  }}
}}

function startPlayback() {{
  if (playing) return;
  playing = true;
  playBtn.textContent = "Pause";
  timer = setInterval(() => {{
    if (current >= frames.length - 1) {{
      stopPlayback();
      return;
    }}
    showFrame(current + 1);
  }}, Math.max(1, Math.round(1000 / fps)));
}}

playBtn.addEventListener("click", () => {{
  if (playing) {{
    stopPlayback();
  }} else {{
    startPlayback();
  }}
}});

scrubber.addEventListener("input", () => {{
  stopPlayback();
  showFrame(parseInt(scrubber.value, 10) || 0);
}});

showFrame(0);
</script>
</body>
</html>
"""
        output_path.write_text(html, encoding="utf-8")
        self.complete_stage_progress("render", total, "Building HTML player")

    def export_animation(self) -> None:
        try:
            if not self.rendered_frame_png_bytes:
                messagebox.showinfo("Generate first", "Generate / Apply the simulation before exporting a file.")
                return

            path_str = filedialog.asksaveasfilename(
                title="Export GIF, MP4, or HTML player",
                defaultextension=".gif",
                filetypes=[
                    ("Animated GIF", "*.gif"),
                    ("MP4 Video", "*.mp4"),
                    ("HTML Player", "*.html"),
                ],
                initialfile="traffic_simulation.gif",
            )
            if not path_str:
                return

            output_path = Path(path_str)
            suffix = output_path.suffix.lower()

            if suffix == ".gif":
                frames = self._decode_rendered_frames_to_pil("Preparing GIF frames")
                duration_ms = max(1, int(round(1000.0 / max(1.0, float(self.engine.config.display_fps)))))
                frames[0].save(
                    output_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=duration_ms,
                    loop=0,
                    disposal=2,
                    optimize=False,
                )
                for frame in frames:
                    frame.close()
                export_label = "GIF"
            elif suffix == ".mp4":
                import imageio.v2 as imageio
                total = len(self.rendered_frame_png_bytes)
                frames = self._decode_rendered_frames_to_pil("Preparing MP4 frames")
                writer = imageio.get_writer(
                    str(output_path),
                    fps=max(1.0, float(self.engine.config.display_fps)),
                    codec="libx264",
                    quality=8,
                    macro_block_size=None,
                )
                try:
                    self.begin_stage_progress("render", total, "Encoding MP4 video")
                    for frame_index, frame in enumerate(frames, start=1):
                        writer.append_data(np.asarray(frame.convert("RGB")))
                        self.update_stage_progress("render", frame_index, total, "Encoding MP4 video")
                    self.complete_stage_progress("render", total, "Encoding MP4 video")
                finally:
                    writer.close()
                    for frame in frames:
                        frame.close()
                export_label = "MP4"
            elif suffix == ".html":
                self._write_playable_html(output_path)
                export_label = "HTML player"
            else:
                raise RuntimeError("Choose .gif, .mp4, or .html for export.")

            self.status_var.set(f"Exported {export_label} to {output_path}")
            messagebox.showinfo("Export complete", f"Saved {export_label} to:\n{output_path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))
            self.status_var.set("Export failed")
    def _on_close(self) -> None:
        self.stop_playback()
        self.destroy()

def main() -> None:
    app = TrafficSimulatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
