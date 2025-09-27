# order_app_sqlite.py
# Streamlit app (Tiếng Việt) - Quản lý đơn hàng + nhắc (reminder)
import streamlit as st
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
from io import BytesIO

import os
DB_FILE = os.path.join(os.path.dirname(__file__), "orders.db")
REMINDER_DAYS = [9, 7, 5, 3]  # danh sách ngày sẽ nhắc trước hạn

# -------------------------
# Database helpers
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # tạo bảng nếu chưa có
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT,
        name TEXT,
        start_date TEXT,
        lead_time INTEGER,
        expected_date TEXT,
        delivered_date TEXT,
        status TEXT,
        notes TEXT,
        created_at TEXT,
        package_info TEXT
    )
    """)
    conn.commit()
    # kiểm tra và auto add missing columns nếu DB cũ
    cur.execute("PRAGMA table_info(orders)")
    existing_cols = [r[1] for r in cur.fetchall()]
    needed = {
        "order_code":"TEXT", "name":"TEXT", "start_date":"TEXT", "lead_time":"INTEGER",
        "expected_date":"TEXT","delivered_date":"TEXT","status":"TEXT","notes":"TEXT",
        "created_at":"TEXT","package_info":"TEXT"
    }
    for col, coltype in needed.items():
        if col not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE orders ADD COLUMN {col} {coltype}")
            except Exception:
                pass
    conn.commit()
    conn.close()

def add_order_db(order_code, name, start_date_str, lead_time_int, notes="", package_info=""):
    conn = get_conn()
    cur = conn.cursor()
    expected = (datetime.strptime(start_date_str, "%Y-%m-%d") + timedelta(days=int(lead_time_int))).strftime("%Y-%m-%d")
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO orders (order_code, name, start_date, lead_time, expected_date, delivered_date, status, notes, created_at, package_info)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_code, name, start_date_str, int(lead_time_int), expected, None, "Đang sản xuất", notes, created, package_info))
    conn.commit()
    conn.close()

def get_orders_df():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", conn)
    conn.close()
    if not df.empty:
        for col in ["start_date", "expected_date", "delivered_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return df

def update_order_db(order_id, order_code, name, start_date_str, lead_time_int, notes, package_info=""):
    conn = get_conn()
    cur = conn.cursor()
    expected = (datetime.strptime(start_date_str, "%Y-%m-%d") + timedelta(days=int(lead_time_int))).strftime("%Y-%m-%d")
    cur.execute("""
        UPDATE orders SET order_code=?, name=?, start_date=?, lead_time=?, expected_date=?, notes=?, package_info=? WHERE id=?
    """, (order_code, name, start_date_str, int(lead_time_int), expected, notes, package_info, order_id))
    conn.commit()
    conn.close()

def delete_order_db(order_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE id=?", (order_id,))
    conn.commit()
    conn.close()

def mark_delivered_db(order_id, delivered_date_str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT expected_date FROM orders WHERE id=?", (order_id,))
    r = cur.fetchone()
    if not r or not r[0]:
        conn.close()
        return False, "Không tìm thấy ngày dự kiến để so sánh."
    expected = datetime.strptime(r[0], "%Y-%m-%d").date()
    try:
        delivered = datetime.strptime(delivered_date_str, "%Y-%m-%d").date()
    except Exception:
        conn.close()
        return False, "Sai định dạng ngày (phải YYYY-MM-DD)."
    delta = (delivered - expected).days
    if delta == 0:
        status = "✅ Đã giao đúng hẹn"
    elif delta > 0:
        status = f"🚨 Đã giao trễ {delta} ngày"
    else:
        status = f"⏱️ Đã giao sớm {-delta} ngày"
    cur.execute("UPDATE orders SET delivered_date=?, status=? WHERE id=?", (delivered_date_str, status, order_id))
    conn.commit()
    conn.close()
    return True, status

# -------------------------
# Reminders (nhắc)
# -------------------------
def build_reminders():
    """Trả về list các chuỗi nhắc cho orders chưa delivered"""
    df = get_orders_df()
    today = date.today()
    msgs = []
    if df.empty:
        return msgs
    df_pending = df[df['delivered_date'].isna()]
    for _, row in df_pending.iterrows():
        if pd.isna(row['expected_date']):
            continue
        expected = row['expected_date'].date()
        days_left = (expected - today).days
        if days_left < 0:
            msgs.append(f"⚠️ [TRỄ] {row['name']} (ID:{row['id']}) đã trễ {-days_left} ngày (dự kiến {expected})")
        elif days_left == 0:
            msgs.append(f"🚨 [HÔM NAY] {row['name']} (ID:{row['id']}) đến hạn hôm nay ({expected})")
        elif days_left in REMINDER_DAYS:
            msgs.append(f"🔔 [SẮP ĐẾN HẠN - {days_left} ngày] {row['name']} (ID:{row['id']}) dự kiến {expected}")
    return msgs

# -------------------------
# Export Excel
# -------------------------
def export_df_to_excel_bytes(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="orders")
        writer.save()
    return output.getvalue()

# -------------------------
# Utility functions for UI
# -------------------------
def format_df_for_display(df):
    if df.empty:
        return df
    out = df.copy()
    for c in ["start_date", "expected_date", "delivered_date"]:
        if c in out.columns:
            out[c] = out[c].dt.strftime("%Y-%m-%d")
    # compute delta if delivered
    def compute_delta(row):
        if pd.isna(row.get("delivered_date")) or pd.isna(row.get("expected_date")):
            return ""
        try:
            d = (pd.to_datetime(row["delivered_date"]).date() - pd.to_datetime(row["expected_date"]).date()).days
            return d
        except:
            return ""
    out["delta_days"] = out.apply(compute_delta, axis=1)
    return out

# -------------------------
# Init DB
# -------------------------
init_db()

# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title="Quản lý Đơn hàng - Nhắc nhở", layout="wide")
st.title("📦 Quản lý Đơn hàng (Foxrun) — có Nhắc (3/5/7/9 ngày)")

menu = st.sidebar.selectbox("Chọn chức năng", [
    "Thêm đơn mới",
    "Danh sách & Quản lý",
    "Cập nhật / Đánh dấu giao",
    "Nhắc nhở (Reminders)",
    "Thống kê & Xuất"
])

# -------------------------
# 1) Thêm đơn mới
# -------------------------
if menu == "Thêm đơn mới":
    st.header("➕ Thêm đơn mới")
    with st.form("form_add"):
        col1, col2 = st.columns(2)
        with col1:
            customer_name = st.text_input("Tên khách hàng", max_chars=100)
            product_name = st.text_input("Tên sản phẩm", max_chars=150)
            quantity = st.number_input("Số lượng", min_value=1, value=1, step=1)
            price_cny = st.number_input("Giá nhập (CNY) / 1 sp", min_value=0.0, value=0.0, format="%.4f")
            package_info = st.text_input("Kích thước / Cân nặng / Số kiện (nhà máy báo)", max_chars=200)
        with col2:
            start_date = st.date_input("Ngày bắt đầu (xưởng bắt tay làm)", value=date.today())
            first_payment_date = st.date_input("Ngày thanh toán lần đầu (nếu có)", value=None)
            production_days = st.number_input("Số ngày sản xuất", min_value=0, value=30, step=1)
            notes = st.text_area("Ghi chú", height=80)

        submitted = st.form_submit_button("Lưu đơn hàng")
        if submitted:
            if not customer_name or not product_name:
                st.error("Vui lòng nhập tên khách hàng và tên sản phẩm.")
            else:
                start_str = start_date.strftime("%Y-%m-%d") if start_date else None
                fp_str = first_payment_date.strftime("%Y-%m-%d") if first_payment_date else None
                order_code = f"OD{int(datetime.now().timestamp())}"
                add_order_db(order_code, f"{customer_name} - {product_name}", start_str, production_days, notes, package_info)
                expected = (datetime.strptime(start_str, "%Y-%m-%d") + timedelta(days=int(production_days))).strftime("%Y-%m-%d")
                st.success(f"Đã lưu đơn {order_code}. Ngày dự kiến: {expected}")

# -------------------------
# 2) Danh sách & Quản lý
# -------------------------
elif menu == "Danh sách & Quản lý":
    st.header("📋 Danh sách đơn hàng")
    df = get_orders_df()
    if df.empty:
        st.info("Chưa có đơn hàng.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            start_filter = st.date_input("Lọc từ ngày dự kiến (từ)", value=(date.today() - timedelta(days=30)))
        with col2:
            end_filter = st.date_input("Lọc đến ngày dự kiến (đến)", value=(date.today() + timedelta(days=30)))
        mask = (df['expected_date'].dt.date >= start_filter) & (df['expected_date'].dt.date <= end_filter)
        filtered = df[mask].copy()

        all_status = filtered['status'].fillna("Chưa xác định").unique().tolist()
        chosen = st.multiselect("Lọc theo trạng thái", options=all_status, default=all_status)
        filtered = filtered[filtered['status'].fillna("Chưa xác định").isin(chosen)]

        display = format_df_for_display(filtered)
        st.dataframe(display[["id","order_code","name","start_date","lead_time","expected_date","delivered_date","status","delta_days","notes","package_info"]], use_container_width=True)

        opts = [f"{row['id']} - {row['name']}" for _, row in filtered.iterrows()]
        if opts:
            sel = st.selectbox("Chọn đơn để Sửa / Xóa", options=opts)
            sel_id = int(sel.split(" - ")[0])
            sel_row = df[df["id"]==sel_id].iloc[0]

            st.subheader("✏️ Sửa đơn")
            with st.form("edit_form"):
                new_code = st.text_input("Mã đơn", sel_row.get("order_code",""))
                new_name = st.text_input("Tên đơn", sel_row.get("name",""))
                new_start = st.date_input("Ngày bắt đầu", sel_row["start_date"].date() if pd.notna(sel_row["start_date"]) else date.today())
                new_lead = st.number_input("Số ngày sản xuất", min_value=1, value=int(sel_row.get("lead_time") or 7))
                new_notes = st.text_area("Ghi chú", sel_row.get("notes","") or "")
                new_package = st.text_input("Kích thước / Cân nặng / Số kiện (nhà máy báo)", sel_row.get("package_info","") or "")
                save = st.form_submit_button("Lưu thay đổi")
            if save:
                update_order_db(
                    sel_id,
                    new_code.strip(),
                    new_name.strip(),
                    new_start.strftime("%Y-%m-%d"),
                    int(new_lead),
                    new_notes.strip(),
                    (new_package or "").strip()
                )
                st.success("✅ Đã cập nhật.")
                st.rerun()

            if st.checkbox("Tôi muốn xoá đơn này"):
                if st.button("Xóa vĩnh viễn"):
                    delete_order_db(sel_id)
                    st.warning("🗑️ Đã xóa đơn.")
                    st.rerun()

# -------------------------
# 3) Cập nhật / Đánh dấu giao
# -------------------------
elif menu == "Cập nhật / Đánh dấu giao":
    st.header("🚚 Cập nhật / Đánh dấu đã giao")
    df = get_orders_df()
    pending = df[df['delivered_date'].isna()] if not df.empty else pd.DataFrame()
    if pending.empty:
        st.info("Không có đơn chờ giao (tất cả đã có ngày giao).")
    else:
        opts = [f"{row['id']} - {row['name']} (dự kiến {row['expected_date'].strftime('%Y-%m-%d')})" for _, row in pending.iterrows()]
        sel = st.selectbox("Chọn đơn để cập nhật ngày giao", opts)
        sel_id = int(sel.split(" - ")[0])
        default_date = date.today()
        delivered = st.date_input("Ngày giao thực tế", default_date)
        if st.button("Xác nhận đã giao"):
            ok, msg = mark_delivered_db(sel_id, delivered.strftime("%Y-%m-%d"))
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(msg)
            st.rerun()

# -------------------------
# 4) Nhắc nhở (Reminders)
# -------------------------
elif menu == "Nhắc nhở (Reminders)":
    st.header("🔔 Nhắc nhở đơn hàng sắp đến hạn")
    msgs = build_reminders()
    if not msgs:
        st.success("Không có đơn cần nhắc hôm nay.")
    else:
        st.write(f"🔔 Có {len(msgs)} thông báo:")
        for m in msgs:
            st.write("-", m)
        if st.button("Xuất danh sách nhắc (Excel)"):
            df = get_orders_df()
            today = date.today()
            df_pending = df[df['delivered_date'].isna()].copy()
            df_pending['days_left'] = df_pending['expected_date'].dt.date.apply(lambda d: (d - today).days)
            df_remind = df_pending[df_pending['days_left'].isin(REMINDER_DAYS + [0]) | (df_pending['days_left'] < 0)]
            bytes_xlsx = export_df_to_excel_bytes(format_df_for_display(df_remind))
            st.download_button("📥 Tải file nhắc.xlsx", data=bytes_xlsx, file_name="reminders.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# -------------------------
# 5) Thống kê & Xuất
# -------------------------
elif menu == "Thống kê & Xuất":
    st.header("📊 Thống kê tổng quan")
    df = get_orders_df()
    if df.empty:
        st.info("Chưa có dữ liệu để thống kê.")
    else:
        total = len(df)
        delivered_mask = df['delivered_date'].notna()
        pending = df['delivered_date'].isna().sum()
        on_time = df[delivered_mask & df['status'].str.contains("Đã giao đúng hẹn", na=False)].shape[0]
        late = df[delivered_mask & df['status'].str.contains("trễ", na=False)].shape[0]
        early = df[delivered_mask & df['status'].str.contains("sớm", na=False)].shape[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng đơn", total)
        c2.metric("Đã giao", int(delivered_mask.sum()))
        c3.metric("Đang sản xuất", int(pending))
        c4.metric("Giao trễ", int(late))

        labels = ["Đúng hẹn", "Trễ", "Sớm", "Chưa giao"]
        counts = [on_time, late, early, pending]
        fig, ax = plt.subplots()
        ax.pie(counts, labels=labels, autopct="%1.1f%%", startangle=90)
        ax.axis("equal")
        st.pyplot(fig)

        df_display = format_df_for_display(df)
        st.subheader("Chi tiết đơn hàng")
        st.dataframe(df_display[["id","order_code","name","start_date","lead_time","expected_date","delivered_date","delta_days","status","notes","package_info"]], use_container_width=True)

        if st.button("Xuất toàn bộ báo cáo (Excel)"):
            bytes_xlsx = export_df_to_excel_bytes(df_display)
            st.download_button("📥 Tải báo cáo.xlsx", data=bytes_xlsx, file_name="bao_cao_don_hang.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.info("Lưu ý: bạn có thể dùng tab 'Nhắc nhở' để xuất danh sách cần follow up.")
