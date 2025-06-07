import json
import simpy

no_sched_queue = []

def dispatch_no_scheduling_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks):
    no_sched_queue.append(task)
    env.process(no_scheduling_loop(mqtt_client, mqtt_topic, env, sensor_unit, completed_tasks))

def no_scheduling_loop(mqtt_client, mqtt_topic, env, sensor_unit, completed_tasks):
    while True:
        if not no_sched_queue:
            yield env.timeout(0.1)
            continue

        if not sensor_unit.resource.users:
            task = no_sched_queue.pop(0)
            env.process(run_no_sched_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks))
        else:
            yield env.timeout(0.05)

def run_no_sched_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks):
    print(f"🔵 [{env.now:.2f}s] Start task {task['id']} on {sensor_unit.name}")

    with sensor_unit.resource.request() as req:
        yield req
        yield env.timeout(task["duration"])

        mqtt_client.publish(mqtt_topic, json.dumps({
            "task_id": task["id"],
            "sensor": sensor_unit.name,
            "strategy": "no-scheduling",
            "time": env.now
        }))

        print(f"✅ [{env.now:.2f}s] Finished task {task['id']}")

        completed_tasks.append({
            "id": task["id"],
            "arrival": task["arrival_time"],
            "deadline": task["deadline"],
            "finish": env.now,
            "strategy": "no-scheduling",
            "mode": "LO",
            "safety": task["safety"],
            "sensor_usage": {
                sensor_unit.name: task["duration"]
            }
        })
