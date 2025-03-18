import streamlit as st
import pandas as pd
from pymongo import MongoClient
import base64
import io

# Set page configuration
st.set_page_config(
    page_title="PFAS Zip Code Checker",
    page_icon="🧪",
    layout="wide"
)

# Define CSS for better styling
st.markdown("""
<style>
    .title {
        font-size: 42px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 20px;
    }
    .subtitle {
        font-size: 24px;
        color: #1E3A8A;
        margin-bottom: 10px;
    }
    .success {
        color: green;
        font-weight: bold;
    }
    .info-box {
        background-color: #E5E7EB;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Main title
st.markdown('<p class="title">PFAS Zip Code Checker</p>', unsafe_allow_html=True)

# Keep the PFAS zip code data in the session state to avoid reloading
if 'pfas_zip_codes' not in st.session_state:
    st.session_state.pfas_zip_codes = None

# MongoDB Connection Details
# Store these in Streamlit secrets in production
# You can access them using st.secrets["mongo_uri"] etc.
mongodb_uri = st.secrets["mongodb_uri"]
mongodb_db = st.secrets["mongodb_db"]
mongodb_collection = st.secrets["mongodb_collection"]

# Function to load PFAS zip codes from MongoDB
@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_pfas_zipcodes_from_mongodb():
    try:
        # Connect to MongoDB
        client = MongoClient(mongodb_uri)
        db = client[mongodb_db]
        collection = db[mongodb_collection]
        
        # Fetch all records from the collection
        records = list(collection.find({}, {"_id": 0}))
        
        # Convert to DataFrame
        df = pd.DataFrame(records)
        
        # Extract and clean zip codes
        pfas_zip_codes = df['ZIP Codes']
        pfas_zips_clean = set()
        
        for row in pfas_zip_codes:
            if isinstance(row,list):
                codes = [str(code).strip() for code in row if code]
            else:
                codes = [code.strip() for code in str(row).split(';')]
            for code in codes:
                if code and code != 'nan':
                    pfas_zips_clean.add(code)
        
        return pfas_zips_clean
    
    except Exception as e:
        st.error(f'Error loading PFAS zip codes from MongoDB: {e}')
        return set()

# Load PFAS zip codes
if st.session_state.pfas_zip_codes is None:
    st.session_state.pfas_zip_codes = load_pfas_zipcodes_from_mongodb()
    if st.session_state.pfas_zip_codes:
        st.markdown(f'<p>Database loaded with {len(st.session_state.pfas_zip_codes)} unique PFAS-affected zip codes.</p>', unsafe_allow_html=True)

# Create tabs for different functionalities
tab1, tab2 = st.tabs(["Check Single Zip Code", "Process Client File"])

# Tab 1: Single Zip Code Check
with tab1:
    st.markdown('<p class="subtitle">Check a Single Zip Code</p>', unsafe_allow_html=True)
    
    with st.form("zip_code_form"):
        zip_code = st.text_input("Enter a 5-digit zip code:", max_chars=5)
        check_button = st.form_submit_button("Check Zip Code")
        
        if check_button:
            if not (len(zip_code) == 5 and zip_code.isdigit()):
                st.error('Invalid zip code format. Please enter a 5-digit zip code.')
            else:
                if zip_code in st.session_state.pfas_zip_codes:
                    st.success(f'✅ Zip code {zip_code} is in a PFAS-affected area.')
                else:
                    st.warning(f"❌ Zip code {zip_code} is NOT in a PFAS-affected area.")

# Tab 2: Process Client File
with tab2:
    st.markdown('<p class="subtitle">Check Multiple Zip Codes</p>', unsafe_allow_html=True)
    
    st.markdown('<div class="info-box">Upload a CSV or Excel file containing a column with zip codes. The file will be processed to identify which zip codes are in PFAS-affected areas.</div>', unsafe_allow_html=True)
    
    # File upload widget
    uploaded_file = st.file_uploader("Upload your client file (CSV or Excel)", type=['csv', 'xlsx', 'xls'])
    
    if uploaded_file is not None:
        # Process the uploaded file
        try:
            # Determine file type and load accordingly
            if uploaded_file.name.endswith('.csv'):
                client_df = pd.read_csv(uploaded_file)
            elif uploaded_file.name.endswith(('.xlsx', '.xls')):
                client_df = pd.read_excel(uploaded_file)
            
            # Display the first few rows of the file
            st.write("Preview of uploaded data:")
            st.dataframe(client_df.head())
            
            # Find the zip code column
            possible_zip_columns = ['zip', 'zip_code', 'zipcode', 'postal_code', 'postal', 'zip code']
            available_columns = client_df.columns.tolist()
            
            # Try to find a match automatically
            zip_column = None
            for col in client_df.columns:
                if col.lower() in possible_zip_columns:
                    zip_column = col
                    break
            
            # If not found automatically, let the user select
            if zip_column is None:
                zip_column = st.selectbox(
                    "Select the column containing zip codes:",
                    options=available_columns
                )
            else:
                zip_column = st.selectbox(
                    "Confirm or change the column containing zip codes:",
                    options=available_columns,
                    index=available_columns.index(zip_column)
                )
            
            process_button = st.button("Process Data")
            
            if process_button:
                with st.spinner("Processing data..."):
                    # Ensure zip codes are treated as strings
                    client_df[zip_column] = client_df[zip_column].astype(str)
                    
                    # Handle zip codes that might have decimal points
                    client_df[zip_column] = client_df[zip_column].apply(
                        lambda x: x.split('.')[0].zfill(5) if x and x != 'nan' else x
                    )
                    
                    # Add the PFAS status column
                    client_df['In_PFAS_Area'] = client_df[zip_column].apply(
                        lambda x: 'Yes' if x in st.session_state.pfas_zip_codes else 'No'
                    )
                    
                    # Count results
                    pfas_count = client_df['In_PFAS_Area'].value_counts().get('Yes', 0)
                    total_count = len(client_df)
                    
                    # Create a results container
                    results_container = st.container()
                    
                    with results_container:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.metric(
                                "Total Clients", 
                                f"{total_count}"
                            )
                        
                        with col2:
                            st.metric(
                                "Clients in PFAS Areas", 
                                f"{pfas_count}",
                                f"{pfas_count/total_count*100:.1f}%"
                            )
                        
                        # Display the results dataframe
                        st.write("Results (with PFAS status):")
                        st.dataframe(client_df)
                        
                        # Create a download link for the results
                        csv_buffer = io.StringIO()
                        client_df.to_csv(csv_buffer, index=False)
                        csv_str = csv_buffer.getvalue()
                        
                        b64 = base64.b64encode(csv_str.encode()).decode()
                        href = f'<a href="data:file/csv;base64,{b64}" download="{uploaded_file.name.split(".")[0]}_with_pfas_status.csv" class="success">Download Results as CSV</a>'
                        st.markdown(href, unsafe_allow_html=True)
                
        except Exception as e:
            st.error(f"Error processing file: {e}")

# Footer
st.markdown("---")
st.markdown("© 2025 PFAS Zip Code Checker")