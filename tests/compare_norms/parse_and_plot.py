#!/usr/bin/env python3
"""
Parse IFS-NEMO validation output and create a dashboard showing
differences of prognostic 2-norms between diverging runs.
"""

import re
import sys
import os
import glob as _glob
import argparse
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_norms import parse_yaml_arrays

_p = argparse.ArgumentParser(description="Plot norm comparison between two IFS-NEMO result YAMLs")
_p.add_argument('ref_dir',     help="Reference results directory (containing result.*.yaml)")
_p.add_argument('test_dir',    help="Test results directory (containing result.*.yaml)")
_p.add_argument('--output-dir', default='.', dest='output_dir',
                help="Directory in which to save output PNG files (default: current dir)")
_p.add_argument('--annotation', default='', dest='annotation',
                help="Optional identifying text rendered in a footnote box on each figure")
_args = _p.parse_args()

_output_dir = _args.output_dir
os.makedirs(_output_dir, exist_ok=True)
_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
_annotation = _args.annotation

def _find_yaml(d):
    hits = _glob.glob(os.path.join(d, 'result.*.yaml'))
    if len(hits) != 1:
        sys.exit(f"Expected exactly 1 result YAML in {d}, found {len(hits)}")
    return hits[0]

ref_arrays  = parse_yaml_arrays(_find_yaml(_args.ref_dir))
test_arrays = parse_yaml_arrays(_find_yaml(_args.test_dir))

# Build paired variables dict: {varname: [(ref_val, test_val), …]}
# Zipped element-wise; arrays of different lengths are truncated to the shorter.
_common   = sorted(set(ref_arrays) & set(test_arrays))
variables = {var: list(zip(ref_arrays[var], test_arrays[var])) for var in _common}

# For each variable, compute relative difference per timestep

# For multi-valued vars, we have 3 stats per timestep
# (mean, min, max). The last_step variable tells us the total timestep count.

# Extract the authoritative timestep count from the file
if 'last_step' in variables and len(variables['last_step']) > 0:
    last_step = int(variables['last_step'][0][0])  # ref column
else:
    # Fallback: infer from the most common value count
    last_step = None

print(f"last_step from file: {last_step}")

# Compute relative difference |ref - test| / max(|ref|, |test|, eps)
def rel_diff(ref, test):
    denom = max(abs(ref), abs(test), 1e-30)
    return abs(ref - test) / denom

# For the visualization, compute per-variable, per-timestep relative differences
# For variables with 3 values per timestep, take the max relative diff across the 3

var_data = OrderedDict()
for var, vals in variables.items():
    n = len(vals)
    if var == 'last_step':
        continue  # skip metadata
    
    if n == 0:
        continue
    
    # Determine values per timestep using last_step as the anchor
    if n == 1:
        # Single scalar value (e.g., ifs_sp_div) — 1 timestep, 1 val
        vpt = 1
        n_ts = 1
    elif last_step is not None:
        if n == last_step:
            # Exactly one value per timestep (e.g., ssh_norm_max)
            vpt = 1
            n_ts = last_step
        elif n % last_step == 0:
            # Multiple values per timestep (typically 3: mean/min/max)
            vpt = n // last_step
            n_ts = last_step
        elif n % 3 == 0 and n // 3 <= last_step:
            # Fewer timesteps than last_step but has 3 stats each
            # (e.g., wam_wpp with only 2 output timesteps)
            vpt = 3
            n_ts = n // 3
        elif n < last_step:
            # Fewer values than timesteps, treat as 1 per timestep
            vpt = 1
            n_ts = n
        else:
            # Unknown structure — best guess: 3 per timestep
            vpt = 3
            n_ts = n // 3
    else:
        # No last_step available — heuristic fallback
        if n % 3 == 0:
            vpt = 3
            n_ts = n // 3
        else:
            vpt = 1
            n_ts = n
    
    timestep_diffs = []
    for t in range(n_ts):
        max_rd = 0
        for v in range(vpt):
            idx = t * vpt + v
            if idx < n:
                rd = rel_diff(vals[idx][0], vals[idx][1])
                max_rd = max(max_rd, rd)
        timestep_diffs.append(max_rd)
    
    var_data[var] = {
        'n_timesteps': n_ts,
        'n_values': n,
        'vpt': vpt,
        'diffs': timestep_diffs,
    }

