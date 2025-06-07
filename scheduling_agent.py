import simpy
import requests
from plot import plot_gantt_chart
import paho.mqtt.client as mqtt
from EDF import (
    dispatch_earliest_deadline_task
)
from Dual import dispatch_hi_lo_shift_task
from FP import dispatch_fixed_priority_task
from Evaluation import evaluate
from FIFO import dispatch_no_scheduling_task

# --- Parameters ---
NUM_SENSORS = 2
SIM_TIME = 50
MQTT_BROKER = "172.22.80.1"
MQTT_PORT = 1883
MQTT_TOPIC = "simulation/task/finished"
BASE_SUBMODEL_URL = "http://localhost:8081/submodels/aHR0cHM6Ly9leGFtcGxlLmNvbS9pZHMvc20vOTAyM18yMjEwXzUwNTJfOTY0Mg/submodel-elements"

# --- Global Task Completion Record ---
completed_tasks = []

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
        return "fp"

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

# --- Main Simulation ---
env = simpy.Environment()
sensor_unit = Sensor(env, "DualCameraUnit")

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
    (0.0, "Task1"),  # Front Vehicle Distance Check
    (0.5, "Task2"),  # Emergency Obstacle Detection
    (1.5, "Task3"),  # Navigation Map Update
    (2.0, "Task4"),  # Lane Detection
    (3.0, "Task5"),  # Road Sign Recognition
]

# 语义驱动的 deadline 设定（时间窗口越紧，deadline 越靠前）
for arrival_time, task_id in arrival_plan:
    for task in tasks:
        if task["id"] == task_id:
            task["arrival_time"] = arrival_time
            if task_id == "Task2":  # Emergency → 超高优先
                slack = 1.0
            elif task_id == "Task1":  # Distance Check → 较高优先
                slack = 2.0
            elif task_id == "Task4":  # Lane Detection → 中等优先
                slack = 3.0
            elif task_id == "Task3":  # Map Update → 可延迟
                slack = 4.0
            elif task_id == "Task5":  # Sign Recognition → 最不紧急
                slack = 5.0
            else:
                slack = 3.0

            task["deadline"] = arrival_time + task["duration"]+slack
            print(f"📌 {task_id}: arrival={arrival_time}s, deadline={task['deadline']}s")

# Run simulation based on dynamic scheduling strategy
current_strategy = fetch_strategy_from_basyx()
print(f"🔀 Strategy at {env.now:.2f}: {current_strategy}")

for arrival_time, task_id in arrival_plan:
    # 找到当前任务
    t = next(task for task in tasks if task["id"] == task_id)

    # 推进仿真时间到 arrival_time（如果需要）
    if arrival_time > env.now:
        env.run(until=arrival_time)

    print(f"🔀 Strategy at {env.now:.2f}: {current_strategy}")

    if current_strategy == "fp":
        dispatch_fixed_priority_task(mqtt_client, MQTT_TOPIC, env, t, sensor_unit, completed_tasks)
    elif current_strategy == "edf":
        dispatch_earliest_deadline_task(mqtt_client, MQTT_TOPIC, env, t, sensor_unit, completed_tasks)
    elif current_strategy == "dual":
        dispatch_hi_lo_shift_task(mqtt_client, MQTT_TOPIC, env, t, sensor_unit, completed_tasks)
    else:
        print(f"⚠️ Unknown strategy '{current_strategy}', defaulting to no scheduling.")
        dispatch_no_scheduling_task(mqtt_client, MQTT_TOPIC, env, t, sensor_unit, completed_tasks)

env.run(until=SIM_TIME)
mqtt_client.loop_stop()
mqtt_client.disconnect()

evaluate(completed_tasks)
plot_gantt_chart(completed_tasks, current_strategy)