cd ~/plate_tool
cat > app.py <<'PY'
import streamlit as st
import numpy as np
import cv2
from PIL import Image
from streamlit_cropper import st_cropper
from streamlit_image_coordinates import streamlit_image_coordinates

ROWS = list("ABCDEFGHIJKLMNOP")
N_ROWS, N_COLS = 16, 24

st.set_page_config(page_title="384-well Picker (Crop + Click)", layout="wide")
st.title("384-well Empty-Well Picker")

uploaded = st.file_uploader("Upload plate photo", type=["jpg", "jpeg", "png"])
flip_h = st.checkbox("Flip horizontally (if mirrored)", value=True)

# -------------------------
# Session state
# -------------------------
if "selected" not in st.session_state:
    st.session_state["selected"] = set()
if "crop_locked" not in st.session_state:
    st.session_state["crop_locked"] = False
if "crop_np" not in st.session_state:
    st.session_state["crop_np"] = None
if "last_click" not in st.session_state:
    st.session_state["last_click"] = None
if "prev_flip_h" not in st.session_state:
    st.session_state["prev_flip_h"] = flip_h

# ✅ If flip changes, reset crop + selections (locked crop won't match flipped image)
if flip_h != st.session_state["prev_flip_h"]:
    st.session_state["prev_flip_h"] = flip_h
    st.session_state["crop_locked"] = False
    st.session_state["crop_np"] = None
    st.session_state["last_click"] = None
    st.session_state["selected"] = set()
    st.rerun()

# -------------------------
# Helpers
# -------------------------
def well_name(r, c):
    return f"{ROWS[r]}{c+1}"

def sorted_wells(wells):
    def key(w):
        return (ROWS.index(w[0]), int(w[1:]))
    return sorted(list(wells), key=key)

def toggle_well(r, c):
    w = well_name(r, c)
    if w in st.session_state["selected"]:
        st.session_state["selected"].remove(w)
    else:
        st.session_state["selected"].add(w)

def draw_grid_and_selected(img_bgr):
    out = img_bgr.copy()
    h, w = out.shape[:2]

    # grid lines
    for i in range(1, N_COLS):
        x = int(i * w / N_COLS)
        cv2.line(out, (x, 0), (x, h), (255, 255, 255), 1)
    for j in range(1, N_ROWS):
        y = int(j * h / N_ROWS)
        cv2.line(out, (0, y), (w, y), (255, 255, 255), 1)

    # selected wells
    for r in range(N_ROWS):
        for c in range(N_COLS):
            if well_name(r, c) in st.session_state["selected"]:
                x1 = int(c * w / N_COLS)
                x2 = int((c + 1) * w / N_COLS)
                y1 = int(r * h / N_ROWS)
                y2 = int((r + 1) * h / N_ROWS)
                cv2.rectangle(out, (x1, y1), (x2, y2), (0, 0, 255), 2)

    return out

def add_labels(img_bgr):
    h, w = img_bgr.shape[:2]
    pad_left, pad_top = 55, 45
    bg = (30, 30, 30)

    labeled = cv2.copyMakeBorder(
        img_bgr, pad_top, 0, pad_left, 0,
        cv2.BORDER_CONSTANT, value=bg
    )

    # Row letters A–P
    for r in range(N_ROWS):
        y = pad_top + int((r + 0.5) * h / N_ROWS)
        cv2.putText(
            labeled, ROWS[r], (10, y + 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
            (255, 255, 255), 2, cv2.LINE_AA
        )

    # Column numbers 1–24
    for c in range(N_COLS):
        x = pad_left + int((c + 0.5) * w / N_COLS)
        cv2.putText(
            labeled, str(c + 1), (x - 10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
            (255, 255, 255), 2, cv2.LINE_AA
        )

    return labeled, pad_left, pad_top

def map_click(x, y, w, h):
    col = int(x / w * N_COLS)
    row = int(y / h * N_ROWS)
    col = min(max(col, 0), N_COLS - 1)
    row = min(max(row, 0), N_ROWS - 1)
    return row, col

# -------------------------
# Main
# -------------------------
if not uploaded:
    st.stop()

img = Image.open(uploaded).convert("RGB")
img_np = np.array(img)

if flip_h:
    img_np = cv2.flip(img_np, 1)

# Resize for usability
MAX_W = 2200
h0, w0 = img_np.shape[:2]
if w0 > MAX_W:
    scale = MAX_W / w0
    img_np = cv2.resize(
        img_np,
        (int(w0 * scale), int(h0 * scale)),
        interpolation=cv2.INTER_AREA
    )

img_pil = Image.fromarray(img_np)

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Reset crop"):
        st.session_state["crop_locked"] = False
        st.session_state["crop_np"] = None
        st.session_state["last_click"] = None
        st.rerun()
with c2:
    if st.button("Clear selected"):
        st.session_state["selected"] = set()
        st.rerun()
with c3:
    st.caption("Crop → Lock crop → Click wells to toggle")

st.subheader("Step 1: Drag crop rectangle")
if not st.session_state["crop_locked"]:
    cropped_pil = st_cropper(
        img_pil,
        realtime_update=True,
        box_color="yellow",
        aspect_ratio=None,
        key=f"main_cropper_{flip_h}"
    )
    if st.button("Lock crop"):
        st.session_state["crop_np"] = np.array(cropped_pil)
        st.session_state["crop_locked"] = True
        st.session_state["last_click"] = None
        st.rerun()

if st.session_state["crop_np"] is None:
    st.stop()

# Cropped plate
crop_rgb = st.session_state["crop_np"]
crop_bgr = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
ch, cw = crop_bgr.shape[:2]

# Overlay grid + labels
overlay = draw_grid_and_selected(crop_bgr)
labeled, pad_left, pad_top = add_labels(overlay)
labeled_rgb = cv2.cvtColor(labeled, cv2.COLOR_BGR2RGB)

# 🔴 Big orientation warning
st.markdown(
    "<h2 style='color:red; text-align:center;'>MAKE SURE A1 IS AT TOP LEFT</h2>",
    unsafe_allow_html=True
)

st.subheader("Step 2: Click wells to toggle (A–P / 1–24 shown)")
display_w = min(labeled.shape[1], 1500)  # increase/decrease size on screen
scale_disp = labeled.shape[1] / display_w

coords = streamlit_image_coordinates(
    Image.fromarray(labeled_rgb),
    key="click_plate",
    width=display_w
)

if coords is not None:
    click_id = (int(coords["x"]), int(coords["y"]))
    if click_id != st.session_state["last_click"]:
        st.session_state["last_click"] = click_id

        x = float(coords["x"]) * scale_disp - pad_left
        y = float(coords["y"]) * scale_disp - pad_top

        if 0 <= x < cw and 0 <= y < ch:
            r, c = map_click(x, y, cw, ch)
            toggle_well(r, c)
            st.rerun()

# Output
st.subheader("Selected wells")
wells_list = sorted_wells(st.session_state["selected"])

st.markdown(f"### Total selected wells: {len(wells_list)}")
st.code(", ".join(wells_list) if wells_list else "None selected yet")

csv_text = "well\n" + "\n".join(wells_list) + "\n"
st.download_button(
    "Download CSV",
    csv_text.encode("utf-8"),
    file_name="empty_wells.csv",
    mime="text/csv"
)
PY