print("\nVariable structure:")
for var, d in var_data.items():
    avg_diff = np.mean(d['diffs'])
    max_diff = np.max(d['diffs'])
    print(f"  {var}: {d['n_timesteps']} timesteps, {d['vpt']} vals/ts, "
          f"avg_rel_diff={avg_diff:.2e}, max_rel_diff={max_diff:.2e}")

# ----- VISUALIZATION -----
# Separate into IFS (atmosphere) and WAM (wave) and NEMO (ocean) groups
ifs_vars = [v for v in var_data if v.startswith('ifs_')]
wam_vars = [v for v in var_data if v.startswith('wam_')]
nemo_vars = [v for v in var_data if v.startswith(('ssh_', 'U_', 'S_', 'T_'))]

# If no NEMO in nemo_vars, check for remaining
other_vars = [v for v in var_data if v not in ifs_vars and v not in wam_vars and v not in nemo_vars]
nemo_vars = nemo_vars + other_vars

print(f"\nIFS vars: {ifs_vars}")
print(f"WAM vars: {wam_vars}")
print(f"NEMO vars: {nemo_vars}")

# Filter to variables with >1 timestep for interesting plots
multi_ts_vars = [v for v in var_data if var_data[v]['n_timesteps'] > 1]

# Create figure with subplots: one per variable (multi-timestep ones)
# Use a grid layout

all_vars = multi_ts_vars
n_vars = len(all_vars)
print(f"\nPlotting {n_vars} variables with multiple timesteps")

plt.style.use('default')

# Light mode color scheme
BG_COLOR = '#ffffff'
PANEL_BG = '#f6f8fa'
TEXT_COLOR = '#1f2328'
GRID_COLOR = '#d1d9e0'
BORDER_COLOR = '#d1d9e0'
MUTED_TEXT = '#656d76'

def diff_color(rd):
    """Colorblind-safe palette: uses luminance + hue channels that survive
    deuteranopia and protanopia (no red-green distinction)."""
    if rd < 1e-10:
        return '#1b9e77'   # teal - bitwise-close (dark, cool)
    elif rd < 1e-6:
        return '#7570b3'   # purple - excellent
    elif rd < 1e-3:
        return '#e6ab02'   # amber/gold - acceptable
    elif rd < 1e-1:
        return '#e7298a'   # magenta - notable
    else:
        return '#d95f02'   # orange - significant

def adaptive_xticks(ax, n_ts, fig_width_inches=18):
    """Set x-axis ticks that coarsen automatically when there are too many timesteps.
    Targets roughly 1 label per ~0.4 inches of plot width to stay readable."""
    plot_width = fig_width_inches * 0.82  # approximate data area fraction
    max_labels = int(plot_width / 0.4)    # ~0.4 inches per label minimum
    
    if n_ts <= max_labels:
        # Every timestep gets a label
        step = 1
    else:
        # Pick a "nice" step: 2, 5, 10, 20, 25, 50, 100, ...
        raw_step = n_ts / max_labels
        nice_steps = [2, 5, 10, 15, 20, 25, 50, 100, 200, 250, 500, 1000]
        step = nice_steps[0]
        for ns in nice_steps:
            if ns >= raw_step:
                step = ns
                break
        else:
            step = nice_steps[-1]
    
    ticks = np.arange(0, n_ts, step)
    # Always include the last timestep
    if ticks[-1] != n_ts - 1:
        ticks = np.append(ticks, n_ts - 1)
    
    ax.set_xticks(ticks)
    # Labels are 1-indexed timestep numbers
    ax.set_xticklabels([str(t + 1) for t in ticks],
                       fontsize=max(5, min(7, 200 / n_ts)), color=MUTED_TEXT)

