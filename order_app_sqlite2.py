import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client
import math

st.set_page_config(page_title="Quản Lý Đơn Hàng", layout="wide")

# ===================== CONFIG SUPABASE =====================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

REMINDER_DAYS = [9, 7, 5, 3]

# ===================== DATABASE HELPER =====================
def fetch_orders():
    res = supabase.table("orders").select("*").order("id", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        for c in ["start_date", "expected_date", "delivered_date", "created_at"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        return df
    return pd.DataFrame()

def insert_order(order):
    return supabase.table("orders").insert(order).execute()

def update_order(order_id, data):
    return supabase.table("orders").update(data).eq("id", order_id).execute()

def delete_order(order_id):
    return supabase.table("orders").delete().eq("id", order_id).execute()

# ===================== UI =====================
st.title("📦 Quản Lý Đơn Hàng")

menu = st.sidebar.radio("Menu", ["➕ Thêm Đơn Hàng", "✏️ Quản Lý / Chỉnh Sửa"])

# ===================== MENU 1: ADD =====================
if menu == "➕ Thêm Đơn Hàng":
    with st.form("add_order_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            order_code = st.text_input("Mã đơn")
            name = st.text_input("Tên khách")
        with col2:
            start_date = st.date_input("Ngày bắt đầu", datetime.today())
            lead_time = st.number_input("Thời gian sản xuất (ngày)", min_value=0, value=10)
        with col3:
            price_cny = st.number_input("💴 Giá nhập (tệ)", min_value=0.0, step=0.1)
            quantity = st.number_input("📦 Số lượng", min_value=0, step=1)
            deposit_amount = st.number_input("💰 Tiền đặt cọc", min_value=0.0, step=0.1)

        notes = st.text_area("Ghi chú")
        package_info = st.text_area("Thông tin kiện hàng")

        submitted = st.form_submit_button("✅ Thêm Đơn")
        if submitted:
            total_cny = price_cny * quantity if quantity else 0
            deposit_ratio = (deposit_amount / total_cny) if total_cny else 0
            expected_date = start_date + timedelta(days=int(lead_time))
            payload = {
                "order_code": order_code,
                "name": name,
                "start_date": start_date.isoformat(),
                "lead_time": int(lead_time),
                "expected_date": expected_date.isoformat(),
                "delivered_date": None,
                "status": "Đang sản xuất",
                "notes": notes,
                "package_info": package_info,
                "price_cny": price_cny,
                "quantity": quantity,
                "total_cny": total_cny,
                "deposit_amount": deposit_amount,
                "deposit_ratio": deposit_ratio,
                "created_at": datetime.utcnow().isoformat()
            }
            res = insert_order(payload)
            if res.data:
                st.success("✅ Đã thêm đơn hàng!")
            else:
                st.error(f"❌ Lỗi Supabase insert: {res}")

# ===================== MENU 2: MANAGE =====================
elif menu == "✏️ Quản Lý / Chỉnh Sửa":
    df = fetch_orders()
    if df.empty:
        st.info("⚠️ Chưa có đơn hàng nào.")
    else:
        st.dataframe(df[["id", "order_code", "name", "start_date",
                         "expected_date", "status",
                         "price_cny", "quantity", "total_cny",
                         "deposit_amount", "deposit_ratio"]],
                     use_container_width=True)

        order_ids = df["id"].tolist()
        edit_id = st.selectbox("Chọn ID để chỉnh sửa / xóa", order_ids)
        order_row = df[df["id"] == edit_id].iloc[0]

        with st.form("edit_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                e_code = st.text_input("Mã đơn", order_row["order_code"])
                e_name = st.text_input("Tên khách", order_row["name"])
            with col2:
                e_start = st.date_input("Ngày bắt đầu",
                                         order_row["start_date"].date() if pd.notnull(order_row["start_date"]) else datetime.today())
                e_lead = st.number_input("Thời gian sản xuất", min_value=0,
                                         value=int(order_row["lead_time"] or 0))
            with col3:
                e_price = st.number_input("💴 Giá nhập (tệ)",
                                          min_value=0.0,
                                          value=float(order_row["price_cny"] or 0))
                e_quantity = st.number_input("📦 Số lượng",
                                             min_value=0,
                                             value=int(order_row["quantity"] or 0))
                e_deposit = st.number_input("💰 Tiền đặt cọc",
                                            min_value=0.0,
                                            value=float(order_row["deposit_amount"] or 0))

            e_notes = st.text_area("Ghi chú", order_row["notes"] or "")
            e_package = st.text_area("Thông tin kiện hàng", order_row["package_info"] or "")

            update_btn = st.form_submit_button("💾 Cập nhật")
            delete_btn = st.form_submit_button("🗑️ Xóa đơn")

            if update_btn:
                new_total = e_price * e_quantity if e_quantity else 0
                new_ratio = (e_deposit / new_total) if new_total else 0
                expected_date = e_start + timedelta(days=int(e_lead))
                update_payload = {
                    "order_code": e_code,
                    "name": e_name,
                    "start_date": e_start.isoformat(),
                    "lead_time": int(e_lead),
                    "expected_date": expected_date.isoformat(),
                    "notes": e_notes,
                    "package_info": e_package,
                    "price_cny": e_price,
                    "quantity": e_quantity,
                    "deposit_amount": e_deposit,
                    "deposit_ratio": new_ratio
                }
                res = update_order(edit_id, update_payload)
                if res.data:
                    st.success("✅ Cập nhật thành công!")
                else:
                    st.error(f"❌ Lỗi Supabase update: {res}")

            if delete_btn:
                delete_order(edit_id)
                st.warning("🗑️ Đã xóa đơn hàng.")

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
