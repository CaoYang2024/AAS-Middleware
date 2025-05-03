import simpy
import random
import requests
import json
import paho.mqtt.client as mqtt

# --- Simulation and MQTT Parameters ---
NUM_SENSORS = 2
SIM_TIME = 50
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "simulation/task/finished"
BASE_SUBMODEL_URL = "http://localhost:8081/submodels/aHR0cHM6Ly9leGFtcGxlLmNvbS9pZHMvc20vOTAyM18yMjEwXzUwNTJfOTY0Mg/submodel-elements"
STRATEGY_FLAG = "fair"  # Strategy options: "asil-d-priority", "fair", "energy-aware"
# 1. "asil-d-priority":
#    - ASIL-D tasks have absolute priority.
#    - They preempt all other tasks and require both sensors to execute simultaneously.
#    - All other tasks are assigned based on computed priority: 0.5 * safety + 0.5 * realtime - 0.1 * duration.
#    - Non-D tasks only execute on a single available sensor.
#    - If preempted, non-D tasks are requeued.
#
# 2. "fair":
#    - Tasks are executed strictly in arrival order (FIFO), regardless of criticality.
#    - Each task uses only one available sensor.
#    - If both sensors are busy, task waits.
#    - No preemption is applied.
#
# 3. "energy-aware":
#    - Prioritizes tasks by computed score, but also minimizes sensor switching.
#    - Once a sensor starts executing a task, it is preferred to stay on same sensor unless idle.
#    - Tasks are mapped to the sensor with the shortest future estimated load.
#    - Only one sensor used per task.
#    - No preemption is used, intended for energy-constrained systems.

# --- Tasks ---
tasks = [{"id": f"Task{i}"} for i in range(1, 6)]

# --- Utility: Map safety levels A-D to 1-4 ---
def map_safety_level(level_str):
    mapping = {"A": 1, "B": 2, "C": 3, "D": 4}
    return mapping.get(level_str.upper(), 1)

# --- Fetch task data from BaSyx ---
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

# --- MQTT Client ---
mqtt_client = mqtt.Client()
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# --- Sensor Class ---
class Sensor:
    def __init__(self, env, name):
        self.env = env
        self.name = name
        self.resource = simpy.PreemptiveResource(env, capacity=1)

# --- Task Execution ---
def execute_task(env, task, sensors):
    if task['safety_str'] == 'D':
        # Wait until both sensors are available
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
        # Non-D task: use one available sensor
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
                    print(f"[{env.now:.2f}] {task['id']} was preempted on {sensor.name}, will retry")
                    # Reschedule the interrupted task
                    env.process(execute_task(env, task, sensors))

# --- Strategy: FIFO ---
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

# --- Strategy: Energy-Aware ---
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

for task in tasks:
    try:
        values = fetch_task_data_from_basyx(task["id"])
        task.update(values)
        print(f"✔️ Task loaded: {task}")
    except Exception as e:
        print(f"❌ Failed to load task {task['id']}: {e}")

arrival_plan = [
    (0.0, "Task1"),
    (0.5, "Task2"),
    (1.5, "Task3"),
    (2.0, "Task4"),
    (3.0, "Task5"),
]

for arrival_time, task_id in arrival_plan:
    t = next(task for task in tasks if task["id"] == task_id)

    # Only advance time if necessary
    if arrival_time > env.now:
        env.run(until=arrival_time)

    if STRATEGY_FLAG == "asil-d-priority":
        env.process(execute_task(env, t, sensors))
    elif STRATEGY_FLAG == "fair":
        dispatch_fair_task(env, t, sensors)
    elif STRATEGY_FLAG == "energy-aware":
        dispatch_energy_aware_task(env, t, sensors)

env.run(until=SIM_TIME)
mqtt_client.loop_stop()
mqtt_client.disconnect()