def find_zero_runs(mask):
    """Find contiguous runs of True in a 1D boolean array.
    Returns list of (start, end) inclusive index pairs."""
    runs = []
    in_run = False
    for i, v in enumerate(mask):
        if v and not in_run:
            start = i
            in_run = True
        elif not v and in_run:
            runs.append((start, i - 1))
            in_run = False
    if in_run:
        runs.append((start, len(mask) - 1))
    return runs

# Determine the "main" timestep count (the most common one among multi-ts vars)
ts_counts = [var_data[v]['n_timesteps'] for v in var_data if var_data[v]['n_timesteps'] > 1]
if ts_counts:
    from collections import Counter
    main_ts = Counter(ts_counts).most_common(1)[0][0]
else:
    main_ts = 24
print(f"  Main timestep count: {main_ts}")

# Group variables by component, separate main-ts from short-ts
groups_main = OrderedDict()
groups_short = OrderedDict()
groups_scalar = OrderedDict()
for v in var_data:
    if v.startswith('ifs_'):
        g = 'IFS (Atmosphere)'
    elif v.startswith('wam_'):
        g = 'WAM (Wave)'
    elif v.startswith(('ssh_', 'U_', 'S_')):
        g = 'NEMO (Ocean)'
    else:
        g = 'Other'
    
    n_ts = var_data[v]['n_timesteps']
    if n_ts == main_ts:
        if g not in groups_main:
            groups_main[g] = []
        groups_main[g].append(v)
    elif n_ts > 1:
        if g not in groups_short:
            groups_short[g] = []
        groups_short[g].append(v)
    else:
        if g not in groups_scalar:
            groups_scalar[g] = []
        groups_scalar[g].append(v)

# Count rows
n_full_rows = sum(len(vs) for vs in groups_main.values())
# Short vars: one row per group
n_short_rows = len(groups_short)
# Scalars: one summary row
n_scalar_rows = 1 if groups_scalar else 0
n_total = n_full_rows + n_short_rows + n_scalar_rows

print(f"  Full rows: {n_full_rows}")
print(f"  Short group rows: {n_short_rows}")
print(f"  Scalar row: {n_scalar_rows}")

from matplotlib.gridspec import GridSpec
from matplotlib.patches import Patch

fig_height = max(14, n_total * 1.6 + 3)
fig = plt.figure(figsize=(18, fig_height), facecolor=BG_COLOR)

# Use gridspec for flexible row heights
height_ratios = []
row_map = []  # (type, group, var) for each row
for g, vs in groups_main.items():
    for v in vs:
        height_ratios.append(1)
        row_map.append(('full', g, v))
for g, vs in groups_short.items():
    height_ratios.append(1.2)
    row_map.append(('short', g, vs))
if groups_scalar:
    height_ratios.append(0.8)
    all_scalars = []
    for vs in groups_scalar.values():
        all_scalars.extend(vs)
    row_map.append(('scalar', 'IFS (Atmosphere)', all_scalars))

gs = GridSpec(len(height_ratios), 1, figure=fig, height_ratios=height_ratios,
              hspace=0.4, top=0.95, bottom=0.04)

fig.suptitle(f'ifsnemo-compare: Norm Comparison Output · {main_ts} Timesteps',
             fontsize=18, fontweight='bold', color=TEXT_COLOR, y=0.99,
             fontfamily='monospace')
fig.text(0.5, 0.965,
         'Relative difference  |ref − test| / max(|ref|, |test|)  per output step',
         fontsize=11, color=MUTED_TEXT, ha='center', fontfamily='monospace')

# Track which group we're in for separators
prev_group = None
axes_list = []

