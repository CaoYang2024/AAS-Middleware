import matplotlib
matplotlib.use('TkAgg')  # 避免 PyCharm 后端兼容问题

import matplotlib.pyplot as plt
import matplotlib.cm as cm

def plot_gantt_chart(completed_tasks, strategy_name="", show_plot=True):
    if not strategy_name:
        strategy_name = "FIFO"  # 默认策略名称补丁

    fig, ax = plt.subplots(figsize=(10, 2.5))

    y_pos = 10  # 固定唯一 Y 轴

    # 为每个 task ID 分配颜色（使用 colormap）
    task_ids = [task["id"] for task in completed_tasks]
    unique_ids = sorted(set(task_ids))
    color_map = cm.get_cmap("tab20", len(unique_ids))
    task_colors = {task_id: color_map(i) for i, task_id in enumerate(unique_ids)}

    for task in completed_tasks:
        usage = task.get("sensor_usage", {})
        for sensor, duration in usage.items():
            start_time = task["finish"] - duration
            color = task_colors.get(task["id"], "lightblue")

            ax.broken_barh([(start_time, duration)], (y_pos, 8), facecolors=color)
            ax.text(start_time + duration / 2, y_pos + 4,
                    task["id"], ha='center', va='center', fontsize=8, color='black')

    ax.set_yticks([y_pos + 4])
    ax.set_yticklabels(["CameraDataFlow"])
    ax.set_xlabel("Time (s)")
    ax.set_title(f"Task Execution Timeline — {strategy_name.upper()}")
    ax.grid(True, axis='x')

    plt.tight_layout()
    plt.savefig(f"gantt_{strategy_name}.png", dpi=300)
    print(f"📁 Gantt chart saved as gantt_{strategy_name}.png")

    if show_plot:
        plt.show()
