# order_app_supabase.py
# Streamlit app (Tiếng Việt) - Quản lý đơn hàng + nhắc (reminder) with Supabase backend

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
from io import BytesIO
import os

# -------------------------
# Helpers
# -------------------------
def format_df_for_display(df):
    """Chuẩn hóa DataFrame để hiển thị trên Streamlit"""
    if df is None or df.empty:
        return df
    df_display = df.copy()
    for col in df_display.columns:
        try:
            if str(df_display[col].dtype).startswith("datetime"):
                df_display[col] = df_display[col].dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return df_display

def export_df_to_excel_bytes(df):
    """Xuất DataFrame thành file Excel bytes để tải về"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if df is None:
            pd.DataFrame().to_excel(writer, index=False, sheet_name="Orders")
        else:
            df.to_excel(writer, index=False, sheet_name="Orders")
    return output.getvalue()

# supabase client
try:
    from supabase import create_client
except Exception as e:
    raise RuntimeError("Thiếu package 'supabase'. Cài: pip install supabase") from e

# -------------------------
# Cấu hình Supabase
# -------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Thiếu cấu hình Supabase. Thiết lập SUPABASE_URL và SUPABASE_KEY.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

DB_TABLE = "orders"
REMINDER_RANGE = 7  # số ngày trước hạn cần nhắc liên tục

# -------------------------
# Database helpers
# -------------------------
def row_to_df(records):
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    for c in ["start_date", "expected_date", "delivered_date", "created_at"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df

def get_orders_df():
    try:
        res = supabase.table(DB_TABLE).select("*").order("id", desc=True).execute()
        return row_to_df(res.data)
    except Exception as e:
        st.error(f"Lỗi khi lấy danh sách đơn: {e}")
        return pd.DataFrame()

def load_orders():
    return get_orders_df()

def add_order_db(order_code, name, start_date_str, lead_time_int, notes="", package_info="",
                 quantity=1, price_cny=0.0, deposit_amount=0.0):
    """Insert a new order into Supabase table."""
    try:
        # Tính toán
        total_cny = float(price_cny) * int(quantity)
        deposit_ratio = (float(deposit_amount) / total_cny * 100) if total_cny > 0 else 0

        expected = None
        if start_date_str:
            try:
                expected = (datetime.strptime(start_date_str, "%Y-%m-%d") +
                            timedelta(days=int(lead_time_int))).date().isoformat()
            except Exception:
                expected = None

        created = datetime.utcnow().isoformat()
        payload = {
            "order_code": order_code,
            "name": name,
            "start_date": start_date_str,
            "lead_time": int(lead_time_int) if lead_time_int is not None else None,
            "expected_date": expected,
            "delivered_date": None,
            "status": "Đang sản xuất",
            "notes": notes,
            "created_at": created,
            "package_info": package_info,
            "quantity": int(quantity),
            "price_cny": float(price_cny),
            "total_cny": total_cny,
            "deposit_amount": float(deposit_amount),
            "deposit_ratio": deposit_ratio
        }
        res = supabase.table(DB_TABLE).insert(payload).execute()
        return res.data
    except Exception as e:
        raise RuntimeError(f"Supabase insert error: {e}")


def update_order_db(order_id, order_code, name, start_date_str, lead_time_int,
                    notes, package_info="",
                    quantity=1, price_cny=0.0, deposit_amount=0.0):
    """Update an order by id."""
    try:
        total_cny = float(price_cny) * int(quantity)
        deposit_ratio = (float(deposit_amount) / total_cny * 100) if total_cny > 0 else 0

        expected = None
        if start_date_str:
            try:
                expected = (datetime.strptime(start_date_str, "%Y-%m-%d") +
                            timedelta(days=int(lead_time_int))).date().isoformat()
            except Exception:
                expected = None

        payload = {
            "order_code": order_code,
            "name": name,
            "start_date": start_date_str,
            "lead_time": int(lead_time_int) if lead_time_int is not None else None,
            "expected_date": expected,
            "notes": notes,
            "package_info": package_info,
            "quantity": int(quantity),
            "price_cny": float(price_cny),
            "total_cny": total_cny,
            "deposit_amount": float(deposit_amount),
            "deposit_ratio": deposit_ratio
        }
        res = supabase.table(DB_TABLE).update(payload).eq("id", int(order_id)).execute()
        return res.data
    except Exception as e:
        raise RuntimeError(f"Supabase update error: {e}")

def delete_order_db(order_id):
    try:
        res = supabase.table(DB_TABLE).delete().eq("id", int(order_id)).execute()
        return res.data
    except Exception as e:
        raise RuntimeError(f"Lỗi delete: {e}")

def mark_delivered_db(order_id, delivered_date_str):
    try:
        r = supabase.table(DB_TABLE).select("expected_date").eq("id", int(order_id)).single().execute()
        if not r.data or r.data.get("expected_date") is None:
            return False, "Không tìm thấy ngày dự kiến."
        expected = pd.to_datetime(r.data.get("expected_date")).date()
        delivered = datetime.strptime(delivered_date_str, "%Y-%m-%d").date()
        delta = (delivered - expected).days
        if delta == 0:
            status = "✅ Đã giao đúng hẹn"
        elif delta > 0:
            status = f"🚨 Trễ {delta} ngày"
        else:
            status = f"⏱️ Sớm {-delta} ngày"
        payload = {"delivered_date": delivered_date_str, "status": status}
        supabase.table(DB_TABLE).update(payload).eq("id", int(order_id)).execute()
        return True, status
    except Exception as e:
        return False, f"Lỗi mark delivered: {e}"

# -------------------------
# Reminders (đã chỉnh sửa)
# -------------------------
def build_reminders():
    """
    Trả về danh sách thông báo:
    - Nhắc mỗi ngày nếu còn 0–7 ngày tới hạn.
    - Nhắc cả các đơn đã quá hạn chưa giao, kèm số ngày trễ.
    """
    df = get_orders_df()
    today = date.today()
    msgs = []
    if df.empty:
        return msgs
    df["expected_date"] = pd.to_datetime(df["expected_date"], errors="coerce")
    df["delivered_date"] = pd.to_datetime(df["delivered_date"], errors="coerce")
    df_pending = df[df["delivered_date"].isna()]
    for _, row in df_pending.iterrows():
        if pd.isna(row["expected_date"]):
            continue
        expected = row["expected_date"].date()
        days_left = (expected - today).days
        if days_left < 0:
            msgs.append(
                f"⚠️ Đơn **{row['name']}** (ID:{row['id']}) đã trễ **{-days_left} ngày** so với hẹn {expected}"
            )
        elif 0 <= days_left <= REMINDER_RANGE:
            if days_left == 0:
                msgs.append(
                    f"🚨 Hôm nay đến hạn giao đơn **{row['name']}** (ID:{row['id']}) — hẹn {expected}"
                )
            else:
                msgs.append(
                    f"🔔 Còn **{days_left} ngày** đến hạn giao đơn **{row['name']}** (ID:{row['id']}) — hẹn {expected}"
                )
    return msgs

# -------------------------
# UI
# -------------------------
st.set_page_config(page_title="Quản lý Đơn hàng", layout="wide")
st.title("📦 Quản lý Đơn hàng Foxrun")

menu = st.sidebar.selectbox("Chọn chức năng", [
    "Thêm đơn mới",
    "Danh sách & Quản lý",
    "Cập nhật / Đánh dấu giao",
    "Nhắc nhở (Reminders)",
    "Thống kê & Xuất"
])

# --- Flash message placeholder ---
flash = st.empty()
if "flash_msg" in st.session_state:
    msg, level = st.session_state.pop("flash_msg")
    if level == "success":
        flash.success(msg)
    elif level == "error":
        flash.error(msg)
    elif level == "warning":
        flash.warning(msg)
    else:
        flash.info(msg)

# 1) Thêm đơn mới
if menu == "Thêm đơn mới":
    st.header("➕ Thêm đơn mới")
    with st.form("form_add"):
        col1, col2 = st.columns(2)
        with col1:
            customer_name = st.text_input("Tên khách hàng", max_chars=100)
            product_name = st.text_input("Tên sản phẩm", max_chars=150)
            quantity = st.number_input("Số lượng", min_value=0.0, value=1.0, step=0.1, format="%.2f")
            price_cny = st.number_input("Giá nhập (CNY) / 1 sp", min_value=0.0, value=0.0, format="%.2f")
            deposit_amount = st.number_input("Tiền đặt cọc (CNY)", min_value=0.0, value=0.0, format="%.2f")
            package_info = st.text_input("Kích thước / Cân nặng / Số kiện (nhà máy báo)", max_chars=200)
        with col2:
            start_date = st.date_input("Ngày bắt đầu (xưởng bắt tay làm)", value=date.today())
            first_payment_date = st.date_input("Ngày thanh toán lần đầu (nếu có)", value=None)
            production_days = st.number_input("Số ngày sản xuất", min_value=0, value=30, step=1)
            notes = st.text_area("Ghi chú", height=80)

        # Tính toán hiển thị
        total_cny = price_cny * quantity
        deposit_ratio = (deposit_amount / total_cny * 100) if total_cny > 0 else 0
        st.markdown(f"**💰 Tổng tiền (CNY):** {total_cny:.2f}")
        st.markdown(f"**📊 Tỷ lệ đặt cọc:** {deposit_ratio:.1f}%")

        submitted = st.form_submit_button("Lưu đơn hàng")
        if submitted:
            if not customer_name or not product_name:
                st.error("❌ Vui lòng nhập tên khách hàng và tên sản phẩm.")
            elif quantity <= 0:
                st.error("❌ Vui lòng nhập Số lượng lớn hơn 0.")
            elif price_cny <= 0:
                st.error("❌ Vui lòng nhập Giá nhập (CNY) lớn hơn 0.")
            else:
                start_str = start_date.strftime("%Y-%m-%d") if start_date else None
                order_code = f"OD{int(datetime.utcnow().timestamp())}"
                try:
                    add_order_db(order_code, f"{customer_name} - {product_name}", start_str,
                                 production_days, notes, package_info,
                                 quantity, price_cny, deposit_amount)
                    expected = ""
                    try:
                        expected = (datetime.strptime(start_str, "%Y-%m-%d") +
                                    timedelta(days=int(production_days))).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                    st.success(f"✅ Đã lưu đơn {order_code}. Ngày dự kiến: {expected}")
                except Exception as e:
                    st.error(f"❌ Lỗi khi lưu đơn: {e}")


# -------------------------
# 2) Danh sách & Quản lý
# -------------------------
elif menu == "Danh sách & Quản lý":
    st.header("📋 Danh sách đơn hàng")
    df = get_orders_df()
    if df.empty:
        st.info("Chưa có đơn hàng.")
    else:
        if "expected_date" in df.columns:
            df["expected_date"] = pd.to_datetime(df["expected_date"], errors="coerce")
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
        show_cols = [
            "id","order_code","name","quantity","price_cny","total_cny",
            "deposit_amount","deposit_ratio","start_date","lead_time",
            "expected_date","delivered_date","status","delta_days",
            "notes","package_info"
        ]
        show_cols = [c for c in show_cols if c in display.columns]

        # 🔑 ĐỔI TÊN CỘT SANG TIẾNG VIỆT
        vietnamese_cols = {
            "id": "STT",
            "order_code": "Mã đơn",
            "name": "Tên khách",
            "quantity": "Số lượng",
            "price_cny": "Giá nhập (CNY)",
            "total_cny": "Tổng tiền (CNY)",
            "deposit_amount": "Tiền đặt cọc (CNY)",
            "deposit_ratio": "Đặt cọc (%)",
            "start_date": "Ngày bắt đầu",
            "lead_time": "Số ngày SX",
            "expected_date": "Ngày dự kiến giao",
            "delivered_date": "Ngày giao thực tế",
            "status": "Trạng thái",
            "delta_days": "Chênh lệch ngày",
            "notes": "Ghi chú",
            "package_info": "Thông tin kiện hàng"
        }

        display_renamed = display[show_cols].rename(columns=vietnamese_cols)
        st.dataframe(display_renamed, use_container_width=True)

        # ------ Chọn đơn để sửa / xóa ------
        opts = [f"{row['id']} - {row['name']}" for _, row in filtered.iterrows()]
        if opts:
            sel = st.selectbox("Chọn đơn để Sửa / Xóa", options=opts)
            sel_id = int(sel.split(" - ")[0])
            sel_row = df[df["id"]==sel_id].iloc[0]

            st.subheader("✏️ Sửa đơn")
            with st.form(key=f"edit_form_{sel_id}"):
                new_code = st.text_input("Mã đơn", sel_row.get("order_code",""))
                new_name = st.text_input("Tên KH - SP", sel_row.get("name",""))
                try:
                    start_dt = pd.to_datetime(sel_row.get("start_date"), errors="coerce")
                    start_default = start_dt.date() if pd.notna(start_dt) else date.today()
                except Exception:
                    start_default = date.today()
                new_start = st.date_input("Ngày bắt đầu", start_default)
                new_lead = st.number_input("Số ngày sản xuất", min_value=0,
                                           value=int(sel_row.get("lead_time") or 0), step=1)
                new_quantity = st.number_input("Số lượng", min_value=1.0,
                                               value=float(sel_row.get("quantity") or 1.0), step=0.1, format="%.2f")
                new_price = st.number_input("Giá nhập (CNY) / 1 sp", min_value=0.0,
                                            value=float(sel_row.get("price_cny") or 0.0), format="%.2f")
                new_deposit = st.number_input("Tiền đặt cọc (CNY)", min_value=0.0,
                                              value=float(sel_row.get("deposit_amount") or 0.0), format="%.2f")
                new_notes = st.text_area("Ghi chú", sel_row.get("notes","") or "")
                new_package = st.text_area("Kích thước / Cân nặng / Số kiện (nhà máy báo)",
                                           sel_row.get("package_info","") or "")
                save = st.form_submit_button("Lưu thay đổi")

                if save:
                    try:
                        update_order_db(
                            sel_id,
                            (new_code or "").strip(),
                            (new_name or "").strip(),
                            new_start.strftime("%Y-%m-%d"),
                            int(new_lead),
                            (new_notes or "").strip(),
                            (new_package or "").strip(),
                            new_quantity, new_price, new_deposit
                        )
                        st.success("✅ Đã cập nhật đơn.")
                    except Exception as e:
                        st.error(f"❌ Lỗi khi cập nhật: {e}")

            st.subheader("🗑️ Xóa đơn")
            if st.button("❌ Xóa đơn này"):
                try:
                    delete_order_db(sel_id)
                    st.success("🗑️ Đã xóa đơn.")
                except Exception as e:
                    st.error(f"❌ Lỗi khi xóa: {e}")
        else:
            st.info("Không có đơn để sửa hoặc xóa.")

# 3) Cập nhật / Đánh dấu giao
elif menu == "Cập nhật / Đánh dấu giao":
    st.header("🚚 Cập nhật / Đánh dấu đã giao")
    df = get_orders_df()
    pending = df[df['delivered_date'].isna()] if (not df.empty and "delivered_date" in df.columns) else pd.DataFrame()
    if pending.empty:
        st.info("Không có đơn chờ giao (tất cả đã có ngày giao).")
    else:
        opts = [f"{row['id']} - {row['name']} (dự kiến {pd.to_datetime(row['expected_date']).strftime('%Y-%m-%d') if not pd.isna(row.get('expected_date')) else '??'})" for _, row in pending.iterrows()]
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
            
# 4) Nhắc nhở (Reminders)
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
            df_all = get_orders_df()
            if not df_all.empty and "expected_date" in df_all.columns:
                df_all['expected_date'] = pd.to_datetime(df_all['expected_date'], errors='coerce')
                df_pending = df_all[df_all['delivered_date'].isna()] if "delivered_date" in df_all.columns else df_all.copy()
                today = date.today()
                df_pending['days_left'] = df_pending['expected_date'].dt.date.apply(lambda d: (d - today).days)
                df_remind = df_pending[df_pending['days_left'].isin(REMINDER_DAYS + [0]) | (df_pending['days_left'] < 0)]
            else:
                df_remind = pd.DataFrame()
            bytes_xlsx = export_df_to_excel_bytes(format_df_for_display(df_remind))
            st.download_button("📥 Tải file nhắc.xlsx", data=bytes_xlsx, file_name="reminders.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# 5) Thống kê & Xuất
elif menu == "Thống kê & Xuất":
    st.header("📊 Thống kê tổng quan")
    df = get_orders_df()
    if df.empty:
        st.info("Chưa có dữ liệu để thống kê.")
    else:
        total = len(df)
        delivered_mask = df['delivered_date'].notna() if "delivered_date" in df.columns else pd.Series([], dtype=bool)
        pending = int(df['delivered_date'].isna().sum()) if "delivered_date" in df.columns else total
        on_time = df[delivered_mask & df['status'].str.contains("Đã giao đúng hẹn", na=False)].shape[0] if "status" in df.columns else 0
        late = df[delivered_mask & df['status'].str.contains("trễ", na=False)].shape[0] if "status" in df.columns else 0
        early = df[delivered_mask & df['status'].str.contains("sớm", na=False)].shape[0] if "status" in df.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng đơn", total)
        c2.metric("Đã giao", int(delivered_mask.sum()) if hasattr(delivered_mask, "sum") else 0)
        c3.metric("Đang sản xuất", int(pending))
        c4.metric("Giao trễ", int(late))

        labels = ["Đúng hẹn", "Trễ", "Sớm", "Chưa giao"]
        counts = [on_time, late, early, pending]
        fig, ax = plt.subplots()
        ax.pie(counts, labels=labels, autopct="%1.1f%%", startangle=90)
        ax.axis("equal")
        st.pyplot(fig)

        # Hiển thị chi tiết và xuất
        df_display = format_df_for_display(df)
        st.subheader("Chi tiết đơn hàng")
        show_cols = ["id","order_code","name","start_date","lead_time","expected_date",
                     "delivered_date","delta_days","status","notes","package_info"]
        show_cols = [c for c in show_cols if c in df_display.columns]
        st.dataframe(df_display[show_cols], use_container_width=True)

        if st.button("Xuất toàn bộ báo cáo (Excel)"):
            bytes_xlsx = export_df_to_excel_bytes(df_display)
            st.download_button("📥 Tải báo cáo.xlsx", data=bytes_xlsx, file_name="bao_cao_don_hang.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.info("Lưu ý: bạn có thể dùng tab 'Nhắc nhở' để xuất danh sách cần follow up.")

