

def compute_priority(task):
    return -(0.5 * task["safety"] + 0.5 * task["realtime"] - 0.1 * task["duration"])

