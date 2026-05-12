import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import os
import glob

# -----------------------------------------
#  Config
# -----------------------------------------

CSV_DIR = os.path.join(os.path.dirname(__file__), "csv")
OUT_DIR = os.path.join(os.path.dirname(__file__), "charts")
os.makedirs(OUT_DIR, exist_ok=True)

DRIVER_COLORS = {
    "RX":        "#4C72B0",
    "COROUTINE": "#55A868",
    "UPDATE":    "#C44E52",
}

INSTANCES = [1, 10, 100, 500, 1000]

# -----------------------------------------
#  Load & aggregate
# -----------------------------------------

def load_all(csv_dir):
    files = glob.glob(os.path.join(csv_dir, "*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {csv_dir}")
    frames = [pd.read_csv(f) for f in files]
    raw = pd.concat(frames, ignore_index=True)
    # average all numeric columns across runs
    group_keys = ["Driver", "TimerType", "Instances"]
    agg = raw.groupby(group_keys, as_index=False).mean(numeric_only=True)
    return agg

# -----------------------------------------
#  Chart helpers
# -----------------------------------------

def setup_style():
    sns.set_theme(style="darkgrid", palette="muted")
    plt.rcParams.update({
        "figure.facecolor": "#1a1a2e",
        "axes.facecolor":   "#16213e",
        "axes.edgecolor":   "#444466",
        "axes.labelcolor":  "#ccccdd",
        "xtick.color":      "#ccccdd",
        "ytick.color":      "#ccccdd",
        "text.color":       "#ccccdd",
        "grid.color":       "#2a2a4a",
        "grid.linewidth":   0.8,
        "font.family":      "monospace",
    })

def save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"  saved → {path}")
    plt.close(fig)

# -----------------------------------------
#  Chart 1 — GC by driver at 1000 instances (bar)
# -----------------------------------------

def chart_gc_at_1000(df):
    data = df[df["Instances"] == 1000].copy()
    drivers = list(DRIVER_COLORS.keys())

    timer_types = sorted(data["TimerType"].unique())
    x = range(len(timer_types))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#1a1a2e")

    for i, driver in enumerate(drivers):
        vals = []
        for tt in timer_types:
            row = data[(data["Driver"] == driver) & (data["TimerType"] == tt)]
            vals.append(row["GC_Mean"].values[0] if len(row) else 0)
        bars = ax.bar([xi + i * width for xi in x], vals, width,
                      label=driver, color=DRIVER_COLORS[driver], alpha=0.85)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=8, color="#ccccdd")

    ax.set_title("GC Allocation at 1000 Instances (MB)", fontsize=13, pad=12)
    ax.set_xlabel("Timer Type")
    ax.set_ylabel("GC Mean (MB)")
    ax.set_xticks([xi + width for xi in x])
    ax.set_xticklabels(timer_types)
    ax.legend(facecolor="#1a1a2e", edgecolor="#444466")
    save(fig, "gc_at_1000_instances.png")

# -----------------------------------------
#  Chart 2 — GC scaling across instance counts (line per driver)
# -----------------------------------------

def chart_gc_scaling(df):
    timer_types = sorted(df["TimerType"].unique())
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    fig.patch.set_facecolor("#1a1a2e")
    fig.suptitle("GC Allocation vs Instance Count", fontsize=14, y=1.01)

    for ax, tt in zip(axes.flat, timer_types):
        for driver, color in DRIVER_COLORS.items():
            sub = df[(df["Driver"] == driver) & (df["TimerType"] == tt)]
            sub = sub.sort_values("Instances")
            ax.plot(sub["Instances"], sub["GC_Mean"],
                    marker="o", label=driver, color=color, linewidth=2)
        ax.set_title(tt, fontsize=11)
        ax.set_xlabel("Instances")
        ax.set_ylabel("GC Mean (MB)")
        ax.set_xscale("log")

    handles = [mpatches.Patch(color=c, label=d) for d, c in DRIVER_COLORS.items()]
    fig.legend(handles=handles, loc="lower center", ncol=3,
               facecolor="#1a1a2e", edgecolor="#444466", bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout()
    save(fig, "gc_scaling.png")

# -----------------------------------------
#  Chart 3 — FPS stability (CoV = StdDev/Mean) heatmap
# -----------------------------------------

def chart_fps_stability(df):
    drivers = list(DRIVER_COLORS.keys())
    timer_types = sorted(df["TimerType"].unique())

    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    fig.patch.set_facecolor("#1a1a2e")
    fig.suptitle("FPS Instability (StdDev / Mean) — lower is better", fontsize=13)

    for ax, driver in zip(axes, drivers):
        matrix = []
        for tt in timer_types:
            row_vals = []
            for inst in INSTANCES:
                sub = df[(df["Driver"] == driver) &
                         (df["TimerType"] == tt) &
                         (df["Instances"] == inst)]
                if len(sub):
                    mean = sub["FPS_Mean"].values[0]
                    std  = sub["FPS_StdDev"].values[0]
                    cov  = round(std / mean, 2) if mean > 0 else 0
                else:
                    cov = 0
                row_vals.append(cov)
            matrix.append(row_vals)

        heat_df = pd.DataFrame(matrix, index=timer_types, columns=INSTANCES)
        sns.heatmap(heat_df, ax=ax, annot=True, fmt=".2f",
                    cmap="RdYlGn_r", vmin=0, vmax=0.6,
                    linewidths=0.5, linecolor="#1a1a2e",
                    cbar=ax == axes[-1])
        ax.set_title(driver, fontsize=11, color=DRIVER_COLORS[driver])
        ax.set_xlabel("Instances")
        if ax == axes[0]:
            ax.set_ylabel("Timer Type")

    fig.tight_layout()
    save(fig, "fps_stability_heatmap.png")

# -----------------------------------------
#  Chart 4 — FPS median comparison (reliable rows only)
# -----------------------------------------

def chart_fps_median(df):
    # only rows where CoV < 0.25 (reliable)
    df = df.copy()
    df["CoV"] = df["FPS_StdDev"] / df["FPS_Mean"]
    reliable = df[df["CoV"] < 0.25]

    timer_types = sorted(reliable["TimerType"].unique())
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    fig.patch.set_facecolor("#1a1a2e")
    fig.suptitle("FPS Median — stable runs only (CoV < 0.25)", fontsize=13)

    for ax, tt in zip(axes.flat, timer_types):
        for driver, color in DRIVER_COLORS.items():
            sub = reliable[(reliable["Driver"] == driver) & (reliable["TimerType"] == tt)]
            sub = sub.sort_values("Instances")
            if len(sub):
                ax.plot(sub["Instances"], sub["FPS_Median"],
                        marker="o", label=driver, color=color, linewidth=2)
        ax.set_title(tt, fontsize=11)
        ax.set_xlabel("Instances")
        ax.set_ylabel("FPS Median")
        ax.set_xscale("log")

    handles = [mpatches.Patch(color=c, label=d) for d, c in DRIVER_COLORS.items()]
    fig.legend(handles=handles, loc="lower center", ncol=3,
               facecolor="#1a1a2e", edgecolor="#444466", bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout()
    save(fig, "fps_median_stable.png")

# -----------------------------------------
#  Main
# -----------------------------------------

if __name__ == "__main__":
    print("Loading CSVs...")
    df = load_all(CSV_DIR)
    print(f"  {len(df)} configurations loaded (averaged across runs)")

    setup_style()
    print("Generating charts...")
    chart_gc_at_1000(df)
    chart_gc_scaling(df)
    chart_fps_stability(df)
    chart_fps_median(df)
    print("Done.")
