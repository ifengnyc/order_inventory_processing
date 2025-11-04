import streamlit as st
import pandas as pd
import os

# --- Constants ---
ITEM_DATA_FILE = "item_data.xlsx"
EXCEPTION_CASES_FILE = "exception_cases.xlsx"

# --- Helper Functions ---

def load_data_if_exists(file_path):
    """Loads data from an Excel file if it exists."""
    if os.path.exists(file_path):
        try:
            return pd.read_excel(file_path)
        except Exception as e:
            st.error(f"Error loading {file_path}: {e}")
    return None

# --- Data Processing Logic Functions ---

def process_orders_logic(orders, item_data, exception_cases):
    """
    Processes the orders data based on item data and exception cases.
    This function contains the original pandas logic without refactoring.
    """
    # Filter out rows where `Variant SKU` starts with 'ROUTEINS' or 'KITE'
    orders = orders[~orders['Variant SKU'].astype(str).str.startswith(('ROUTEINS', 'KITE'))]

    # Create dictionaries for multipliers and name changes
    product_multipliers = dict(zip(exception_cases['Variant SKU'], exception_cases['Quantity']))
    product_name_changes = dict(zip(exception_cases['Variant SKU'], exception_cases['Item Name']))

    # Convert 'Quantity' column in 'orders' to numeric type
    orders['Quantity'] = pd.to_numeric(orders['Quantity'], errors='coerce')

    # Apply multipliers and name changes
    orders['Quantity'] *= orders['Variant SKU'].map(product_multipliers).fillna(1)
    orders['Variant SKU'] = orders['Variant SKU'].replace(product_name_changes)

    # Aggregate and sort
    shipment = (
        orders.groupby('Variant SKU')['Quantity']
        .sum()
        .reset_index()
        .rename(columns={'Variant SKU': 'Variant_SKU'})
        .assign(Variant_SKU=lambda x:x['Variant_SKU'].str.split('+'))
        .explode('Variant_SKU')
    )
    # Merge data, rename and rearrange columns according to delivery note template
    col = ['item_code', 'item_name', 'description', 'qty', 'stock_uom', 'uom', 'amount']

    delivery = (
        shipment.merge(item_data, how='left', left_on='Variant_SKU', right_on='Item Name')
        .assign(amount=lambda x:x['Quantity'] * x['Amount'])
        .assign(uom=lambda x:x['Default Unit of Measure'])
        .rename(columns={'ID':'item_code', 'Item Name':'item_name', 'Variant_SKU':'description', 'Quantity':'qty', 'Default Unit of Measure':'stock_uom'})
        .reindex(columns=col)
    )

    multi_cols = pd.MultiIndex.from_arrays([col, col, col])
    delivery.columns = multi_cols

    new_index = range(-4, len(delivery))
    delivery = delivery.reindex(new_index)

    return delivery

def process_inventory_logic(stock, shopify, exception_cases):
    """
    Processes the inventory data based on stock, shopify, and exception cases.
    This function contains the original pandas logic without refactoring.
    """
    # Create qty mapping for stock and exception cases
    stock_qty = stock.groupby('Item Name')['Balance Qty'].sum()
    exception_fixqty = exception_cases.groupby('Variant SKU')['Fix Qty'].sum()

    # Create a 'Total Qty' column in exception_cases
    exception_cases['Total Qty'] = exception_cases['Fix Qty'] * exception_cases['Quantity']

    # First, map stock quantities to the 'On hand' column in shopify
    shopify['On hand'] = shopify['SKU'].map(stock_qty).fillna(0)

    # Then, update 'On hand' using exception cases, prioritizing the 'Fix Qty'
    shopify['On hand'] = shopify['SKU'].map(exception_fixqty).fillna(shopify['On hand'])
    
    # Finally, update 'On hand' using exception cases, subtracting the 'Total Qty'
    for i in exception_cases['Item Name'].unique():
        shopify.loc[shopify['SKU'] == i, 'On hand'] -= exception_cases.loc[exception_cases['Item Name'] == i, 'Total Qty'].sum()

    return shopify


# --- Streamlit UI ---

st.title("Data Processor")

# --- Initialize Session State ---
if 'item_data' not in st.session_state:
    st.session_state.item_data = load_data_if_exists(ITEM_DATA_FILE)
    if st.session_state.item_data is not None:
        st.toast("Loaded item data from previous session.")

if 'exception_cases' not in st.session_state:
    st.session_state.exception_cases = load_data_if_exists(EXCEPTION_CASES_FILE)
    if st.session_state.exception_cases is not None:
        st.toast("Loaded exception cases from previous session.")

