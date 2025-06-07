import json
import simpy

dual_queue = []

def dispatch_hi_lo_shift_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks):
    # 设置默认 wcet_lo/wcet_hi（如未指定）
    task.setdefault("wcet_lo", task["duration"])
    task.setdefault("wcet_hi", task["duration"])

    dual_queue.append(task)
    env.process(dual_scheduler_loop(mqtt_client, mqtt_topic, env, sensor_unit, completed_tasks))

def dual_scheduler_loop(mqtt_client, mqtt_topic, env, sensor_unit, completed_tasks):
    while True:
        if not dual_queue:
            yield env.timeout(0.1)
            continue

        if not sensor_unit.resource.users:
            task = dual_queue.pop(0)
            env.process(run_dual_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks))
        else:
            yield env.timeout(0.05)

def run_dual_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks):
    wcet_lo = task.get("wcet_lo", task["duration"])
    wcet_hi = task.get("wcet_hi", task["duration"])

    # 判断是否进入高关键性模式
    if task["duration"] > wcet_lo:
        mode = "HI"
        adjusted_duration = task["duration"] / 2  # 执行效率提升（例如双倍速度）
    else:
        mode = "LO"
        adjusted_duration = task["duration"]

    print(f"🔵 [{env.now:.2f}s] Start task {task['id']} in {mode} mode on {sensor_unit.name}")

    with sensor_unit.resource.request() as req:
        yield req
        yield env.timeout(adjusted_duration)

        mqtt_client.publish(mqtt_topic, json.dumps({
            "task_id": task["id"],
            "sensor": sensor_unit.name,
            "strategy": "dual-criticality",
            "mode": mode,
            "time": env.now
        }))

        print(f"✅ [{env.now:.2f}s] Finished task {task['id']} in {mode} mode")

        completed_tasks.append({
            "id": task["id"],
            "arrival": task["arrival_time"],
            "deadline": task["deadline"],
            "finish": env.now,
            "strategy": "dual-criticality",
            "mode": mode,
            "safety": task["safety"],
            "sensor_usage": {
                sensor_unit.name: adjusted_duration
            }
        })
