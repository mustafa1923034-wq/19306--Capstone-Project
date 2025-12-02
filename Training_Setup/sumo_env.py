import os
import time
import pickle
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Tuple, Dict

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
    """Two independent traffic systems with independent TLS control for each traffic light."""

    metadata = {"render.modes": ["human"]}

    def __init__(self,
                 lateral_resolution: float = 0.2,
                 yellow: float = 5.0,
                 zero_vehicle_restart_seconds: float = 600.0,
                 retry_start_attempts: int = 3,
                 total_training_cycles: int = 5000):
        super().__init__()

        if traci is None:
            raise ImportError("TraCI (SUMO) bindings not found.")

        self.lateral_resolution: float = lateral_resolution
        self.yellow: float = yellow
        self.green_red_pool: float = 45.0
        self.cycle: float = 2 * self.yellow + self.green_red_pool  # 55 ثانية
        self.zero_vehicle_restart_seconds: float = zero_vehicle_restart_seconds
        self.retry_start_attempts: int = retry_start_attempts
        self.total_training_cycles = total_training_cycles
        self.current_cycle_count = 0

        self.systems: Dict[str, Dict] = {
            "A": {"tls_ids": ["J6", "J26"], "edges": {"J6": ("E1", "E6"), "J26": ("E15", "E16")}},
            "B": {"tls_ids": ["J16", "J41"], "edges": {"J16": ("E8", "E13"), "J41": ("E22", "E23")}}
        }

        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.observation_space = spaces.Box(low=0.0, high=1e6, shape=(20,), dtype=np.float32)

        self.current_green_alloc = np.array([30.0, 30.0, 30.0, 30.0], dtype=np.float32)
        self._next_green_alloc = np.array([30.0, 30.0, 30.0, 30.0], dtype=np.float32)

        self._connected = False
        self._sim_time = 0.0
        self.cumulative_time = 0.0
        self._last_vehicle_time = 0.0
        self._resolved_edges: Dict[str, str] = {}

        self._cycle_start_time = 0.0
        self._steps_per_cycle = int(self.cycle / self.lateral_resolution)

    # --------------------------------------------
    # Helper: Resolve Edge Name
    # --------------------------------------------
    def _resolve_edge(self, base_name: str) -> str:
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

    # --------------------------------------------
    # SUMO Control Helpers
    # --------------------------------------------
    def _force_close_existing_traci(self):
        try:
            traci.close()
        except Exception:
            pass

    def _start_sumo(self):
        if self._connected:
            return
        last_exception = None
        for attempt in range(self.retry_start_attempts):
            try:
                self._force_close_existing_traci()
                traci.start(SUMO_CMD)
                traci.simulationStep()
                self._connected = True
                self._sim_time = traci.simulation.getTime()
                self._last_vehicle_time = self._sim_time
                self._cycle_start_time = self._sim_time
                print(f"✅ SUMO started successfully (attempt {attempt + 1})")
                return
            except TraCIException as e:
                last_exception = e
                try:
                    traci.close()
                except Exception:
                    pass
                time.sleep(0.5 + 0.5 * attempt)
        raise last_exception if last_exception else RuntimeError("Failed to start SUMO")

    def _close_sumo(self):
        if self._connected:
            try:
                traci.close()
            except Exception:
                pass
        self._connected = False

    def _safe_step(self, steps: int = 1) -> bool:
        successful_steps = 0
        for _ in range(steps):
            try:
                traci.simulationStep()
                successful_steps += 1
                self._sim_time = traci.simulation.getTime()
            except TraCIException:
                self._connected = False
                try:
                    print("🔄 SUMO connection lost, attempting auto-restart...")
                    self._restart_sumo()
                    continue
                except Exception as e:
                    print(f"❌ Auto-restart failed: {e}")
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
                print("🔄 No vehicles detected for too long, restarting SUMO...")
                self._restart_sumo()
        return successful_steps > 0

    def _restart_sumo(self):
        print(f"🔄 Restarting SUMO at sim_time={self._sim_time:.1f}s")
        try:
            self._close_sumo()
        except Exception:
            pass
        time.sleep(1.0)
        self._start_sumo()
        self._resolved_edges = {}
        self._next_green_alloc = np.array([30.0, 30.0, 30.0, 30.0], dtype=np.float32)
        self._apply_next_green()
        self._ensure_equal_priority()
        print("✅ SUMO restart completed successfully")

    # --------------------------------------------
    # Priority Management
    # --------------------------------------------
    def _ensure_equal_priority(self):
        print("[sumo_env] Ensuring equal priority for all traffic lights...")
        for key in ["A", "B"]:
            for tls_id in self.systems[key]["tls_ids"]:
                try:
                    traci.trafficlight.setProgram(tls_id, "0")
                    current_program = traci.trafficlight.getProgram(tls_id)
                    print(f"  - {tls_id}: Program '{current_program}'")
                except Exception as e:
                    print(f"  - {tls_id}: Error setting program - {e}")

    # --------------------------------------------
    # Density / Reward (تم تعديل _compute_density فقط)
    # --------------------------------------------
    def _compute_density(self, edge_id: str) -> float:
        try:
            # استخدام عدد العربيات مباشرة ككثافة
            num = traci.edge.getLastStepVehicleNumber(edge_id)
            density = float(num)
            return density
        except Exception as e:
            print(f"[ERROR] _compute_density failed for {edge_id}: {e}")
            return 0.0

    def _compute_reward(self) -> float:
        reward = 0.0
        total_vehicles = 0
        print("\n📊 REWARD CALCULATION DETAILS:")
        for key in ["A", "B"]:
            densities = {}
            for tls_id, (in_base, out_base) in self.systems[key]["edges"].items():
                in_edge = self._resolve_edge(in_base)
                out_edge = self._resolve_edge(out_base)
                in_density = self._compute_density(in_edge)
                out_density = self._compute_density(out_edge)
                in_vehicles = traci.edge.getLastStepVehicleNumber(in_edge)
                out_vehicles = traci.edge.getLastStepVehicleNumber(out_edge)
                total_vehicles += in_vehicles + out_vehicles
                densities[tls_id] = {
                    'in': in_density,
                    'out': out_density,
                    'total': in_density + out_density,
                    'in_vehicles': in_vehicles,
                    'out_vehicles': out_vehicles
                }
                print(
                    f"  🚦 {tls_id}: {in_edge}[{in_vehicles} vehicles, density={in_density:.4f}], "
                    f"{out_edge}[{out_vehicles} vehicles, density={out_density:.4f}]"
                )
                reward -= in_density * 2.0
                reward -= out_density * 1.5
            if len(densities) == 2:
                tls_ids = list(densities.keys())
                imbalance = abs(densities[tls_ids[0]]['total'] - densities[tls_ids[1]]['total'])
                reward -= imbalance * 0.8
                print(f"  ⚖️  System {key} imbalance: {imbalance:.4f}")
        print(f"  🚗 Total vehicles in system: {total_vehicles}")
        print(f"  💰 Final reward: {reward:.4f}")
        return reward

    # --------------------------------------------
    # Apply Action
    # --------------------------------------------
    def _apply_action(self, action: np.ndarray):
        self._next_green_alloc = np.clip(action, 0.0, 1.0)
        if not hasattr(self, "_cycle_started"):
            self._apply_next_green()

    def _print_final_cycle_summary(self):
        print("\n" + "="*50)
        print("🎯 FINAL CYCLE SUMMARY - Next Cycle Settings")
        print("="*50)
        for key in ["A", "B"]:
            print(f"\n📊 System {key}:")
            for tls_id in self.systems[key]["tls_ids"]:
                green_time = None
                for sys_idx, k in enumerate(["A", "B"]):
                    for tls_idx, tid in enumerate(self.systems[k]["tls_ids"]):
                        if tid == tls_id:
                            action_idx = sys_idx * 2 + tls_idx
                            green_time = 25.0 + self._next_green_alloc[action_idx] * 10.0
                            break
                if green_time is not None:
                    red_time = 45.0 - green_time
                    print(f"  🚦 {tls_id}: Green={green_time:.1f}s, Red={red_time:.1f}s, Yellow=5.0s")
        print(f"⏱️  Total Cycle: {self.cycle:.1f}s (Fixed)")
        print("="*50)

    def _apply_next_green(self):
        yellow_time = 5.0
        min_green_time = 25.0
        max_green_time = 35.0
        green_times = {}
        action_idx = 0
        for sys_idx, key in enumerate(["A", "B"]):
            for tls_idx, tls_id in enumerate(self.systems[key]["tls_ids"]):
                green_time = min_green_time + self._next_green_alloc[action_idx] * (max_green_time - min_green_time)
                green_times[tls_id] = green_time
                self.current_green_alloc[action_idx] = green_time
                action_idx += 1
        for key in ["A", "B"]:
            for tls_id in self.systems[key]["tls_ids"]:
                green_time = green_times[tls_id]
                red_time = 45.0 - green_time
                durations = [green_time, yellow_time, red_time, yellow_time]
                try:
                    Phase = traci.trafficlight.Phase
                    Logic = traci.trafficlight.Logic
                    logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)
                    new_phases = []
                    for i, phase in enumerate(logic.phases):
                        if i < 4:
                            new_phases.append(Phase(int(round(durations[i])), phase.state))
                        else:
                            new_phases.append(phase)
                    new_logic = Logic("0", 0, 0, new_phases)
                    traci.trafficlight.setCompleteRedYellowGreenDefinition(tls_id, new_logic)
                    traci.trafficlight.setProgram(tls_id, "0")
                except Exception:
                    try:
                        nph = traci.trafficlight.getPhaseCount(tls_id)
                        for p_idx in range(min(4, nph)):
                            try:
                                traci.trafficlight.setPhaseDuration(tls_id, p_idx, float(durations[p_idx]))
                            except Exception:
                                pass
                        traci.trafficlight.setProgram(tls_id, "0")
                    except Exception:
                        pass

    # --------------------------------------------
    # Gym API
    # --------------------------------------------
    def reset(self, *, seed=None, options=None) -> Tuple[np.ndarray, Dict]:
        if seed is not None:
            np.random.seed(seed)
        if os.path.exists(SAVE_STATE_FILE):
            try:
                self.cumulative_time = float(pickle.load(open(SAVE_STATE_FILE, "rb")))
                self.current_cycle_count = int(self.cumulative_time / self.cycle)
                print(f"✅ Loaded previous state: {self.cumulative_time:.1f}s ({self.current_cycle_count} cycles)")
            except Exception:
                self.cumulative_time = 0.0
                self.current_cycle_count = 0
                print("🆕 Starting new training session")
        else:
            self.cumulative_time = 0.0
            self.current_cycle_count = 0
            print("🆕 Starting new training session")
        self._start_sumo()
        self._resolved_edges = {}
        for key in ["A", "B"]:
            for tls_id, (in_base, out_base) in self.systems[key]["edges"].items():
                self._resolve_edge(in_base)
                self._resolve_edge(out_base)
        self._next_green_alloc = np.array([30.0, 30.0, 30.0, 30.0], dtype=np.float32)
        self._apply_next_green()
        self._cycle_started = True
        self._cycle_start_time = self._sim_time
        self._ensure_equal_priority()
        self._safe_step(2)
        return self._get_observation(), {}

    def _get_observation(self) -> np.ndarray:
        obs = []
        for key in ["A", "B"]:
            for tls_id, (in_base, out_base) in self.systems[key]["edges"].items():
                in_edge = self._resolve_edge(in_base)
                out_edge = self._resolve_edge(out_base)
                obs.extend([
                    self._compute_density(in_edge),
                    self._compute_density(out_edge),
                    float(traci.edge.getLastStepHaltingNumber(in_edge)),
                    float(traci.edge.getLastStepHaltingNumber(out_edge)),
                ])
        obs.extend([
            float(self.current_green_alloc[0]),
            float(self.current_green_alloc[1]),
            float(self.current_green_alloc[2]),
            float(self.current_green_alloc[3])
        ])
        return np.array(obs, dtype=np.float32)

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        steps_taken = 0
        cycle_duration = 0.0
        print(f"\n🔄 STARTING CYCLE {self.current_cycle_count + 1} at {self._sim_time:.1f}s")
        print(f"⏱️  Running for {self.cycle} seconds (full cycle)")
        start_time = self._sim_time
        for step in range(self._steps_per_cycle):
            ok = self._safe_step(1)
            if not ok:
                print("❌ Simulation stopped due to SUMO connection failure")
                break
            steps_taken += 1
        cycle_duration = self._sim_time - start_time
        print(f"✅ CYCLE COMPLETED: {cycle_duration:.1f}s elapsed ({steps_taken} steps)")
        reward = self._compute_reward()
        self.current_cycle_count += 1
        training_progress = (self.current_cycle_count / self.total_training_cycles) * 100
        print(f"💰 Reward for this cycle: {reward:.2f}")
        print(f"📈 Training Progress: {training_progress:.1f}% ({self.current_cycle_count}/{self.total_training_cycles} cycles)")
        self._apply_action(action)
        self._apply_next_green()
        print("🔄 NEXT CYCLE SETTINGS:")
        self._print_final_cycle_summary()
        obs = self._get_observation()
        done = False
        try:
            pickle.dump(self.cumulative_time, open(SAVE_STATE_FILE, "wb"))
        except Exception:
            pass
        return obs, reward, done, False, {}
