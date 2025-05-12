import simpy
import requests
import json
import paho.mqtt.client as mqtt


def dispatch_fair_task(mqtt_client,MQTT_TOPIC,env, task, sensors):
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