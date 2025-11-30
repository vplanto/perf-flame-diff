import streamlit as st
import plotly.graph_objects as go

# 1. Page Configuration
st.set_page_config(page_title="FlameGraph Diff Tool", layout="wide")


# --- PARSER LOGIC ---
@st.cache_data
def parse_collapsed_data(content):
    """
    Parses 'collapsed stack' format: "func;func;func count"
    Returns:
      1. Hierarchical root for Plotly
      2. Flat map {path: count} for fast Diff calculation
      3. Total sample count
    """
    root = {"frame": "root", "value": 0, "children": {}}
    total_samples = 0
    flat_map = {}

    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            parts = line.rsplit(" ", 1)
            if len(parts) != 2:
                continue

            stack_str, count_str = parts
            count = float(count_str)
            total_samples += count

            frames = stack_str.split(";")

            # 1. Build Flat Map for Diffing
            # Key = "method/method/method" (full path)
            current_path = ""
            for frame in frames:
                if current_path:
                    current_path += "/" + frame
                else:
                    current_path = frame
                flat_map[current_path] = flat_map.get(current_path, 0) + count

            # 2. Build Tree for Visualization
            current = root
            current["value"] += count
            for frame in frames:
                if frame not in current["children"]:
                    current["children"][frame] = {
                        "frame": frame,
                        "value": 0,
                        "children": {},
                    }
                current = current["children"][frame]
                current["value"] += count

        except ValueError:
            continue

    return root, flat_map, total_samples


# --- FLATTENER & PRUNING ---
def flatten_tree_limited(node, total_samples, prune_percent, parent_id=""):
    """
    Flattens the tree into lists required by Plotly.
    Prunes nodes smaller than `prune_percent` to prevent browser crashes.
    """
    # Safety Pruning
    if total_samples > 0 and (node["value"] / total_samples * 100) < prune_percent:
        return [], [], [], [], []

    # Generate Unique ID based on path
    node_id = f"{parent_id}/{node['frame']}" if parent_id else node["frame"]

    ids = [node_id]
    labels = [node["frame"]]
    parents = [parent_id]
    values = [node["value"]]
    # Colors will be overwritten later based on Diff logic
    colors = ["#dddddd"]

    for child in node["children"].values():
        c_ids, c_labels, c_parents, c_values, _ = flatten_tree_limited(
            child, total_samples, prune_percent, node_id
        )
        ids.extend(c_ids)
        labels.extend(c_labels)
        parents.extend(c_parents)
        values.extend(c_values)
        colors.extend(["#dddddd"] * len(c_ids))

    return ids, labels, parents, values, colors


# --- UI LAYOUT ---
st.title("🔥 FlameGraph Diff Tool")

# Sidebar / Top Controls
col1, col2 = st.columns([1, 3])

with col1:
    st.subheader("1. Upload Data")
    st.caption("Upload `.txt` files generated with `asprof ... --collapsed`")
    file_a = st.file_uploader("Baseline (State A)", type=["txt"], key="a")
    file_b = st.file_uploader("Comparison (State B)", type=["txt"], key="b")

    st.divider()
    st.subheader("2. View Settings")

    chart_type = st.radio("Chart Visualization", ["Icicle (Recommended)", "Sunburst"])

    prune_val = st.slider(
        "Noise Filter (%)",
        0.1,
        5.0,
        1.0,
        0.1,
        help="Hides functions taking less than X% of CPU time. Helps performance.",
    )

    diff_threshold = st.slider(
        "Color Sensitivity",
        1,
        100,
        10,
        5,
        help="How many samples difference required to color Red/Green.",
    )

with col2:
    if file_a and file_b:
        with st.spinner("Processing profiles..."):
            # A. Parse Files
            content_a = file_a.getvalue().decode("utf-8")
            content_b = file_b.getvalue().decode("utf-8")

            root_a, map_a, total_a = parse_collapsed_data(content_a)
            root_b, map_b, total_b = parse_collapsed_data(content_b)

            # Show global delta
            delta_samples = total_b - total_a
            delta_color = "inverse" if delta_samples > 0 else "normal"

            # FIX: Використовуємо правильний параметр delta_color
            st.metric(
                "Total CPU Samples (B vs A)",
                f"{total_b:,.0f}",
                f"{delta_samples:+,.0f}",
                delta_color=delta_color,
            )

            # B. Prepare Visualization Data (Based on B)
            ids, labels, parents, values, _ = flatten_tree_limited(
                root_b, total_b, prune_val
            )

            # C. Calculate Diffs (The Logic)
            final_colors = []
            hover_texts = []

            for i, nid in enumerate(ids):
                val_b = values[i]

                # Cleanup ID to match Map keys (remove root prefix)
                lookup_key = nid
                if nid.startswith("root/"):
                    lookup_key = nid.replace("root/", "", 1)
                elif nid == "root":
                    lookup_key = "root"

                val_a = map_a.get(lookup_key, 0)
                diff = val_b - val_a

                # Color Logic
                if diff > diff_threshold:
                    final_colors.append("rgba(255, 65, 54, 0.9)")  # Red (Regression)
                elif diff < -diff_threshold:
                    final_colors.append("rgba(46, 204, 64, 0.9)")  # Green (Improvement)
                else:
                    final_colors.append("#eeeeee")  # Grey (Stable)

                # Tooltip
                hover_texts.append(
                    f"<b>{labels[i]}</b><br>"
                    + f"Samples (New): {val_b:,.0f}<br>"
                    + f"Samples (Old): {val_a:,.0f}<br>"
                    + f"Diff: <b>{diff:+,.0f}</b>"
                )

            # D. Render Chart
            if len(ids) > 0:
                # Instructions Expander
                with st.expander("📖 How to read this chart (English)", expanded=True):
                    st.markdown(
                        """
                    **Chart Basics (Icicle View):**
                    * **Y-Axis (Height):** Stack Depth. The top bar is the root, moving down to specific functions.
                    * **X-Axis (Width):** CPU Usage in the **New State (B)**. Wider bars = more time spent.
                    
                    **Color Coding (The Diff):**
                    * 🔴 **RED (Regression):** This function is significantly **slower** (or called more often) in State B than in State A.
                    * 🟢 **GREEN (Improvement):** This function is **faster** (or called less often) in State B.
                    * ⚪ **GREY (Stable):** Performance is roughly the same.
                    
                    **Analysis Strategy:**
                    1.  Look for wide **RED** blocks at the bottom of the stack. These are your new bottlenecks.
                    2.  Hover over them to see the exact `Diff` value (samples count).
                    """
                    )

                # Determine Chart Class
                ChartClass = (
                    go.Icicle if chart_type.startswith("Icicle") else go.Sunburst
                )

                # Handle specific args (Sunburst doesn't support 'tiling')
                chart_kwargs = {}
                if ChartClass == go.Icicle:
                    chart_kwargs["tiling"] = dict(orientation="v")

                fig = go.Figure(
                    ChartClass(
                        ids=ids,
                        labels=labels,
                        parents=parents,
                        values=values,
                        branchvalues="total",
                        marker=dict(colors=final_colors),
                        hovertext=hover_texts,
                        hoverinfo="text",
                        **chart_kwargs,
                    )
                )

                fig.update_layout(
                    margin=dict(t=10, l=0, r=0, b=0),
                    height=900,
                    uniformtext=dict(minsize=8, mode="hide"),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(
                    f"No data visible. Try reducing the Noise Filter (currently {prune_val}%)."
                )

    else:
        st.info("👋 Upload both `.txt` files to start comparison.")