for row_idx, (rtype, group, data) in enumerate(row_map):
    ax = fig.add_subplot(gs[row_idx])
    axes_list.append(ax)
    ax.set_facecolor(PANEL_BG)
    
    if rtype == 'full':
        var = data
        d = var_data[var]
        n_ts = d['n_timesteps']
        diffs = np.array(d['diffs'])
        x = np.arange(n_ts)
        colors = [diff_color(rd) for rd in diffs]
        
        # Bars as thick as possible: width=1.0, no gaps, solid fill
        bar_w = 1.0
        
        ax.bar(x, diffs, color=colors, width=bar_w, edgecolor='none',
               alpha=0.9, zorder=3, linewidth=0)
        ax.set_yscale('log')
        
        nonzero = diffs[diffs > 0]
        if len(nonzero) > 0:
            ymin = max(nonzero.min() * 0.2, 1e-16)
            ymax = nonzero.max() * 8
            ax.set_ylim(ymin, ymax)
        
        ax.set_xlim(-0.6, n_ts - 0.4)
        adaptive_xticks(ax, n_ts)
        
        # Label inside the plot area, top-left
        # Asterisk marks variables where max-of-3 stats is shown
        var_label = f'{var}*' if var_data[var]['vpt'] > 1 else var
        ax.text(0.005, 0.92, var_label, transform=ax.transAxes,
                fontsize=11, fontweight='bold', color=TEXT_COLOR,
                ha='left', va='top', fontfamily='monospace',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=PANEL_BG,
                         edgecolor=BORDER_COLOR, alpha=0.95))
        
        mean_rd = np.mean(diffs)
        max_rd = np.max(diffs)
        ax.text(0.995, 0.92, f'mean {mean_rd:.1e}  ·  max {max_rd:.1e}',
                transform=ax.transAxes, fontsize=8, color=MUTED_TEXT,
                ha='right', va='top', fontfamily='monospace',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=PANEL_BG,
                         edgecolor=BORDER_COLOR, alpha=0.95))
    
    elif rtype == 'short':
        # Multiple variables with 2 timesteps, show as grouped bars
        var_list = data
        n_v = len(var_list)
        x_positions = np.arange(n_v)
        bar_width = 0.35
        
        # For each var, show timestep 1 and timestep 2 as paired bars
        ts1_vals = []
        ts2_vals = []
        labels = []
        for v in var_list:
            d = var_data[v]
            ts1_vals.append(d['diffs'][0])
            ts2_vals.append(d['diffs'][1] if len(d['diffs']) > 1 else 0)
            labels.append(v)
        
        ts1_vals = np.array(ts1_vals)
        ts2_vals = np.array(ts2_vals)
        
        bars1 = ax.bar(x_positions - bar_width/2, ts1_vals, bar_width,
                       color='#58a6ff', alpha=0.85, label='t=0 (initial)', zorder=3)
        bars2 = ax.bar(x_positions + bar_width/2, ts2_vals, bar_width,
                       color='#f97583', alpha=0.85, label='t=last', zorder=3)
        
        # Color each bar by its magnitude
        for bar, val in zip(bars1, ts1_vals):
            bar.set_facecolor(diff_color(val))
        for bar, val in zip(bars2, ts2_vals):
            bar.set_facecolor(diff_color(val))
            bar.set_hatch('///')
            bar.set_edgecolor('#ffffff20')
        
        ax.set_yscale('log')
        ax.set_xlim(-0.5, n_v - 0.5)
        ax.set_xticks(x_positions)
        ax.set_xticklabels(labels, fontsize=9, color=TEXT_COLOR, fontfamily='monospace',
                           fontweight='bold')
        
        all_vals = np.concatenate([ts1_vals, ts2_vals])
        nonzero = all_vals[all_vals > 0]
        if len(nonzero) > 0:
            ax.set_ylim(nonzero.min() * 0.2, nonzero.max() * 8)
        
        ax.set_title(f'{group} — 2-timestep vars (solid=t_0, hatched=t_n)',
                     fontsize=10, color=MUTED_TEXT, loc='left',
                     fontfamily='monospace', pad=4)
    
    elif rtype == 'scalar':
        # Single-value scalars: horizontal bar chart
        var_list = data
        labels = []
        vals = []
        for v in var_list:
            d = var_data[v]
            labels.append(v)
            vals.append(d['diffs'][0])
        
        y_pos = np.arange(len(labels))
        vals = np.array(vals)
        colors = [diff_color(v) if v > 0 else '#1b9e77' for v in vals]
        
        # Replace 0 with tiny value for log display
        display_vals = np.where(vals > 0, vals, 1e-16)
        
        ax.barh(y_pos, display_vals, color=colors, height=0.5, alpha=0.9, zorder=3)
        ax.set_xscale('log')
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=10, color=TEXT_COLOR, fontfamily='monospace',
                           fontweight='bold')
        ax.set_xlim(1e-16, 1e-5)
        ax.invert_yaxis()
        
        # Annotate exact values
        for j, (v, val) in enumerate(zip(labels, vals)):
            label = f'{val:.2e}' if val > 0 else 'identical'
            ax.text(max(val * 2, 1e-15), j, f'  {label}', va='center',
                    fontsize=8, color=MUTED_TEXT, fontfamily='monospace')
        
        ax.set_title(f'IFS scalar fields (single output at step {main_ts})',
                     fontsize=10, color=MUTED_TEXT, loc='left',
                     fontfamily='monospace', pad=4)
    
    # Common styling
    ax.tick_params(axis='y', labelsize=7, colors=MUTED_TEXT)
    ax.tick_params(axis='x', labelsize=7, colors=MUTED_TEXT)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color(BORDER_COLOR)
    ax.spines['left'].set_color(BORDER_COLOR)
    ax.grid(axis='y' if rtype != 'scalar' else 'x',
            color=GRID_COLOR, linewidth=0.5, alpha=0.5, zorder=0)
    
    prev_group = group

