import simpy
import random

# 模拟参数
NUM_SENSORS = 2
SIM_TIME = 50  # 仿真时间

# 任务定义（criticality: 3 = 高，1 = 低）
tasks = [
    {"id": "T1", "criticality": 2, "duration": 5, "description": "Front Vehicle Distance Check"},
    {"id": "T2", "criticality": 3, "duration": 4, "description": "Emergency Obstacle Detection"},
    {"id": "T3", "criticality": 1, "duration": 6, "description": "Navigation Map Update"},
    {"id": "T4", "criticality": 3, "duration": 3, "description": "Pedestrian Crossing Detection"},
    {"id": "T5", "criticality": 2, "duration": 4, "description": "Lane Recommendation"}
]

class Sensor:
    def __init__(self, env, name):
        self.env = env
        self.name = name
        self.resource = simpy.PreemptiveResource(env, capacity=1)

    def use(self, task):
        print(f"[{self.env.now}] {task['id']} starts on {self.name} (criticality {task['criticality']})")
        yield self.env.timeout(task['duration'])
        print(f"[{self.env.now}] {task['id']} finishes on {self.name}")

class Scheduler:
    def __init__(self, env, sensors):
        self.env = env
        self.sensors = sensors

    def submit_task(self, task):
        sensor = random.choice(self.sensors)
        self.env.process(self.run_task(task, sensor))

    def run_task(self, task, sensor):
        with sensor.resource.request(priority=-task['criticality']) as req:
            try:
                yield req
                yield self.env.process(sensor.use(task))
            except simpy.Interrupt:
                print(f"[{self.env.now}] {task['id']} was preempted on {sensor.name}!")

# 仿真环境
env = simpy.Environment()
sensors = [Sensor(env, f"Sensor-{i}") for i in range(NUM_SENSORS)]
scheduler = Scheduler(env, sensors)

# 提交任务（可改为动态生成）
for t in tasks:
    sensor = random.choice(sensors)
    env.process(scheduler.run_task(t, sensor))
    env.run(until=env.now + random.randint(1, 3))
# 启动仿真
env.run(until=SIM_TIME)
