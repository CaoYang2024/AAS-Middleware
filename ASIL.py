import simpy
import json
from compute import compute_priority

# 最大等待时间，超出即从 H0 切换到 H1 模式（使用 USB 摄像头）
MAX_WAIT_TIME = 2.0

# 全局任务完成日志
task_finish_log = []

def execute_task(mqtt_client, MQTT_TOPIC, env, task, sensors):
    sensor_csi = next(s for s in sensors if s.name == "CSI")
    sensor_usb = next(s for s in sensors if s.name == "USB")

    priority = compute_priority(task)

    with sensor_csi.resource.request(priority=priority) as req:
        wait_start = env.now
        result = yield req | env.timeout(MAX_WAIT_TIME)

        if req in result:
            try:
                print(f"[{env.now:.2f}] {task['id']} starts on CSI")
                yield env.timeout(task['duration'])
                print(f"[{env.now:.2f}] {task['id']} finishes on CSI")
                selected_sensor = "CSI"
            except simpy.Interrupt:
                print(f"[{env.now:.2f}] {task['id']} was preempted on CSI — rescheduling...")
                env.process(execute_task(mqtt_client, MQTT_TOPIC, env, task, sensors))
                return
        else:
            print(f"[{env.now:.2f}] {task['id']} waited too long, switching to USB")
            with sensor_usb.resource.request(priority=priority) as usb_req:
                try:
                    yield usb_req
                    print(f"[{env.now:.2f}] {task['id']} starts on USB")
                    yield env.timeout(task['duration'])
                    print(f"[{env.now:.2f}] {task['id']} finishes on USB")
                    selected_sensor = "USB"
                except simpy.Interrupt:
                    print(f"[{env.now:.2f}] {task['id']} was preempted on USB — rescheduling...")
                    env.process(execute_task(mqtt_client, MQTT_TOPIC, env, task, sensors))
                    return

    mqtt_client.publish(MQTT_TOPIC, json.dumps({
        "task_id": task["id"],
        "sensor": selected_sensor,
        "finish_time": env.now,
        "description": task["description"],
        "safety": task["safety_str"],
        "realtime": task["realtime"],
        "duration": task["duration"]
    }))

    task_finish_log.append({
        "task_id": task["id"],
        "sensor": selected_sensor,
        "finish_time": round(env.now, 2)
    })
