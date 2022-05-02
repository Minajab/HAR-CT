import os
import matplotlib.pyplot as plt

# # creating the dataset
data = {
            "Particle\nSwarm\nOptimization\n(PSO) + SVM": 87.50,
            "Convolutional\nNeura\nNetwork\n[11]": 95.28,
            "Anonymizing\nAutoEncoder": 92.9,
            "Proposed\nCNN": 96.74,
            "Proposed\nTernary\nWeight\nNetwork ": 96.03,
        }
sorted_date = {k: v for k, v in sorted(data.items(), key=lambda item: item[1])}
methods = list(sorted_date.keys())
rmse_values = list(sorted_date.values())
# Figure Size
fig, ax = plt.subplots(figsize=(16, 9))

# Horizontal Bar Plot
ax.barh(methods, rmse_values, color='maroon')
# Remove axes splines
for s in ['top', 'bottom', 'left', 'right']:
    ax.spines[s].set_visible(False)

# Remove x, y Ticks
ax.xaxis.set_ticks_position('none')
ax.yaxis.set_ticks_position('none')

# Add padding between axes and labels
ax.xaxis.set_tick_params(pad=5)
ax.yaxis.set_tick_params(pad=10)

# Add x, y gridlines
ax.grid(b=True, color='grey',
        linestyle='-.', linewidth=0.5,
        alpha=0.2)

# Show top values
ax.invert_yaxis()

# Add annotation to bars
for i in ax.patches:
    plt.text(i.get_width() + 0.2, i.get_y() + 0.5,
             str(round((i.get_width()), 2)),
             fontsize=10, fontweight='bold',
             color='grey')

# Add Plot Title

ax.set_title('Comparing Accuracy of Different Methods for MotionSense Dataset',
             loc='left', )

# Add Text watermark
# fig.text(0.9, 0.15, 'SSARSys', fontsize=12,
#          color='grey', ha='right', va='bottom',
#          alpha=0.7)

plt.savefig("res/accuracy_comparison_of_motion_sense.jpg")
