import heapq
import json

fp_queue = []

def dispatch_fixed_priority_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks):
    # 使用 -task["safety"] 保证 safety 高的优先级高（heapq 是小顶堆）
    heapq.heappush(fp_queue, (-task["safety"], env.now, task))
    env.process(fp_scheduler_loop(mqtt_client, mqtt_topic, env, sensor_unit, completed_tasks))

def fp_scheduler_loop(mqtt_client, mqtt_topic, env, sensor_unit, completed_tasks):
    while True:
        if not fp_queue:
            yield env.timeout(0.1)
            continue

        # 如果“虚拟单核传感器”空闲，调度任务
        if not sensor_unit.resource.users:
            _, _, task = heapq.heappop(fp_queue)
            env.process(run_fixed_priority_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks))
        else:
            yield env.timeout(0.05)

def run_fixed_priority_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks):
    print(f"🔵 [{env.now:.2f}s] Start task {task['id']} on {sensor_unit.name} [safety={task['safety']}]")

    with sensor_unit.resource.request() as req:
        yield req
        yield env.timeout(task["duration"])

        mqtt_client.publish(mqtt_topic, json.dumps({
            "task_id": task["id"],
            "sensor": sensor_unit.name,
            "strategy": "fixed-priority",
            "time": env.now
        }))

        print(f"✅ [{env.now:.2f}s] Finished task {task['id']} on {sensor_unit.name}")

        completed_tasks.append({
            "id": task["id"],
            "arrival": task["arrival_time"],
            "deadline": task["deadline"],
            "finish": env.now,
            "strategy": "fixed-priority",
            "mode": "LO",
            "safety": task["safety"],
            "sensor_usage": {
                sensor_unit.name: task["duration"]
            }
        })