if 'orders' not in st.session_state:
    st.session_state.orders = None
if 'stock' not in st.session_state:
    st.session_state.stock = None
if 'shopify' not in st.session_state:
    st.session_state.shopify = None


# --- UI Tabs ---
tab1, tab2 = st.tabs(["Order Processing", "Inventory Processing"])

with tab1:
    st.header("Order Processing")
    st.info("Upload Item Data and Exception Cases here. They will be saved for future use in both processing tabs.")

    # --- File Uploads for Order Processing ---
    uploaded_item_data = st.file_uploader("Upload Item Data File (xlsx)", type=["xlsx"], key="item_data_uploader")
    uploaded_exception_cases = st.file_uploader("Upload Exception Cases File (xlsx)", type=["xlsx"], key="exception_cases_uploader")
    uploaded_orders = st.file_uploader("Upload Orders File (xlsx)", type=["xlsx"], key="orders_uploader")

    if uploaded_item_data:
        try:
            st.session_state.item_data = pd.read_excel(uploaded_item_data)
            st.session_state.item_data.to_excel(ITEM_DATA_FILE, index=False)
            st.success("Item data file uploaded and saved successfully!")
        except Exception as e:
            st.error(f"Error reading or saving item data file: {e}")

    if uploaded_exception_cases:
        try:
            st.session_state.exception_cases = pd.read_excel(uploaded_exception_cases)
            st.session_state.exception_cases.to_excel(EXCEPTION_CASES_FILE, index=False)
            st.success("Exception cases file uploaded and saved successfully!")
        except Exception as e:
            st.error(f"Error reading or saving exception cases file: {e}")

    if uploaded_orders:
        try:
            st.session_state.orders = pd.read_excel(uploaded_orders)
            st.success("Orders file uploaded successfully!")
        except Exception as e:
            st.error(f"Error reading orders file: {e}")

    # --- Processing Trigger ---
    st.subheader("Process Orders")
    if st.button("Process Orders", key="process_orders_button"):
        if st.session_state.item_data is not None and st.session_state.exception_cases is not None and st.session_state.orders is not None:
            with st.spinner("Processing orders..."):
                processed_delivery = process_orders_logic(
                    st.session_state.orders,
                    st.session_state.item_data,
                    st.session_state.exception_cases
                )
                st.write("✅ Processed orders:")
                st.write(processed_delivery)

                st.download_button(
                    label="Download Delivery as CSV",
                    data=processed_delivery.to_csv(index=False).encode('utf-8'),
                    file_name='delivery.csv',
                    mime='text/csv',
                )
        else:
            st.warning("Please ensure Item Data, Exception Cases, and Orders files are uploaded.")


with tab2:
    st.header("Inventory Processing")
    st.info("This processor uses the saved Exception Cases file. If you need to update it, please do so in the 'Order Processing' tab.")

    # --- File Uploads for Inventory Processing ---
    uploaded_stock = st.file_uploader("Upload Stock File (xlsx)", type=["xlsx"], key="stock_uploader")
    uploaded_shopify = st.file_uploader("Upload Shopify File (csv)", type=["csv"], key="shopify_uploader")

    if uploaded_stock:
        try:
            st.session_state.stock = pd.read_excel(uploaded_stock)
            st.success('Stock file uploaded successfully!')
        except Exception as e:
            st.error(f"Error reading stock file: {e}")

    if uploaded_shopify:
        try:
            st.session_state.shopify = pd.read_csv(uploaded_shopify)
            st.success('Shopify file uploaded successfully!')
        except Exception as e:
            st.error(f"Error reading shopify file: {e}")

    # --- Processing Trigger ---
    st.subheader("Process Inventories")
    if st.button("Process Inventories", key="process_inventory_button"):
        if st.session_state.exception_cases is not None and st.session_state.stock is not None and st.session_state.shopify is not None:
            with st.spinner("Processing inventories..."):
                processed_shopify = process_inventory_logic(
                    st.session_state.stock,
                    st.session_state.shopify,
                    st.session_state.exception_cases
                )
                st.write("✅ Processed inventories (shopify):")
                st.write(processed_shopify)

                st.download_button(
                    label="Download Shopify as CSV",
                    data=processed_shopify.to_csv(index=False).encode('utf-8'),
                    file_name='shopify.csv',
                    mime='text/csv',
                )
        else:
            st.warning("Please ensure Exception Cases, Stock, and Shopify files are uploaded.")