# X-label on last full-row axis
for ax_info, ax_obj in zip(reversed(row_map), reversed(axes_list)):
    if ax_info[0] == 'full':
        ax_obj.set_xlabel('Timestep', fontsize=10, color=MUTED_TEXT, fontfamily='monospace')
        break

# Legend — tight to bottom
legend_elements = [
    Patch(facecolor='#1b9e77', label='< 1e-10'),
    Patch(facecolor='#7570b3', label='< 1e-6'),
    Patch(facecolor='#e6ab02', label='< 1e-3'),
    Patch(facecolor='#e7298a', label='< 1e-1'),
    Patch(facecolor='#d95f02', label='≥ 1e-1'),
]
fig.legend(handles=legend_elements, loc='lower center', ncol=5,
           fontsize=9, frameon=True, fancybox=True,
           facecolor=PANEL_BG, edgecolor=BORDER_COLOR,
           labelcolor=TEXT_COLOR, bbox_to_anchor=(0.5, 0.005))

# Asterisk footnote
fig.text(0.5, -0.003,
         '* max of relative differences across mean/min/max stats at each timestep',
         fontsize=9, color=MUTED_TEXT, ha='center', fontfamily='monospace',
         fontstyle='italic')

if _annotation:
    fig.text(0.01, 0.002, _annotation, fontsize=7, color=MUTED_TEXT,
             fontfamily='monospace', ha='left', va='bottom',
             bbox=dict(boxstyle='round,pad=0.3', facecolor=PANEL_BG,
                       edgecolor=BORDER_COLOR, alpha=0.85))

_dashboard_png = os.path.join(_output_dir, f'validation_dashboard_{_ts}.png')
plt.savefig(_dashboard_png, dpi=150, facecolor=BG_COLOR,
            bbox_inches='tight', pad_inches=0.2)
