import simpy
import requests
import json
import paho.mqtt.client as mqtt



# --- Energy-aware scheduling ---
def dispatch_energy_aware_task(mqtt_client,MQTT_TOPIC,env, task, sensors):
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
