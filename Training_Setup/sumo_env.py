import os
import time
import pickle
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Tuple, Dict
import warnings
from config import *

try:
    import traci
    from traci import TraCIException
except ImportError:
    traci = None
    TraCIException = Exception

SUMO_BINARY = os.environ.get("SUMO_BINARY", "sumo-gui")
SUMO_CMD = [SUMO_BINARY, "-c", "4.sumocfg", "--no-step-log", "true", "--start"]

SAVE_STATE_FILE = "sumo_env_state.pkl"

class SumoTrafficEnv(gym.Env):
    """RL Environment for traffic signal control with consistent cycle timing."""

    metadata = {"render_modes": ["human"]}

    def __init__(self,
                 lateral_resolution: float = 0.2,
                 yellow: float = YELLOW_TIME,
                 zero_vehicle_restart_seconds: float = 600.0,
                 retry_start_attempts: int = 3,
                 total_training_cycles: int = 5000,
                 last_n_for_reward: int = 5):
        super().__init__()

        if traci is None:
            raise ImportError("TraCI (SUMO) bindings not found.")

        # Use shared configuration
        self.lateral_resolution: float = lateral_resolution
        self.yellow: float = yellow
        self.green_red_pool: float = CYCLE_TOTAL - 2 * yellow
        self.cycle: float = CYCLE_TOTAL  # Use shared constant
        self.zero_vehicle_restart_seconds: float = zero_vehicle_restart_seconds
        self.retry_start_attempts: int = retry_start_attempts
        self.total_training_cycles = total_training_cycles
        self.current_cycle_count = 0
        self.last_n_for_reward = last_n_for_reward

        # Use shared junction mapping
        self.systems: Dict[str, Dict] = {
            "A": {"tls_ids": ["J6", "J26"], "edges": {"J6": ("E1", "E6"), "J26": ("E15", "E16")}},
            "B": {"tls_ids": ["J16", "J41"], "edges": {"J16": ("E8", "E13"), "J41": ("E22", "E23")}}
        }

        # Observation space: 20 values (4 junctions × (density_before, density_after, halting_before, halting_after) + 4 green allocations)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(20,), dtype=np.float32)
        
        # Action space: 4 continuous values [0,1] for green time allocation
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)

        self._connected = False
        self._sim_time = 0.0
        self.cumulative_time = 0.0
        self._last_vehicle_time = 0.0
        self._resolved_edges: Dict[str, str] = {}
        self._cycle_start_time = 0.0
        self._steps_per_cycle = int(self.cycle / self.lateral_resolution)
        self._cycle_started = False

        # Initialize green allocations (0.5 = 30 seconds, within [25,35])
        self.green_alloc = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)

    def _resolve_edge(self, base_name: str) -> str:
        """Resolve edge name with fallback"""
        if base_name in self._resolved_edges:
            return self._resolved_edges[base_name]
        try:
            all_edges = traci.edge.getIDList()
            chosen = (
                base_name if base_name in all_edges else
                f"{base_name}_0" if f"{base_name}_0" in all_edges else
                base_name
            )
        except Exception:
            chosen = base_name
        self._resolved_edges[base_name] = chosen
        return chosen

    def _force_close_existing_traci(self):
        """Force close existing TraCI connection"""
        try:
            traci.close()
        except Exception:
            pass

    def _start_sumo(self):
        """Start SUMO simulation"""
        if self._connected:
            return
        last_exception = RuntimeError("Failed to start SUMO after all attempts")
        for attempt in range(self.retry_start_attempts):
            try:
                self._force_close_existing_traci()
                traci.start(SUMO_CMD)
                traci.simulationStep()
                self._connected = True
                self._sim_time = traci.simulation.getTime()
                self._last_vehicle_time = self._sim_time
                self._cycle_start_time = self._sim_time
                return
            except TraCIException as e:
                last_exception = e
                try:
                    traci.close()
                except Exception:
                    pass
                time.sleep(0.5 + 0.5 * attempt)
        raise last_exception

    def _close_sumo(self):
        """Close SUMO simulation"""
        if self._connected:
            try:
                traci.close()
            except Exception:
                pass
        self._connected = False

    def _safe_step(self, steps: int = 1) -> bool:
        """Step simulation safely with error handling"""
        successful_steps = 0
        for _ in range(steps):
            try:
                traci.simulationStep()
                successful_steps += 1
                self._sim_time = traci.simulation.getTime()
            except TraCIException:
                self._connected = False
                try:
                    self._restart_sumo()
                    continue
                except Exception:
                    break
        if successful_steps > 0:
            self.cumulative_time += float(successful_steps)
            total_vehicles = 0
            for key in ["A", "B"]:
                for tls_id, (in_base, out_base) in self.systems[key]["edges"].items():
                    in_edge = self._resolve_edge(in_base)
                    out_edge = self._resolve_edge(out_base)
                    try:
                        total_vehicles += traci.edge.getLastStepVehicleNumber(in_edge)
                    except Exception:
                        pass
                    try:
                        total_vehicles += traci.edge.getLastStepVehicleNumber(out_edge)
                    except Exception:
                        pass
            if total_vehicles > 0:
                self._last_vehicle_time = self._sim_time
            elif (self._sim_time - self._last_vehicle_time) >= self.zero_vehicle_restart_seconds:
                self._restart_sumo()
        return successful_steps > 0

    def _restart_sumo(self):
        """Restart SUMO simulation"""
        try:
            self._close_sumo()
        except Exception:
            pass
        time.sleep(1.0)
        self._start_sumo()
        self._resolved_edges = {}
        self.green_alloc = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
        self._apply_green_times()
        self._ensure_equal_priority()

    def _ensure_equal_priority(self):
        """Ensure all traffic lights use program 0"""
        for key in ["A", "B"]:
            for tls_id in self.systems[key]["tls_ids"]:
                try:
                    traci.trafficlight.setProgram(tls_id, "0")
                except Exception:
                    pass

    def _compute_density(self, edge_id: str) -> float:
        """Compute vehicle density on edge"""
        try:
            return float(traci.edge.getLastStepVehicleNumber(edge_id))
        except Exception:
            return 0.0

    def _compute_halting(self, edge_id: str) -> float:
        """Compute number of halting vehicles on edge"""
        try:
            return float(traci.edge.getLastStepHaltingNumber(edge_id))
        except Exception:
            return 0.0

    def _compute_reward(self) -> float:
        """Compute reward based on traffic performance"""
        reward = 0.0

        # System A (J6, J26)
        E1 = self._resolve_edge("E1")
        E15 = self._resolve_edge("E15")
        E6 = self._resolve_edge("E6")
        E16 = self._resolve_edge("E16")

        def total_waiting_time_last_n(edge_id, n):
            try:
                veh_ids = traci.edge.getLastStepVehicleIDs(edge_id)
                recent_veh_ids = veh_ids[-n:] if len(veh_ids) >= n else veh_ids
                return sum(traci.vehicle.getWaitingTime(veh_id) for veh_id in recent_veh_ids)
            except Exception:
                return 0.0

        # Penalize waiting time
        wait_A = total_waiting_time_last_n(E1, self.last_n_for_reward) + \
                 total_waiting_time_last_n(E15, self.last_n_for_reward)
        reward -= wait_A * 0.05

        # Check for congestion after light
        out_J6 = traci.edge.getLastStepVehicleNumber(E6)
        out_J26 = traci.edge.getLastStepVehicleNumber(E16)
        
        if out_J6 > 15 and out_J26 > 15:
            reward -= 5.0  # Penalize congestion

        # System B (J16, J41)
        E8 = self._resolve_edge("E8")
        E22 = self._resolve_edge("E22")
        E13 = self._resolve_edge("E13")
        E23 = self._resolve_edge("E23")

        wait_B = total_waiting_time_last_n(E8, self.last_n_for_reward) + \
                 total_waiting_time_last_n(E22, self.last_n_for_reward)
        reward -= wait_B * 0.05

        out_J16 = traci.edge.getLastStepVehicleNumber(E13)
        out_J41 = traci.edge.getLastStepVehicleNumber(E23)
       
        if out_J16 > 15 and out_J41 > 15:
            reward -= 5.0  # Penalize congestion

        # Reward throughput
        total_out = out_J6 + out_J26 + out_J16 + out_J41
        reward += total_out * 0.5

        # Penalize imbalance between systems
        system_A_out = out_J6 + out_J26
        system_B_out = out_J16 + out_J41
        imbalance = abs(system_A_out - system_B_out)
        reward -= 0.1 * imbalance

        # Penalize very low throughput
        if system_A_out < 5:
            reward -= 5.0
        if system_B_out < 5:
            reward -= 5.0

        return float(np.clip(reward, -100.0, 50.0))

    def _apply_green_times(self):
        """Apply green times to traffic lights with consistent cycle"""
        for idx, (sys_key, tls_id) in enumerate([
            ("A", "J6"), ("A", "J26"),
            ("B", "J16"), ("B", "J41")
        ]):
            # Convert action [0,1] to green time [25,35] seconds
            raw_green = GREEN_MIN + self.green_alloc[idx] * (GREEN_MAX - GREEN_MIN)
            green_time = np.clip(raw_green, GREEN_MIN, GREEN_MAX)
            
            # Calculate red time to maintain cycle
            red_time = CYCLE_TOTAL - green_time - 2 * self.yellow
            red_time = max(red_time, MIN_RED_TIME)
            
            # Recalculate green if red was clipped
            if red_time == MIN_RED_TIME:
                green_time = CYCLE_TOTAL - red_time - 2 * self.yellow
                green_time = np.clip(green_time, GREEN_MIN, GREEN_MAX)
            
            # Quantize to simulation resolution
            green_time = np.round(green_time / self.lateral_resolution) * self.lateral_resolution
            red_time = np.round(red_time / self.lateral_resolution) * self.lateral_resolution
            
            durations = [green_time, self.yellow, red_time, self.yellow]

            try:
                # Try to update complete logic
                logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)
                new_phases = []
                for i, phase in enumerate(logic.phases):
                    if i < 4:
                        new_phases.append(traci.trafficlight.Phase(
                            int(round(durations[i] / self.lateral_resolution)), 
                            phase.state
                        ))
                    else:
                        new_phases.append(phase)
                new_logic = traci.trafficlight.Logic("0", 0, 0, new_phases)
                traci.trafficlight.setCompleteRedYellowGreenDefinition(tls_id, new_logic)
                traci.trafficlight.setProgram(tls_id, "0")
            except Exception as e1:
                # Fallback: set phase durations directly
                try:
                    for p_idx in range(min(4, traci.trafficlight.getPhaseCount(tls_id))):
                        traci.trafficlight.setPhaseDuration(tls_id, p_idx, float(durations[p_idx]))
                    traci.trafficlight.setProgram(tls_id, "0")
                except Exception as e2:
                    warnings.warn(f"Failed to update {tls_id}: {e2}. Using defaults.")
                    try:
                        # Set default timing
                        default_green = 30.0
                        default_red = CYCLE_TOTAL - default_green - 2 * self.yellow
                        traci.trafficlight.setPhaseDuration(tls_id, 0, default_green)
                        traci.trafficlight.setPhaseDuration(tls_id, 1, self.yellow)
                        traci.trafficlight.setPhaseDuration(tls_id, 2, default_red)
                        traci.trafficlight.setPhaseDuration(tls_id, 3, self.yellow)
                        traci.trafficlight.setProgram(tls_id, "0")
                    except Exception:
                        pass

    def reset(self, *, seed=None, options=None) -> Tuple[np.ndarray, Dict]:
        """Reset environment"""
        if seed is not None:
            np.random.seed(seed)

        # Load saved state if exists
        if os.path.exists(SAVE_STATE_FILE):
            try:
                with open(SAVE_STATE_FILE, "rb") as f:
                    state = pickle.load(f)
                self.cumulative_time = state.get("cumulative_time", 0.0)
                self.current_cycle_count = state.get("cycle_count", 0)
                saved_alloc = state.get("green_alloc", [0.5, 0.5, 0.5, 0.5])
                self.green_alloc = np.array(saved_alloc, dtype=np.float32)
                print(f"Loaded state: {self.current_cycle_count} cycles")
            except Exception as e:
                print(f"Failed to load state: {e}")
                self.cumulative_time = 0.0
                self.current_cycle_count = 0
                self.green_alloc = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
        else:
            self.cumulative_time = 0.0
            self.current_cycle_count = 0
            self.green_alloc = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)

        # Start simulation
        self._start_sumo()
        self._resolved_edges = {}
        
        # Resolve all edges
        for key in ["A", "B"]:
            for tls_id, (in_base, out_base) in self.systems[key]["edges"].items():
                self._resolve_edge(in_base)
                self._resolve_edge(out_base)
        
        self._apply_green_times()
        self._cycle_started = True
        self._cycle_start_time = self._sim_time
        self._ensure_equal_priority()
        self._safe_step(2)
        
        return self._get_observation(), {}

    def _get_observation(self) -> np.ndarray:
        """Get observation vector"""
        obs = []
        
        # Collect data for each junction
        for key in ["A", "B"]:
            for tls_id, (in_base, out_base) in self.systems[key]["edges"].items():
                in_edge = self._resolve_edge(in_base)
                out_edge = self._resolve_edge(out_base)
                
                # 1. Input density (normalized)
                density_in = self._compute_density(in_edge)
                obs.append(np.clip(density_in / MAX_DENSITY, 0.0, 1.0))
                
                # 2. Output density (normalized)
                density_out = self._compute_density(out_edge)
                obs.append(np.clip(density_out / MAX_DENSITY, 0.0, 1.0))
                
                # 3. Halting vehicles before light (normalized)
                halting_in = self._compute_halting(in_edge)
                obs.append(np.clip(halting_in / MAX_HALTING, 0.0, 1.0))
                
                # 4. Halting vehicles after light (normalized)
                halting_out = self._compute_halting(out_edge)
                obs.append(np.clip(halting_out / MAX_HALTING, 0.0, 1.0))
        
        # Add current green allocations
        for i in range(4):
            obs.append(np.clip(self.green_alloc[i], 0.0, 1.0))
        
        # Verify observation length
        assert len(obs) == 20, f"Observation length is {len(obs)}, expected 20"
        return np.array(obs, dtype=np.float32)

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """Execute one timestep"""
        # Update green allocations from action
        self.green_alloc = np.clip(action, 0.0, 1.0)
        self._apply_green_times()

        # Simulate one cycle
        for _ in range(self._steps_per_cycle):
            if not self._safe_step(1):
                break

        # Compute reward
        reward = self._compute_reward()
        self.current_cycle_count += 1

        # Print progress
        if self.current_cycle_count % 10 == 0 or self.current_cycle_count <= 5:
            sign = "+" if reward >= 0 else ""
            print(f"🔄 Cycle {self.current_cycle_count:4d} | Reward: {sign}{reward:5.2f}")

        # Get next observation
        obs = self._get_observation()
        
        # Check termination conditions
        terminated = self.current_cycle_count >= self.total_training_cycles
        truncated = False

        # Save state
        try:
            state = {
                "cumulative_time": self.cumulative_time,
                "cycle_count": self.current_cycle_count,
                "green_alloc": self.green_alloc.tolist()
            }
            with open(SAVE_STATE_FILE, "wb") as f:
                pickle.dump(state, f)
        except Exception as e:
            print(f"Failed to save state: {e}")

        return obs, reward, terminated, truncated, {}

    def close(self):
        """Close environment"""
        self._close_sumo()