plt.close()
print(f"\nSaved {_dashboard_png}")
print(f"ARTIFACT: {_dashboard_png}")

# --- SECOND FIGURE: Summary heatmap ---
# Variable x Timestep heatmap of log10(relative diff)
# Colorblind-safe: use 'cividis' (perceptually uniform, designed for deuteranopia/protanopia)

# Use variables with main timestep count for clean heatmap
vars_main = [v for v in var_data if var_data[v]['n_timesteps'] == main_ts]

if vars_main:
    n_ts = main_ts
    n_vars_h = len(vars_main)
    
    fig2, ax2 = plt.subplots(figsize=(16, max(4, n_vars_h * 0.6 + 2)),
                              facecolor=BG_COLOR)
    
    # Build matrix; track exact zeros separately
    matrix = np.zeros((n_vars_h, n_ts))
    zero_mask = np.zeros((n_vars_h, n_ts), dtype=bool)
    for i, v in enumerate(vars_main):
        for j, d in enumerate(var_data[v]['diffs'][:n_ts]):
            if d == 0.0:
                zero_mask[i, j] = True
                matrix[i, j] = np.nan  # will show as masked
            else:
                matrix[i, j] = np.log10(d)
    
    # Use cividis: perceptually uniform, colorblind-safe (monotonic luminance)
    cmap = plt.cm.cividis_r.copy()
    cmap.set_bad(color='#eaeef2')  # NaN cells (exact zeros) get light neutral bg
    
    im = ax2.imshow(matrix, aspect='auto', cmap=cmap,
                     interpolation='nearest',
                     vmin=-15, vmax=0)
    
    # --- Zero-stamping: adaptive to timestep density ---
    # For each row, find contiguous zero-runs and draw:
    #   - isolated zeros: tiny "0" text
    #   - spans (2+ consecutive): "|--- 0 ---|" bracket notation
    ZERO_COLOR = '#0969da'  # blue that works on light bg and is colorblind-safe
    
    # Cell width in data coords is 1.0; determine a "tiny" font size
    # that scales down as n_ts grows
    tiny_fontsize = max(3, min(13, 300 / n_ts))
    
    for i in range(n_vars_h):
        row_zeros = zero_mask[i, :]
        if not row_zeros.any():
            continue
        
        runs = find_zero_runs(row_zeros)
        for (start, end) in runs:
            span_len = end - start + 1
            
            if span_len == 1:
                # Isolated zero: tiny "0"
                ax2.text(start, i, '0', ha='center', va='center',
                         fontsize=tiny_fontsize, fontweight='bold',
                         color=ZERO_COLOR, fontfamily='monospace')
            else:
                # Span: draw bracket |--- 0 ---|
                center = (start + end) / 2.0
                # Bracket end caps (vertical bars)
                cap_offset = 0.42  # slightly inside cell edges
                y_top = i - 0.25
                y_bot = i + 0.25
                
                # Left cap |
                ax2.plot([start - cap_offset, start - cap_offset],
                         [y_top, y_bot], color=ZERO_COLOR,
                         linewidth=1.5, solid_capstyle='round', zorder=5)
                # Right cap |
                ax2.plot([end + cap_offset, end + cap_offset],
                         [y_top, y_bot], color=ZERO_COLOR,
                         linewidth=1.5, solid_capstyle='round', zorder=5)
                # Horizontal dashes connecting caps
                ax2.plot([start - cap_offset, end + cap_offset],
                         [i, i], color=ZERO_COLOR,
                         linewidth=1.0, linestyle=(0, (4, 3)),
                         solid_capstyle='round', zorder=5)
                # "0" label at center
                label_fontsize = max(5, min(12, 600 / n_ts * span_len**0.3))
                ax2.text(center, i, '0', ha='center', va='center',
                         fontsize=label_fontsize, fontweight='bold',
                         color=ZERO_COLOR, fontfamily='monospace',
                         bbox=dict(boxstyle='round,pad=0.15',
                                  facecolor='#eaeef2', edgecolor='none',
                                  alpha=0.9),
                         zorder=6)
    
    ax2.set_yticks(range(n_vars_h))
    heatmap_labels = [f'{v}*' if var_data[v]['vpt'] > 1 else v for v in vars_main]
    ax2.set_yticklabels(heatmap_labels, fontsize=10, color=TEXT_COLOR, fontfamily='monospace')
    
    # Adaptive x-ticks for heatmap
    adaptive_xticks(ax2, n_ts, fig_width_inches=16)
    
    ax2.set_xlabel('Timestep', fontsize=11, color=TEXT_COLOR, fontfamily='monospace')
    ax2.set_title('ref vs test: log_10(relative difference) Heatmap',
                   fontsize=15, fontweight='bold', color=TEXT_COLOR,
                   fontfamily='monospace', pad=15)
    
    # Footnote: explain zero notation
    if zero_mask.any():
        fig2.text(0.5, 0.01,
                  '0 / |--- 0 ---| = bitwise identical (zero difference)',
                  fontsize=10, color='#0969da', ha='center', fontfamily='monospace')
    
    ax2.set_facecolor(PANEL_BG)
    ax2.tick_params(axis='both', colors=MUTED_TEXT)
    
    # Add thin grid lines for readability (only if not too dense)
    if n_ts <= 100:
        ax2.set_xticks(np.arange(-0.5, n_ts, 1), minor=True)
        ax2.set_yticks(np.arange(-0.5, n_vars_h, 1), minor=True)
        ax2.grid(which='minor', color=GRID_COLOR, linewidth=0.5, alpha=0.5)
        ax2.tick_params(which='minor', length=0)
    else:
        # Sparse grid at major ticks only
        ax2.set_yticks(np.arange(-0.5, n_vars_h, 1), minor=True)
        ax2.grid(which='minor', axis='y', color=GRID_COLOR, linewidth=0.5, alpha=0.5)
        ax2.tick_params(which='minor', length=0)
    
    cbar = plt.colorbar(im, ax=ax2, fraction=0.02, pad=0.02)
    cbar.set_label('log_10 (relative difference)', fontsize=10,
                    color=TEXT_COLOR, fontfamily='monospace')
    cbar.ax.tick_params(colors=MUTED_TEXT)
    cbar.ax.text(1.5, -14, 'better', fontsize=8, color=MUTED_TEXT,
                 fontfamily='monospace', va='center')
    cbar.ax.text(1.5, -1, 'worse', fontsize=8, color=MUTED_TEXT,
                 fontfamily='monospace', va='center')
    
    plt.tight_layout()
    # Asterisk footnote for heatmap
    has_multi = any(var_data[v]['vpt'] > 1 for v in vars_main)
    if has_multi:
        fig2.text(0.5, -0.01,
                  '* max of relative differences across mean/min/max stats at each timestep',
                  fontsize=9, color=MUTED_TEXT, ha='center', fontfamily='monospace',
                  fontstyle='italic')
    if _annotation:
        fig2.text(0.01, 0.002, _annotation, fontsize=7, color=MUTED_TEXT,
                  fontfamily='monospace', ha='left', va='bottom',
                  bbox=dict(boxstyle='round,pad=0.3', facecolor=PANEL_BG,
                            edgecolor=BORDER_COLOR, alpha=0.85))

    _heatmap_png = os.path.join(_output_dir, f'validation_heatmap_{_ts}.png')
    plt.savefig(_heatmap_png, dpi=150, facecolor=BG_COLOR,
                bbox_inches='tight', pad_inches=0.2)
    plt.close()
    print(f"Saved {_heatmap_png}")
    print(f"ARTIFACT: {_heatmap_png}")
