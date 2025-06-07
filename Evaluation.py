def evaluate(completed_tasks):
    total = len(completed_tasks)
    on_time = 0
    total_lateness = 0
    total_response = 0
    high_priority_total = 0
    high_priority_on_time = 0
    hi_mode_count = 0
    lo_mode_count = 0
    total_energy = 0.0

    for task in completed_tasks:
        response_time = task["finish"] - task["arrival"]
        lateness = task["finish"] - task["deadline"]
        total_response += response_time
        total_lateness += max(0, lateness)

        if task["finish"] <= task["deadline"]:
            on_time += 1
            if task["safety"] == 4:
                high_priority_on_time += 1
        if task["safety"] == 4:
            high_priority_total += 1

        if task.get("mode") == "HI":
            hi_mode_count += 1
        elif task.get("mode") == "LO":
            lo_mode_count += 1

        if "sensor_usage" in task:
            total_energy += sum(task["sensor_usage"].values())

    print("\n📊 Evaluation Summary:")
    print(f"✅ On-Time Completion Rate: {on_time}/{total} = {on_time/total:.2%}")
    print(f"⏱️ Average Lateness: {total_lateness / total:.2f} sec")
    print(f"⏱️ Average Response Time: {total_response / total:.2f} sec")

    if high_priority_total > 0:
        print(f"🚨 ASIL-D Completion Rate: {high_priority_on_time}/{high_priority_total} = {high_priority_on_time/high_priority_total:.2%}")

    if hi_mode_count + lo_mode_count > 0:
        print(f"⚙️ HI Mode Usage: {hi_mode_count} tasks")
        print(f"⚙️ LO Mode Usage: {lo_mode_count} tasks")

    print(f"\n🔋 Total Sensor Time Usage: {total_energy:.2f} seconds")
    print(f"⚡ Estimated Energy Usage: {total_energy * 2.0:.2f} unit-seconds (assuming DualCameraUnit power = 2.0)")
