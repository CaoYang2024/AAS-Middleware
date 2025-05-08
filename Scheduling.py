import simpy
import requests
import json
import paho.mqtt.client as mqtt

# --- Parameters ---
NUM_SENSORS = 2
SIM_TIME = 50
MQTT_BROKER = "192.168.31.34"
MQTT_PORT = 1883
MQTT_TOPIC = "simulation/task/finished"
BASE_SUBMODEL_URL = "http://localhost:8081/submodels/aHR0cHM6Ly9leGFtcGxlLmNvbS9pZHMvc20vOTAyM18yMjEwXzUwNTJfOTY0Mg/submodel-elements"
# mosquitto_sub -h 192.168.31.34 -t "simulation/task/finished" -v
# --- Scheduling Strategy Summary ---
# This simulation supports three scheduling strategies for sensor task execution:
# 1. "asil-d-priority":
#    - ASIL-D tasks have absolute priority.
#    - They preempt all other tasks and require both sensors to execute simultaneously.
#    - Other tasks are prioritized based on: 0.5 × safety_score + 0.5 × realtime_score − 0.1 × duration.
#    - Non-D tasks only execute on one free sensor and can be preempted.
#
# 2. "fair":
#    - Tasks are executed strictly in the order of arrival (FIFO).
#    - Each task uses one available sensor.
#    - No preemption is allowed, regardless of task criticality.
#
# 3. "energy-aware":
#    - Tasks are prioritized using the same priority formula.
#    - The strategy attempts to minimize sensor switching to reduce energy cost.
#    - Each task is assigned to the sensor with the lowest load.
#    - No preemption is allowed (except ASIL-D handled separately).
# --- Strategy fetcher ---
def fetch_strategy_from_basyx():
    strategy_url = "http://localhost:8081/submodels/aHR0cHM6Ly9leGFtcGxlLmNvbS9pZHMvc20vMTIzMF8zMjEwXzUwNTJfODI5Nw/submodel-elements/simpy"
    try:
        response = requests.get(strategy_url)
        response.raise_for_status()
        data = response.json()
        return data.get("value", "fair").strip().lower()
    except Exception as e:
        print(f"❌ Failed to fetch scheduling strategy: {e}")
        return "fair"

# --- Task list ---
tasks = [{"id": f"Task{i}"} for i in range(1, 6)]

# --- Utility: Map safety levels A-D to 1-4 ---
def map_safety_level(level_str):
    mapping = {"A": 1, "B": 2, "C": 3, "D": 4}
    return mapping.get(level_str.upper(), 1)

# --- Fetch task data ---
def fetch_task_data_from_basyx(task_id):
    url = f"{BASE_SUBMODEL_URL}/{task_id}"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    description = ""
    for d in data.get("description", []):
        if d.get("language") == "en":
            description = d.get("text")

    duration = safety = realtime = None
    safety_str = "A"

    for prop in data.get("value", []):
        if prop.get("idShort") == "Duration":
            duration = float(prop["value"])
        elif prop.get("idShort") == "Safety_level":
            safety_str = prop["value"]
            safety = map_safety_level(safety_str)
        elif prop.get("idShort") == "Timing_criticality":
            realtime = int(prop["value"])

    return {
        "safety": safety,
        "safety_str": safety_str,
        "realtime": realtime,
        "duration": duration,
        "description": description
    }

# --- Priority calculation ---
def compute_priority(task):
    return -(0.5 * task["safety"] + 0.5 * task["realtime"] - 0.1 * task["duration"])

# --- MQTT setup ---
mqtt_client = mqtt.Client()
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# --- Sensor class ---
class Sensor:
    def __init__(self, env, name):
        self.env = env
        self.name = name
        self.resource = simpy.PreemptiveResource(env, capacity=1)

