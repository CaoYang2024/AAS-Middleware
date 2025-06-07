import heapq
import json
import simpy

edf_queue = []
current_task = None  # 当前执行任务
current_deadline = None

def dispatch_earliest_deadline_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks):
    heapq.heappush(edf_queue, (task["deadline"], env.now, task))
    env.process(preemptive_edf_scheduler(mqtt_client, mqtt_topic, env, sensor_unit, completed_tasks))

def preemptive_edf_scheduler(mqtt_client, mqtt_topic, env, sensor_unit, completed_tasks):
    global current_task, current_deadline

    while True:
        if not edf_queue:
            yield env.timeout(0.1)
            continue

        if not sensor_unit.resource.users:
            _, _, task = heapq.heappop(edf_queue)
            task["dispatched"] = True
            current_task = task
            current_deadline = task["deadline"]
            env.process(run_edf_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks))
        else:
            # 如果当前任务 deadline 更晚，抢占
            _, _, next_task = edf_queue[0]
            if current_deadline and next_task["deadline"] < current_deadline:
                print(f"⚠️ [{env.now:.2f}s] Preempting task {current_task['id']} for earlier {next_task['id']}")
                sensor_unit.resource.users[0].proc.interrupt("preempted")
        yield env.timeout(0.05)

def run_edf_task(mqtt_client, mqtt_topic, env, task, sensor_unit, completed_tasks):
    global current_task, current_deadline

    remaining = task["duration"]
    start_time = env.now

    try:
        with sensor_unit.resource.request(priority=task["deadline"], preempt=True) as req:
            yield req
            while remaining > 0:
                try:
                    t0 = env.now
                    yield env.timeout(remaining)
                    break
                except simpy.Interrupt:
                    elapsed = env.now - t0
                    remaining -= elapsed
                    print(f"⏸️ [{env.now:.2f}s] {task['id']} interrupted, remaining {remaining:.2f}s")
                    task["dispatched"] = False
                    heapq.heappush(edf_queue, (task["deadline"], env.now, task))
                    return

            mqtt_client.publish(mqtt_topic, json.dumps({
                "task_id": task["id"],
                "sensor": sensor_unit.name,
                "strategy": "preemptive-edf",
                "time": env.now
            }))

            print(f"✅ [{env.now:.2f}s] Finished task {task['id']} on {sensor_unit.name}")
            completed_tasks.append({
                "id": task["id"],
                "arrival": task["arrival_time"],
                "deadline": task["deadline"],
                "finish": env.now,
                "strategy": "preemptive-edf",
                "mode": "LO",
                "safety": task["safety"],
                "sensor_usage": {
                    sensor_unit.name: task["duration"]
                }
            })

    except simpy.Interrupt:
        print(f"⚠️ [{env.now:.2f}s] {task['id']} was interrupted before running")
        task["dispatched"] = False
        heapq.heappush(edf_queue, (task["deadline"], env.now, task))
    finally:
        current_task = None
        current_deadline = None
