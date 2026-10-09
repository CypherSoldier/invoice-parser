import json
import os
import shutil
import glob

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai
from pdf2image import convert_from_bytes
from PIL import Image

load_dotenv()

FREE_INVOICE_LIMIT = 3


def init_session_state():
    st.session_state.setdefault("free_invoices_used", 0)
    st.session_state.setdefault("is_pro", False)
    st.session_state.setdefault("review_df", pd.DataFrame())
    st.session_state.setdefault("last_upload_name", "")


def can_process_invoice(state=None):
    if state is None:
        state = st.session_state
    return bool(state.get("is_pro")) or int(state.get("free_invoices_used", 0)) < FREE_INVOICE_LIMIT


def get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured. Add it to your .env file.")
    return genai.Client(api_key=api_key)


def get_poppler_path():
    """Return a configured Poppler directory, if one is available."""
    configured_path = os.getenv("POPPLER_PATH")
    if configured_path:
        return configured_path

    if shutil.which("pdfinfo") and shutil.which("pdftoppm"):
        return None

    common_paths = glob.glob(
        os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_*\*\Library\bin"
        )
    )
    common_paths.append(r"C:\Program Files\poppler\Library\bin")
    for path in common_paths:
        if os.path.isfile(os.path.join(path, "pdfinfo.exe")) and os.path.isfile(
            os.path.join(path, "pdftoppm.exe")
        ):
            return path

    return None


POPPLER_PATH = get_poppler_path()

PROMPT = """
Extract this invoice into ONLY valid JSON, no commentary, in this shape:
{
  "supplier_name": "",
  "invoice_date": "",
  "line_items": [
    {"description": "", "quantity": 0, "unit_price": 0.0, "line_total": 0.0}
  ],
  "shipping_cost": 0.0,
  "subtotal": 0.0,
  "total": 0.0
}
If a field is unreadable, use null rather than guessing.
"""


def build_export_dataframe(invoice_data):
    line_items = invoice_data.get("line_items") or []
    first_item = line_items[:1]
    if not first_item:
        return pd.DataFrame(columns=["description", "quantity", "unit_price", "line_total"])
    return pd.DataFrame(first_item)


def render_payfast_sandbox():
    st.subheader("Payfast Sandbox")
    st.caption("This is a demo checkout to unlock Pro for the remainder of the session.")
    with st.form("payfast_checkout"):
        st.text_input("First name", value="Demo")
        st.text_input("Last name", value="Customer")
        st.text_input("Email", value="demo@payfast.co.za")
        st.number_input("Amount", value=299.00, min_value=0.0, max_value=9999.0, step=0.01, disabled=True)

        if st.form_submit_button("Upgrade to Pro"):
            st.session_state["is_pro"] = True
            st.success("Sandbox payment successful. Pro is now unlocked for this session.")
            st.rerun()

    st.markdown(
        """
        <div style='padding:8px 0; color:#666;'>
        Demo setup: use the Payfast sandbox flow with merchant_id=10000100 and merchant_key=46f0cd694581a.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_upgrade_prompt():
    st.warning(
        "You’ve reached the free invoice limit for this session. Upgrade to Pro to continue processing more invoices."
    )
    render_payfast_sandbox()


def parse_uploaded_file(uploaded_file):
    if uploaded_file.type == "application/pdf":
        if POPPLER_PATH is None and not (shutil.which("pdfinfo") and shutil.which("pdftoppm")):
            raise RuntimeError(
                "Poppler is required to read PDF files. Install the Windows Poppler package or set "
                "POPPLER_PATH to its Library\\bin folder, then restart Streamlit."
            )
        pages = convert_from_bytes(uploaded_file.read(), poppler_path=POPPLER_PATH)
        image = pages[0]
    else:
        image = Image.open(uploaded_file)
    return image


def extract_invoice_data(uploaded_file):
    client = get_genai_client()
    image = parse_uploaded_file(uploaded_file)
    with st.spinner("Extracting invoice..."):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[PROMPT, image],
        )
        response_text = response.text.strip()
        response_text = response_text.removeprefix("```json").removesuffix("```").strip()
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            st.warning("The model response was not valid JSON. Showing the raw response instead.")
            st.text(response.text)
            st.stop()


def main():
    init_session_state()
    st.title("Invoice Parser")

    with st.sidebar:
        st.header("Plan")
        st.write(f"Free invoices used: {st.session_state['free_invoices_used']} / {FREE_INVOICE_LIMIT}")
        if st.session_state.get("is_pro"):
            st.success("Pro plan active")
        else:
            if st.button("Upgrade to Pro"):
                render_payfast_sandbox()

    if not can_process_invoice():
        render_upgrade_prompt()
        return

    uploaded = st.file_uploader("Drop a PDF or photo", type=["pdf", "png", "jpg", "jpeg"])
    if not uploaded:
        return

    try:
        data = extract_invoice_data(uploaded)
    except RuntimeError as exc:
        st.error(str(exc))
        return

    if not st.session_state.get("is_pro"):
        st.session_state["free_invoices_used"] = int(st.session_state.get("free_invoices_used", 0)) + 1

    if "line_items" not in data or not isinstance(data["line_items"], list):
        st.error("The invoice did not contain usable line items.")
        return

    st.subheader(f"Supplier: {data.get('supplier_name', 'Unknown')}")
    st.metric("Total", f"${data.get('total', 0):,.2f}")

    review_df = pd.DataFrame(data["line_items"])
    st.session_state["review_df"] = review_df.copy()
    edited_df = st.data_editor(
        review_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "quantity": st.column_config.NumberColumn(step=1),
            "unit_price": st.column_config.NumberColumn(step=0.01),
            "line_total": st.column_config.NumberColumn(step=0.01),
        },
    )

    st.subheader("Review and export")
    st.caption("Correct OCR mistakes before exporting the invoice CSV.")
    st.dataframe(edited_df, use_container_width=True)

    csv_payload = build_export_dataframe({"line_items": edited_df.to_dict("records")}).to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv_payload, f"{uploaded.name or 'invoice'}.csv", "text/csv")


if __name__ == "__main__":
    main()