# --- ASIL-D & priority-based execution ---
def execute_task(env, task, sensors):
    if task['safety_str'] == 'D':
        reqs = [s.resource.request(priority=-999) for s in sensors]
        yield simpy.AllOf(env, reqs)
        print(f"[{env.now:.2f}] {task['id']} (ASIL-D) starts on both sensors")
        yield env.timeout(task['duration'])
        print(f"[{env.now:.2f}] {task['id']} finishes")
        for req, s in zip(reqs, sensors):
            s.resource.release(req)
        mqtt_client.publish(MQTT_TOPIC, json.dumps({
            "task_id": task["id"],
            "finish_time": env.now,
            "description": task["description"],
            "safety": task["safety_str"],
            "realtime": task["realtime"],
            "duration": task["duration"]
        }))
    else:
        sensor = next((s for s in sensors if s.resource.count == 0), None)
        if sensor:
            with sensor.resource.request(priority=compute_priority(task)) as req:
                try:
                    yield req
                    print(f"[{env.now:.2f}] {task['id']} starts on {sensor.name}")
                    yield env.timeout(task['duration'])
                    print(f"[{env.now:.2f}] {task['id']} finishes on {sensor.name}")
                    mqtt_client.publish(MQTT_TOPIC, json.dumps({
                        "task_id": task["id"],
                        "sensor": sensor.name,
                        "finish_time": env.now,
                        "description": task["description"],
                        "safety": task["safety_str"],
                        "realtime": task["realtime"],
                        "duration": task["duration"]
                    }))
                except simpy.Interrupt:
                    print(f"[{env.now:.2f}] {task['id']} preempted on {sensor.name}")
                    env.process(execute_task(env, task, sensors))

# --- Fair scheduling ---
def dispatch_fair_task(env, task, sensors):
    def fair_task():
        while True:
            for sensor in sensors:
                if sensor.resource.count == 0:
                    with sensor.resource.request() as req:
                        yield req
                        print(f"[{env.now:.2f}] {task['id']} starts on {sensor.name} (FIFO)")
                        yield env.timeout(task['duration'])
                        print(f"[{env.now:.2f}] {task['id']} finishes on {sensor.name} (FIFO)")
                        mqtt_client.publish(MQTT_TOPIC, json.dumps({
                            "task_id": task["id"],
                            "sensor": sensor.name,
                            "finish_time": env.now,
                            "description": task["description"],
                            "safety": task["safety_str"],
                            "realtime": task["realtime"],
                            "duration": task["duration"]
                        }))
                        return
            yield env.timeout(0.1)
    env.process(fair_task())

# --- Energy-aware scheduling ---
def dispatch_energy_aware_task(env, task, sensors):
    def estimate(sensor):
        return len(sensor.resource.queue) + sensor.resource.count
    sensor = min(sensors, key=estimate)
    def energy_task():
        with sensor.resource.request() as req:
            yield req
            print(f"[{env.now:.2f}] {task['id']} starts on {sensor.name} (energy-aware)")
            yield env.timeout(task['duration'])
            print(f"[{env.now:.2f}] {task['id']} finishes on {sensor.name} (energy-aware)")
            mqtt_client.publish(MQTT_TOPIC, json.dumps({
                "task_id": task["id"],
                "sensor": sensor.name,
                "finish_time": env.now,
                "description": task["description"],
                "safety": task["safety_str"],
                "realtime": task["realtime"],
                "duration": task["duration"]
            }))
    env.process(energy_task())

# --- Main Simulation ---
env = simpy.Environment()
sensors = [Sensor(env, "CSI"), Sensor(env, "USB")]

# Load task details
for task in tasks:
    try:
        values = fetch_task_data_from_basyx(task["id"])
        task.update(values)
        print(f"✔️ Task loaded: {task}")
    except Exception as e:
        print(f"❌ Failed to load task {task['id']}: {e}")

# Task arrival plan
arrival_plan = [
    (0.0, "Task1"),
    (0.5, "Task2"),
    (1.5, "Task3"),
    (2.0, "Task4"),
    (3.0, "Task5"),
]

# Run simulation based on dynamic scheduling strategy
for arrival_time, task_id in arrival_plan:
    t = next(task for task in tasks if task["id"] == task_id)

    if arrival_time > env.now:
        env.run(until=arrival_time)

    current_strategy = fetch_strategy_from_basyx()
    print(f"🔀 Strategy at {env.now:.2f}: {current_strategy}")

    if current_strategy == "asil-d-priority":
        env.process(execute_task(env, t, sensors))
    elif current_strategy == "fair":
        dispatch_fair_task(env, t, sensors)
    elif current_strategy == "energy-aware":
        dispatch_energy_aware_task(env, t, sensors)
    else:
        print(f"⚠️ Unknown strategy '{current_strategy}', defaulting to fair.")
        dispatch_fair_task(env, t, sensors)

env.run(until=SIM_TIME)
mqtt_client.loop_stop()
mqtt_client.disconnect()
