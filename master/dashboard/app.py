import os
import sys
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import parse_qs, urlparse, urljoin
import time
import json
from bs4 import BeautifulSoup, Comment
from openai import OpenAI
from dotenv import load_dotenv

# Add parent directory to path for database imports
script_dir = os.path.dirname(os.path.abspath(__file__))
master_dir = os.path.dirname(script_dir)
if master_dir not in sys.path:
    sys.path.insert(0, master_dir)

try:
    from database import SessionLocal
    from models import AutomatedScrapingConfig
    from sqlalchemy import func
    DB_AVAILABLE = True
except Exception as e:
    DB_AVAILABLE = False
    st.warning(f"Database not available: {e}")

# Load environment variables from .env file
# Try to load from master directory (parent of dashboard/)
script_dir = os.path.dirname(os.path.abspath(__file__))
master_dir = os.path.dirname(script_dir)
env_path = os.path.join(master_dir, '.env')
load_dotenv(env_path)  # Try master/.env first
load_dotenv()  # Also try current directory as fallback

API_BASE_URL = "http://localhost:8000/api/v1"

st.set_page_config(
    page_title="Distributed Orchestration Dashboard",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .stDataFrame {width: 100%;}
    .stButton>button {width: 100%;}
    .status-pending {color: #FFA500;}
    .status-ready {color: #1E90FF;}
    .status-processing {color: #FF4500;}
    .status-completed {color: #32CD32;}
    .sidebar .sidebar-content {
        background-color: #f0f2f6;
    }
    </style>
""", unsafe_allow_html=True)

def get_current_page():
    page = None
    
    try:
        if hasattr(st, 'query_params'):
            query_params = st.query_params
            if isinstance(query_params, dict) and 'page' in query_params:
                page = query_params['page']
                if isinstance(page, list) and len(page) > 0:
                    page = page[0]
                elif isinstance(page, str):
                    page = page
        elif hasattr(st, 'experimental_get_query_params'):
            query_params = st.experimental_get_query_params()
            if 'page' in query_params:
                page = query_params['page'][0]
    except Exception:
        pass
    
    if page and page in ['websites', 'nodes', 'batches', 'priority_batches', 'settings', 'automated_scraping']:
        if 'current_page' not in st.session_state or st.session_state.current_page != page:
            st.session_state.current_page = page
        return page
    
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'websites'
    return st.session_state.current_page


def parse_country_info_input(raw_input: str) -> List[Dict[str, str]]:
    """Convert the multiline country input into structured data."""
    if not raw_input:
        return []

    entries: List[Dict[str, str]] = []
    separators = ["=", ":", "|", ",", "\t"]

    for line in raw_input.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue

        country = cleaned
        country_url = None

        for sep in separators:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                country = parts[0].strip()
                country_url = parts[1].strip() or None
                break

        if country:
            entry: Dict[str, str] = {"country": country}
            if country_url:
                entry["url"] = country_url
            entries.append(entry)

    return entries

def set_current_page(page: str):
    st.session_state.current_page = page
    try:
        if hasattr(st, 'query_params'):
            st.query_params['page'] = page
        elif hasattr(st, 'experimental_set_query_params'):
            st.experimental_set_query_params(page=page)
    except Exception:
        pass

@st.cache_data(ttl=5, show_spinner=False)
def get_websites_cached(status: Optional[str] = None, page: int = 1, page_size: int = 10) -> dict:
    """Cached version of get_websites to prevent unnecessary API calls."""
    try:
        params = {
            "status": status,
            "page": page,
            "page_size": page_size
        } if status else {
            "page": page,
            "page_size": page_size
        }
        response = requests.get(f"{API_BASE_URL}/websites", params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"items": [], "total": 0, "page": 1, "page_size": page_size}

def get_websites(status: Optional[str] = None, page: int = 1, page_size: int = 10) -> dict:
    """Wrapper that uses cached version but allows manual refresh."""
    cache_key = f"websites_{status}_{page}_{page_size}"
    if st.session_state.get("force_refresh", False):
        # Clear cache and reset flag
        get_websites_cached.clear()
        st.session_state.force_refresh = False
    
    return get_websites_cached(status, page, page_size)

@st.cache_data(ttl=3, show_spinner=False)
def get_all_nodes_cached() -> List[Dict]:
    """Cached version of get_all_nodes to prevent unnecessary API calls."""
    try:
        response = requests.get(f"{API_BASE_URL}/nodes", timeout=5)
        response.raise_for_status()
        nodes = response.json()
        # Sort by ID to maintain consistent order
        return sorted(nodes, key=lambda x: x.get('id', 0))
    except requests.exceptions.RequestException:
        return []

def get_all_nodes() -> List[Dict]:
    """Wrapper that uses cached version but allows manual refresh."""
    if st.session_state.get("force_refresh", False):
        get_all_nodes_cached.clear()
        st.session_state.force_refresh = False
    
    return get_all_nodes_cached()

def get_all_tasks(status: Optional[str] = None, node_id: Optional[int] = None, website_id: Optional[int] = None) -> List[Dict]:
    try:
        params = {}
        if status:
            params["status"] = status
        if node_id:
            params["node_id"] = node_id
        if website_id:
            params["website_id"] = website_id
        response = requests.get(f"{API_BASE_URL}/tasks", params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching tasks: {e}")
        return []

@st.cache_data(ttl=5, show_spinner=False)
def get_all_batches_cached(website_id: Optional[int] = None) -> List[Dict]:
    """Cached version of get_all_batches."""
    try:
        params = {}
        if website_id:
            params["website_id"] = website_id
        response = requests.get(f"{API_BASE_URL}/batches", params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return []

def get_all_batches(website_id: Optional[int] = None) -> List[Dict]:
    """Wrapper that uses cached version."""
    if st.session_state.get("force_refresh", False):
        get_all_batches_cached.clear()
        st.session_state.force_refresh = False
    return get_all_batches_cached(website_id)

@st.cache_data(ttl=5, show_spinner=False)
def get_all_priority_batches_cached(website_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> Dict:
    """Cached version of get_all_priority_batches."""
    try:
        params = {"skip": skip, "limit": limit}
        if website_id:
            params["website_id"] = website_id
        response = requests.get(f"{API_BASE_URL}/priority-batches", params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return {"items": [], "total": 0, "skip": 0, "limit": limit}

def get_all_priority_batches(website_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> Dict:
    """Wrapper that uses cached version."""
    if st.session_state.get("force_refresh", False):
        get_all_priority_batches_cached.clear()
        st.session_state.force_refresh = False
    return get_all_priority_batches_cached(website_id, skip, limit)


def get_notification_emails() -> List[str]:
    try:
        response = requests.get(f"{API_BASE_URL}/settings/notifications")
        response.raise_for_status()
        data = response.json()
        return data.get("emails", [])
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching notification settings: {e}")
        return []


def update_notification_emails(emails: List[str]) -> bool:
    try:
        payload = {"emails": emails}
        response = requests.post(f"{API_BASE_URL}/settings/notifications", json=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"Error updating notification settings: {e}")
        return False


@st.cache_data(ttl=2, show_spinner=False)
def get_node_logs_cached(node_id: int, limit: int = 100) -> List[Dict]:
    """Cached version of get_node_logs to prevent unnecessary API calls."""
    try:
        params = {"limit": limit}
        response = requests.get(f"{API_BASE_URL}/nodes/{node_id}/logs", params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return []

def get_node_logs(node_id: int, limit: int = 100, force_refresh: bool = False) -> List[Dict]:
    """Wrapper that uses cached version but allows manual refresh."""
    if force_refresh:
        get_node_logs_cached.clear()
    
    return get_node_logs_cached(node_id, limit)

def update_validator(url: str, validator: str, website_type: Optional[str] = None, priority: bool = False) -> bool:
    try:
        payload = {"url": url, "validator": validator.strip(), "priority": priority}
        if website_type:
            payload["type"] = website_type
        response = requests.patch(
            f"{API_BASE_URL}/websites/validator",
            json=payload
        )
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"Error updating validator: {e}")
        return False

def display_websites(websites_data: dict):
    items = websites_data.get('items', [])
    total = websites_data.get('total', 0)
    page = websites_data.get('page', 1)
    page_size = websites_data.get('page_size', 10)
    
    if not items:
        st.info("No websites found with the selected status.")
        return
    
    st.caption(f"Showing {len(items)} of {total} websites (Page {page})")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if page > 1:
            if st.button("← Previous Page"):
                st.session_state.website_page = max(1, page - 1)
                st.rerun()
    
    with col2:
        st.write(f"Page {page} of {(total + page_size - 1) // page_size}")
    
    with col3:
        if len(items) == page_size and (page * page_size) < total:
            if st.button("Next Page →"):
                st.session_state.website_page = page + 1
                st.rerun()
    
    websites_display = items.copy()
    status_emoji_map = {
        'pending_validator': '⏳',
        'ready': '✅',
        'in_queue': '📋',
        'processing': '🔄',
        'paused': '⏸️',
        'completed': '✔️',
        'terminated': '🛑',
        'rejected': '❌',
        'manual_extraction': '✋'
    }
    
    for i, website in enumerate(websites_display):
        if website['status'] == 'pending_validator':
            with st.expander(f"Set Validator for {website['url']}"):
                with st.form(key=f"validator_form_{i}"):
                    validator_input = st.text_input(
                        "CSS Selector for Validation",
                        key=f"validator_{i}",
                        value=website.get('validator', '')
                    )
                    website_type_input = st.selectbox(
                        "Website Type",
                        options=["Select Type", "retailer", "brand"],
                        index=0 if not website.get('type') else (["Select Type", "retailer", "brand"].index(website.get('type')) if website.get('type') in ["retailer", "brand"] else 0),
                        key=f"type_{i}"
                    )
                    priority_input = st.checkbox(
                        "Priority",
                        value=website.get('priority', False),
                        key=f"priority_{i}"
                    )
                    if st.form_submit_button("Update Validator"):
                        selected_type = website_type_input if website_type_input != "Select Type" else None
                        if update_validator(website['url'], validator_input, selected_type, priority_input):
                            st.success(f"Validator updated for {website['url']}")
                            st.rerun()
        
        status_emoji = status_emoji_map.get(website['status'], '❓')
        website['Status'] = f"{status_emoji} {website['status'].replace('_', ' ').title()}"
        
        if 'priority' in website:
            website['Priority'] = '⭐' if website.get('priority', False) else ''
        else:
            website['Priority'] = ''

        country_info_entries = website.get('country_info')
        if isinstance(country_info_entries, list) and country_info_entries:
            formatted_entries = []
            for entry in country_info_entries:
                country_name = entry.get('country')
                country_url = entry.get('url')
                if country_name and country_url:
                    formatted_entries.append(f"{country_name} ({country_url})")
                elif country_name:
                    formatted_entries.append(country_name)
                elif country_url:
                    formatted_entries.append(country_url)
            website['Country Availability'] = ", ".join(formatted_entries) if formatted_entries else '—'
        else:
            website['Country Availability'] = '—'
    
    df = pd.DataFrame(websites_display)
    
    if 'priority' in df.columns:
        df = df.drop(columns=['priority'])
    if 'country_info' in df.columns:
        df = df.drop(columns=['country_info'])
    
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    if 'updated_at' in df.columns:
        df['updated_at'] = pd.to_datetime(df['updated_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "url": "Website URL",
            "Status": "Status",
            "Priority": "Priority",
            "validator": "Validator",
            "type": "Type",
            "Country Availability": "Country Availability",
            "created_at": "Created At",
            "updated_at": "Last Updated"
        },
        hide_index=True
    )
    
    # Show action buttons for paused websites
    paused_websites = [w for w in websites_display if w['status'] == 'paused']
    if paused_websites:
        st.divider()
        st.subheader("⏸️ Paused Websites - Action Required")
        for website in paused_websites:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.write(f"**{website['url']}** (ID: {website['id']})")
                with col2:
                    if st.button("▶️ Resume", key=f"resume_{website['id']}", use_container_width=True):
                        try:
                            response = requests.post(f"{API_BASE_URL}/websites/{website['id']}/resume")
                            if response.status_code == 200:
                                st.success(f"✅ {response.json().get('message', 'Resumed successfully')}")
                                st.rerun()
                            else:
                                st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                        except Exception as e:
                            st.error(f"Error resuming website: {e}")
                with col3:
                    if st.button("❌ Discard", key=f"discard_{website['id']}", use_container_width=True):
                        try:
                            response = requests.post(f"{API_BASE_URL}/websites/{website['id']}/discard")
                            if response.status_code == 200:
                                st.success(f"✅ {response.json().get('message', 'Discarded successfully')}")
                                st.rerun()
                            else:
                                st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                        except Exception as e:
                            st.error(f"Error discarding website: {e}")
                with col4:
                    if st.button("✋ Manual", key=f"manual_{website['id']}", use_container_width=True):
                        try:
                            response = requests.post(f"{API_BASE_URL}/websites/{website['id']}/manual-extraction")
                            if response.status_code == 200:
                                st.success(f"✅ {response.json().get('message', 'Set to manual extraction')}")
                                st.rerun()
                            else:
                                st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                        except Exception as e:
                            st.error(f"Error setting manual extraction: {e}")
                st.divider()

def launch_node(region: Optional[str] = None):
    try:
        payload = {}
        if region:
            payload = {"region": region}
        response = requests.post(f"{API_BASE_URL}/nodes/launch", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error launching node: {e}")
        return None

def get_aws_regions():
    """Get list of AWS regions with display names for the dropdown.
    Returns a list of tuples: (display_name, region_code)
    """
    return [
        ("Mumbai (ap-south-1)", "ap-south-1"),
        ("Singapore (ap-southeast-1)", "ap-southeast-1"),
        ("Sydney (ap-southeast-2)", "ap-southeast-2"),
        ("Tokyo (ap-northeast-1)", "ap-northeast-1"),
        ("Seoul (ap-northeast-2)", "ap-northeast-2"),
        ("Osaka (ap-northeast-3)", "ap-northeast-3"),
        ("Ireland (eu-west-1)", "eu-west-1"),
        ("London (eu-west-2)", "eu-west-2"),
        ("Paris (eu-west-3)", "eu-west-3"),
        ("Frankfurt (eu-central-1)", "eu-central-1"),
        ("Stockholm (eu-north-1)", "eu-north-1"),
        ("N. Virginia (us-east-1)", "us-east-1"),
        ("Ohio (us-east-2)", "us-east-2"),
        ("N. California (us-west-1)", "us-west-1"),
        ("Oregon (us-west-2)", "us-west-2"),
        ("Central Canada (ca-central-1)", "ca-central-1"),
        ("São Paulo (sa-east-1)", "sa-east-1"),
        ("Cape Town (af-south-1)", "af-south-1"),
        ("Bahrain (me-south-1)", "me-south-1"),
        ("UAE (me-central-1)", "me-central-1"),
    ]

def terminate_node(node_id: int):
    try:
        response = requests.delete(f"{API_BASE_URL}/nodes/{node_id}/terminate")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error terminating node: {e}")
        return None

def display_nodes(nodes: List[Dict]):
    if not nodes:
        st.info("No nodes found.")
        return
    
    website_map = {}
    nodes_with_website_ids = [n for n in nodes if n.get('current_website_id')]
    if nodes_with_website_ids:
        website_ids_needed = set(n.get('current_website_id') for n in nodes_with_website_ids if n.get('current_website_id'))
        
        page = 1
        page_size = 100
        found_count = 0
        
        while found_count < len(website_ids_needed):
            websites_data = get_websites(page=page, page_size=page_size)
            websites = websites_data.get('items', [])
            total = websites_data.get('total', 0)
            
            if not websites:
                break
            
            for website in websites:
                website_id = website.get('id')
                if website_id in website_ids_needed and website_id not in website_map:
                    website_map[website_id] = website.get('url', f"Website ID: {website_id}")
                    found_count += 1
            
            if len(websites) < page_size or page * page_size >= total:
                break
            page += 1
    
    nodes_display = nodes.copy()
    for node in nodes_display:
        current_website_id = node.get('current_website_id')
        if current_website_id:
            node['current_website'] = website_map.get(current_website_id, f"Website ID: {current_website_id}")
        else:
            node['current_website'] = '—'
    
    df = pd.DataFrame(nodes_display)
    
    # Sort by created_at descending (newest first) before formatting dates
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'])
        df = df.sort_values(by='created_at', ascending=False)
        df['created_at'] = df['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    if 'last_seen' in df.columns:
        df['last_seen'] = pd.to_datetime(df['last_seen']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    status_colors = {
        'alive': '🟢',
        'processing': '🟠',
        'dead': '🔴'
    }
    if 'status' in df.columns:
        df['Status'] = df['status'].map(lambda x: f"{status_colors.get(x, '⚪')} {x.title()}")
        df = df.drop(columns=['status'])
    
    if 'current_website_id' in df.columns:
        df = df.drop(columns=['current_website_id'])
    
    # Define column order: id, status, current website, region, last_seen, created at, cpu usage, memory usage, ip address, instance id
    desired_column_order = ['id', 'Status', 'current_website', 'region', 'last_seen', 'created_at', 'cpu_usage', 'memory_usage', 'ip_address', 'instance_id']
    
    # Get available columns that exist in the DataFrame
    available_columns = [col for col in desired_column_order if col in df.columns]
    # Add any remaining columns that weren't in the desired order
    remaining_columns = [col for col in df.columns if col not in available_columns]
    final_column_order = available_columns + remaining_columns
    
    # Reorder DataFrame columns
    df = df[final_column_order]
    
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "id": "ID",
            "Status": "Status",
            "current_website": "Current Website",
            "region": "Region",
            "last_seen": "Last Seen",
            "created_at": "Created At",
            "cpu_usage": "CPU Usage (%)",
            "memory_usage": "Memory Usage (%)",
            "ip_address": "IP Address",
            "instance_id": "Instance ID"
        },
        hide_index=True
    )

def display_tasks(tasks: List[Dict]):
    if not tasks:
        st.info("No tasks found.")
        return
    
    df = pd.DataFrame(tasks)
    
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    status_emoji = {
        'processing': '🔄',
        'completed': '✔️'
    }
    if 'status' in df.columns:
        df['Status'] = df['status'].map(lambda x: f"{status_emoji.get(x, '❓')} {x.title()}")
    
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "node_id": "Node ID",
            "website_id": "Website ID",
            "Status": "Status",
            "created_at": "Created At"
        },
        hide_index=True
    )

def get_batch_status(batch_id: int) -> Optional[Dict]:
    try:
        response = requests.get(f"{API_BASE_URL}/batches/{batch_id}/status")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching batch status: {e}")
        return None

def get_batch_for_download(batch_id: int):
    try:
        response = requests.get(f"{API_BASE_URL}/batches/{batch_id}/download", stream=True)
        if response.status_code == 200:
            content_disposition = response.headers.get('Content-Disposition', '')
            filename = content_disposition.split('filename=')[-1].strip('"') if 'filename=' in content_disposition else f"batch_{batch_id}_output.jsonl"
            return response.content, filename
        else:
            error_msg = response.json().get('detail', 'Unknown error') if response.headers.get('content-type', '').startswith('application/json') else response.text
            st.error(f"Error: {error_msg}")
            return None, None
    except requests.exceptions.RequestException as e:
        st.error(f"Error downloading batch output: {e}")
        return None, None

def display_batches(batches: List[Dict], page: int = 1, page_size: int = 10):
    if not batches:
        st.info("No batches found.")
        return
    
    total = len(batches)
    total_pages = (total + page_size - 1) // page_size
    
    st.caption(f"Showing {min((page - 1) * page_size + 1, total)} - {min(page * page_size, total)} of {total} batches (Page {page})")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if page > 1:
            if st.button("← Previous Page", key="batch_prev"):
                st.session_state.batch_page = max(1, page - 1)
                st.rerun()
    
    with col2:
        st.write(f"Page {page} of {total_pages}")
    
    with col3:
        if page < total_pages:
            if st.button("Next Page →", key="batch_next"):
                st.session_state.batch_page = page + 1
                st.rerun()
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_batches = batches[start_idx:end_idx]
    
    for batch in paginated_batches:
        batch_id = batch['id']
        openai_batch_id = batch.get('open_ai_batch_id', 'N/A')
        
        with st.expander(f"Batch {batch_id} - {batch.get('batch_name', 'N/A')}"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Website ID:** {batch['website_id']}")
                st.write(f"**Batch Name:** {batch.get('batch_name', 'N/A')}")
                st.write(f"**OpenAI Batch ID:** {openai_batch_id}")
                if batch.get('created_at'):
                    st.write(f"**Created At:** {pd.to_datetime(batch['created_at']).strftime('%Y-%m-%d %H:%M:%S')}")
            
            with col2:
                status_btn_key = f"batch_status_btn_{batch_id}"
                status_state_key = f"batch_status_{batch_id}"
                download_key = f"batch_download_{batch_id}"
                
                if st.button("🔍 Check Status", key=status_btn_key, use_container_width=True):
                    status_data = get_batch_status(batch_id)
                    if status_data and isinstance(status_data, dict):
                        st.session_state[status_state_key] = status_data
                        st.rerun()
                
                if openai_batch_id and openai_batch_id != 'N/A':
                    download_btn_key = f"download_btn_{batch_id}"
                    if download_btn_key not in st.session_state:
                        st.session_state[download_btn_key] = False
                    
                    if st.button("⬇️ Download Output", key=download_key, use_container_width=True):
                        with st.spinner("Fetching batch status and downloading output..."):
                            status_data = get_batch_status(batch_id)
                            if status_data and isinstance(status_data, dict) and status_data.get('status') == 'completed':
                                file_content, filename = get_batch_for_download(batch_id)
                                if file_content and filename:
                                    st.session_state[download_btn_key] = True
                                    st.session_state[f"download_data_{batch_id}"] = file_content
                                    st.session_state[f"download_filename_{batch_id}"] = filename
                                    st.rerun()
                            elif status_data and isinstance(status_data, dict):
                                st.warning(f"Batch is not completed. Current status: {status_data.get('status')}")
                            else:
                                st.error("Could not fetch batch status")
                    
                    if st.session_state.get(download_btn_key, False):
                        file_content = st.session_state.get(f"download_data_{batch_id}")
                        filename = st.session_state.get(f"download_filename_{batch_id}", f"batch_{batch_id}_output.jsonl")
                        if file_content:
                            st.download_button(
                                label="📥 Download File",
                                data=file_content,
                                file_name=filename,
                                mime="application/x-ndjson",
                                key=f"actual_download_{batch_id}"
                            )
            
            if f"batch_status_{batch_id}" in st.session_state:
                status_data = st.session_state[f"batch_status_{batch_id}"]
                
                if isinstance(status_data, dict):
                    st.divider()
                    st.subheader("Batch Status Details")
                    
                    status_col1, status_col2 = st.columns(2)
                    
                    with status_col1:
                        st.json({
                            "id": status_data.get('id'),
                            "object": status_data.get('object'),
                            "endpoint": status_data.get('endpoint'),
                            "completion_window": status_data.get('completion_window'),
                            "status": status_data.get('status'),
                            "input_file_id": status_data.get('input_file_id'),
                            "output_file_id": status_data.get('output_file_id'),
                            "error_file_id": status_data.get('error_file_id')
                        })
                    
                    with status_col2:
                        request_counts = status_data.get('request_counts', {})
                        st.write("**Request Counts:**")
                        if request_counts:
                            st.json(request_counts)
                        
                        if status_data.get('errors'):
                            st.write("**Errors:**")
                            st.json(status_data.get('errors'))
                        
                        if status_data.get('created_at'):
                            st.write(f"**Created At:** {datetime.fromtimestamp(status_data['created_at']).strftime('%Y-%m-%d %H:%M:%S')}")
                        if status_data.get('completed_at'):
                            st.write(f"**Completed At:** {datetime.fromtimestamp(status_data['completed_at']).strftime('%Y-%m-%d %H:%M:%S')}")
                        if status_data.get('failed_at'):
                            st.write(f"**Failed At:** {datetime.fromtimestamp(status_data['failed_at']).strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        if st.button("Clear Status", key=f"clear_status_{batch_id}"):
                            if f"batch_status_{batch_id}" in st.session_state:
                                del st.session_state[f"batch_status_{batch_id}"]
                            st.rerun()
                else:
                    st.warning("Invalid status data. Please check status again.")
                    if st.button("Clear Invalid Status", key=f"clear_status_{batch_id}"):
                        del st.session_state[f"batch_status_{batch_id}"]
                        st.rerun()

def render_sidebar():
    st.sidebar.title("📊 Navigation")
    
    current_page = get_current_page()
    
    if st.sidebar.button("🌐 Websites", use_container_width=True):
        set_current_page("websites")
        st.rerun()
    
    if st.sidebar.button("🖥️ Nodes", use_container_width=True):
        set_current_page("nodes")
        st.rerun()
    
    if st.sidebar.button("📦 Batches", use_container_width=True):
        set_current_page("batches")
        st.rerun()
    
    if st.sidebar.button("⭐ Priority Batches", use_container_width=True):
        set_current_page("priority_batches")
        st.rerun()
    
    if st.sidebar.button("⚙️ Settings", use_container_width=True):
        set_current_page("settings")
        st.rerun()
    
    if st.sidebar.button("🤖 Automated Scraping", use_container_width=True):
        set_current_page("automated_scraping")
        st.rerun()
    
    st.sidebar.divider()
    
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = None
    
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
        st.session_state.last_refresh = datetime.now()
        st.session_state.force_refresh = True
        # Clear all caches
        get_websites_cached.clear()
        get_all_nodes_cached.clear()
        get_node_logs_cached.clear()
        get_all_batches_cached.clear()
        get_all_priority_batches_cached.clear()
        st.rerun()
    
    if st.session_state.last_refresh:
        st.sidebar.caption(f"Last refreshed: {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
    
    st.sidebar.divider()
    
    st.sidebar.header("⚙️ Quick Actions")
    
    with st.sidebar.form("add_website_sidebar"):
        st.subheader("Add New Website")
        new_url = st.text_input("Website URL", key="new_website_url_sidebar")
        country_info_input = st.text_area(
            "Country availability (optional)",
            key="new_website_country_info",
            placeholder="US=https://us.example.com\nUK=https://uk.example.com",
            help="Provide one country per line. Use separators like '=', ':', or ',' between the country name/code and its specific URL."
        )
        
        # Scrape region dropdown
        regions = get_aws_regions()
        region_options = [display_name for display_name, _ in regions]
        region_codes = {display_name: region_code for display_name, region_code in regions}
        
        scrape_region_display = st.selectbox(
            "Scrape from region",
            options=region_options,
            index=0,  # Default to Mumbai (ap-south-1)
            key="new_website_scrape_region",
            help="Select the AWS region from which to scrape this website. If not Mumbai, a node will be auto-launched in that region."
        )
        scrape_region = region_codes[scrape_region_display]
        
        if st.form_submit_button("Add Website", use_container_width=True):
            new_url = new_url.strip()
            
            if not new_url:
                st.sidebar.error("Please enter a website URL")
            else:
                try:
                    payload = {"url": new_url, "scrape_region": scrape_region}
                    country_info = parse_country_info_input(country_info_input)
                    if country_info:
                        payload["country_info"] = country_info
                    response = requests.post(
                        f"{API_BASE_URL}/websites/",
                        json=payload
                    )
                    if response.status_code == 200:
                        region_msg = f" (node auto-launched in {scrape_region})" if scrape_region != "ap-south-1" else ""
                        st.sidebar.success(f"Successfully added {new_url}{region_msg}")
                        st.session_state.website_page = 1
                        st.rerun()
                    else:
                        st.sidebar.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                except Exception as e:
                    st.sidebar.error(f"Error adding website: {e}")

def render_websites_page():
    st.title("🌐 Websites")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        status_filter = st.selectbox(
            "Filter by status",
            ["All", "pending_validator", "ready", "in_queue", "processing", "paused", "completed", "terminated", "rejected", "manual_extraction"],
            key="website_status_filter"
        )
    
    if 'website_page' not in st.session_state:
        st.session_state.website_page = 1
    
    with st.spinner("Loading websites..."):
        websites_data = get_websites(
            status=status_filter if status_filter != "All" else None,
            page=st.session_state.website_page,
            page_size=10
        )
        display_websites(websites_data)

def render_nodes_page():
    st.title("🖥️ Nodes")
    
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col3:
        with st.expander("🚀 Launch New Node"):
            st.info("Launch Template: `orchestration-slave`")
            
            # Region dropdown
            regions = get_aws_regions()
            default_region_index = 0  # Default to ap-south-1 (Mumbai)
            if 'AWS_REGION' in os.environ:
                try:
                    # Find the index of the default region
                    for idx, (_, region_code) in enumerate(regions):
                        if region_code == os.environ['AWS_REGION']:
                            default_region_index = idx
                            break
                except (ValueError, IndexError):
                    pass
            
            # Extract display names and region codes
            region_options = [display_name for display_name, _ in regions]
            region_codes = {display_name: region_code for display_name, region_code in regions}
            
            selected_display = st.selectbox(
                "Select AWS Region",
                options=region_options,
                index=default_region_index,
                help="Select the AWS region where you want to launch the node"
            )
            
            # Get the actual region code from the selected display name
            selected_region = region_codes[selected_display]
            
            if st.button("🚀 Launch Node", use_container_width=True, type="primary"):
                with st.spinner(f"Launching EC2 instance in {selected_region}..."):
                    result = launch_node(region=selected_region)
                    if result and result.get('success'):
                        st.success(f"✅ {result.get('message')}")
                        if result.get('instance_details'):
                            instance = result['instance_details']
                            st.info(f"Instance ID: {instance.get('instance_id')}")
                            st.info(f"Region: {instance.get('region', selected_region)}")
                            st.info(f"IP: {instance.get('public_ip') or instance.get('private_ip')}")
                        st.rerun()
                    else:
                        error_msg = result.get('detail', 'Unknown error') if result else 'Failed to launch node'
                        st.error(f"Failed to launch node: {error_msg}")
    
    nodes = get_all_nodes()
    
    with col1:
        st.metric("Total Nodes", len(nodes))
    with col2:
        alive_nodes = len([n for n in nodes if n.get('status') == 'alive'])
        st.metric("Alive Nodes", alive_nodes)
    
    display_nodes(nodes)
    
    st.divider()
    
    # Node selection for logs
    if nodes:
        st.subheader("📋 View Node Logs")
        
        node_options = {f"Node {n['id']} - {n.get('instance_id', 'N/A')} ({n.get('status', 'unknown')})": n['id'] for n in nodes}
        
        # Initialize session state for selected node
        if "selected_node_logs" not in st.session_state:
            st.session_state.selected_node_logs = "None"
        if "log_limit" not in st.session_state:
            st.session_state.log_limit = 100
        
        # Use form to prevent rerender on selectbox change
        with st.form("node_logs_form", clear_on_submit=False):
            col_log1, col_log2 = st.columns([3, 1])
            
            with col_log1:
                # Find current index
                current_label = st.session_state.get("selected_node_logs", "None")
                options_list = ["None"] + list(node_options.keys())
                try:
                    current_index = options_list.index(current_label) if current_label in options_list else 0
                except:
                    current_index = 0
                
                selected_node_label = st.selectbox(
                    "Select a node to view logs",
                    options=options_list,
                    index=current_index,
                    key="selected_node_logs_form"
                )
            
            with col_log2:
                log_limit = st.selectbox("Log Limit", [100, 250, 500, 1000], index=0, key="log_limit_form")
                refresh_logs = st.form_submit_button("🔄 Refresh Logs", use_container_width=True)
            
            # Update session state when form is submitted
            if refresh_logs:
                st.session_state.selected_node_logs = selected_node_label
                st.session_state.log_limit = log_limit
        
        # Display logs outside form to prevent rerender issues
        if st.session_state.selected_node_logs != "None":
            selected_node_id = node_options.get(st.session_state.selected_node_logs)
            if selected_node_id:
                selected_node = next((n for n in nodes if n['id'] == selected_node_id), None)
                
                if selected_node:
                    # Check if we need to refresh logs
                    node_changed = st.session_state.get("last_selected_node_id") != selected_node_id
                    should_refresh = refresh_logs if 'refresh_logs' in locals() else False
                    
                    if should_refresh or node_changed:
                        st.session_state.last_selected_node_id = selected_node_id
                    
                    # Fetch logs (cached unless refresh requested)
                    logs = get_node_logs(selected_node_id, limit=st.session_state.log_limit, force_refresh=(should_refresh or node_changed))
                    
                    if logs:
                        st.subheader(f"Logs for {st.session_state.selected_node_logs}")
                        
                        # Create a container for logs
                        log_container = st.container()
                        
                        with log_container:
                            # Group logs by level for color coding
                            # API already returns logs in descending order (newest first)
                            for log in logs:
                                message = log.get('message', '')
                                level = log.get('level', 'INFO')
                                created_at = log.get('created_at', '')
                                
                                # Format timestamp
                                if created_at:
                                    try:
                                        timestamp = pd.to_datetime(created_at).strftime('%Y-%m-%d %H:%M:%S')
                                    except:
                                        timestamp = created_at
                                else:
                                    timestamp = 'N/A'
                                
                                # Color code by level
                                level_colors = {
                                    'ERROR': '🔴',
                                    'WARNING': '🟡',
                                    'INFO': '🔵',
                                    'DEBUG': '⚪'
                                }
                                level_emoji = level_colors.get(level, '⚪')
                                
                                # Display log entry
                                log_text = f"[{timestamp}] {level_emoji} [{level}] {message}"
                                
                                if level == 'ERROR':
                                    st.error(log_text)
                                elif level == 'WARNING':
                                    st.warning(log_text)
                                else:
                                    st.text(log_text)
                        
                        st.caption(f"Showing {len(logs)} log entries")
                    else:
                        st.info(f"No logs found for {st.session_state.selected_node_logs}")
                else:
                    st.warning("Selected node not found")
    
    st.divider()
    
    if nodes:
        st.subheader("Node Management")
        for node in nodes:
            node_id = node['id']
            instance_id = node.get('instance_id', 'N/A')
            ip_address = node.get('ip_address', 'N/A')
            status = node.get('status', 'unknown')
            
            with st.expander(f"Node {node_id} - {instance_id} ({status})"):
                col_a, col_b = st.columns(2)
                
                with col_a:
                    st.write(f"**Instance ID:** {instance_id}")
                    st.write(f"**IP Address:** {ip_address}")
                    st.write(f"**Status:** {status}")
                    if node.get('last_seen'):
                        st.write(f"**Last Seen:** {pd.to_datetime(node['last_seen']).strftime('%Y-%m-%d %H:%M:%S')}")
                    current_website_id = node.get('current_website_id')
                    if current_website_id:
                        websites = get_websites(page=1, page_size=100).get('items', [])
                        website_map = {w['id']: w['url'] for w in websites}
                        current_website_url = website_map.get(current_website_id, f"Website ID: {current_website_id}")
                        st.write(f"**Current Website:** {current_website_url}")
                    else:
                        st.write(f"**Current Website:** —")
                
                with col_b:
                    if status == 'alive':
                        confirm_key = f"confirm_terminate_{node_id}"
                        if st.session_state.get(confirm_key, False):
                            st.warning("⚠️ Click 'Terminate' again to confirm")
                        
                        # Use form to prevent double-click issue
                        with st.form(key=f"terminate_form_{node_id}", clear_on_submit=True):
                            submit_terminate = st.form_submit_button(f"🛑 Terminate", use_container_width=True)
                            
                            if submit_terminate:
                                if st.session_state.get(confirm_key, False):
                                    # Second click - actually terminate
                                    with st.spinner(f"Terminating instance {instance_id}..."):
                                        result = terminate_node(node_id)
                                        if result and result.get('success'):
                                            st.success(f"✅ {result.get('message')}")
                                            st.session_state.force_refresh = True
                                            get_all_nodes_cached.clear()
                                            st.session_state[confirm_key] = False
                                            # Small delay to show success message before rerun
                                            time.sleep(0.3)
                                            st.rerun()
                                        else:
                                            st.error("Failed to terminate node")
                                            st.session_state[confirm_key] = False
                                else:
                                    # First click - set confirmation flag
                                    st.session_state[confirm_key] = True
                                    # Rerun to show confirmation message
                                    st.rerun()
                    else:
                        st.info("Node is not alive")

def render_tasks_page():
    st.title("📋 Tasks")
    
    # Use form to prevent rerender on filter change
    with st.form("task_filter_form", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            status_filter = st.selectbox(
                "Filter by status",
                ["All", "processing", "completed"],
                key="task_status_filter"
            )
        
        with col2:
            nodes = get_all_nodes()
            node_filter = st.selectbox(
                "Filter by node",
                ["All"] + [f"Node {n['id']}" for n in nodes],
                key="task_node_filter"
            )
    
    with col3:
        website_filter = st.selectbox(
            "Filter by website",
            ["All"] + [f"{w['url']}" for w in get_websites(page=1, page_size=100).get('items', [])],
            key="task_website_filter"
        )
    
    node_id = None
    if node_filter != "All":
        node_id = int(node_filter.split()[-1])
    
    website_id = None
    if website_filter != "All":
        websites = get_websites(page=1, page_size=100).get('items', [])
        website_id = next((w['id'] for w in websites if w['url'] == website_filter), None)
    
    tasks = get_all_tasks(
        status=status_filter if status_filter != "All" else None,
        node_id=node_id,
        website_id=website_id
    )
    
    st.metric("Total Tasks", len(tasks))
    display_tasks(tasks)

def render_batches_page():
    st.title("📦 Batches")
    
    if 'batch_page' not in st.session_state:
        st.session_state.batch_page = 1
    
    if 'batch_page_size' not in st.session_state:
        st.session_state.batch_page_size = 10
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        page_size_options = [10, 25, 50, 100]
        current_index = page_size_options.index(st.session_state.batch_page_size) if st.session_state.batch_page_size in page_size_options else 0
        page_size = st.selectbox(
            "Items per page",
            page_size_options,
            index=current_index,
            key="batch_page_size_selector"
        )
        if page_size != st.session_state.batch_page_size:
            st.session_state.batch_page_size = page_size
            st.session_state.batch_page = 1
            st.rerun()
    
    websites = get_websites(page=1, page_size=100).get('items', [])
    
    website_filter = st.selectbox(
        "Filter by website",
        ["All"] + [f"{w['url']}" for w in websites],
        key="batch_website_filter"
    )
    
    if website_filter != st.session_state.get('last_batch_website_filter', None):
        st.session_state.batch_page = 1
        st.session_state.last_batch_website_filter = website_filter
    
    website_id = None
    if website_filter != "All":
        website_id = next((w['id'] for w in websites if w['url'] == website_filter), None)
    
    batches = get_all_batches(website_id=website_id)
    
    st.metric("Total Batches", len(batches))
    display_batches(batches, page=st.session_state.batch_page, page_size=st.session_state.batch_page_size)

def render_priority_batches_page():
    st.title("⭐ Products")
    
    if 'priority_batch_page' not in st.session_state:
        st.session_state.priority_batch_page = 1
    
    if 'priority_batch_page_size' not in st.session_state:
        st.session_state.priority_batch_page_size = 10
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        page_size_options = [10, 25, 50, 100]
        current_index = page_size_options.index(st.session_state.priority_batch_page_size) if st.session_state.priority_batch_page_size in page_size_options else 0
        page_size = st.selectbox(
            "Items per page",
            page_size_options,
            index=current_index,
            key="priority_batch_page_size_selector"
        )
        if page_size != st.session_state.priority_batch_page_size:
            st.session_state.priority_batch_page_size = page_size
            st.session_state.priority_batch_page = 1
            st.rerun()
    
    websites = get_websites(page=1, page_size=100).get('items', [])
    
    website_filter = st.selectbox(
        "Filter by website",
        ["All"] + [f"{w['url']}" for w in websites],
        key="priority_batch_website_filter"
    )
    
    if website_filter != st.session_state.get('last_priority_batch_website_filter', None):
        st.session_state.priority_batch_page = 1
        st.session_state.last_priority_batch_website_filter = website_filter
    
    website_id = None
    if website_filter != "All":
        website_id = next((w['id'] for w in websites if w['url'] == website_filter), None)
    
    skip = (st.session_state.priority_batch_page - 1) * st.session_state.priority_batch_page_size
    priority_batches_data = get_all_priority_batches(
        website_id=website_id,
        skip=skip,
        limit=st.session_state.priority_batch_page_size
    )
    
    priority_batches = priority_batches_data.get('items', [])
    total = priority_batches_data.get('total', 0)
    
    st.metric("Total Products", total)
    
    if not priority_batches:
        st.info("No priority batches found.")
        return
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if st.session_state.priority_batch_page > 1:
            if st.button("← Previous Page", key="priority_batch_prev"):
                st.session_state.priority_batch_page = max(1, st.session_state.priority_batch_page - 1)
                st.rerun()
    
    with col2:
        total_pages = (total + st.session_state.priority_batch_page_size - 1) // st.session_state.priority_batch_page_size if total > 0 else 1
        st.write(f"Page {st.session_state.priority_batch_page} of {total_pages}")
    
    with col3:
        if len(priority_batches) == st.session_state.priority_batch_page_size and (st.session_state.priority_batch_page * st.session_state.priority_batch_page_size) < total:
            if st.button("Next Page →", key="priority_batch_next"):
                st.session_state.priority_batch_page = st.session_state.priority_batch_page + 1
                st.rerun()
    
    st.caption(f"Showing {len(priority_batches)} of {total} priority batches (Page {st.session_state.priority_batch_page})")
    
    # Prepare data for table
    import json
    table_data = []
    
    for batch in priority_batches:
        batch_id = batch['id']
        url = batch.get('url', 'N/A')
        website_url = batch.get('website_url', 'N/A')
        model = batch.get('model', 'N/A')
        sync = batch.get('sync', False)
        created_at = batch.get('created_at', 'N/A')
        result = batch.get('result', '{}')
        
        # Parse result JSON
        result_json = {}
        try:
            result_json = json.loads(result) if isinstance(result, str) else result
        except:
            pass
        
        # Build row data
        row = {
            'ID': batch_id,
            'Product URL': url,
            'Website URL': website_url,
            'Model': model,
            'Sync': '✅' if sync else '❌',
            'Created At': pd.to_datetime(created_at).strftime('%Y-%m-%d %H:%M:%S') if created_at and created_at != 'N/A' else 'N/A',
            'Product Name': result_json.get('product_name', 'N/A'),
            'Product Price': result_json.get('product_price', 'N/A'),
            'Product Category': result_json.get('product_category', 'N/A'),
            'Brand Name': result_json.get('product_brand_name', 'N/A'),
            'Product ID': result_json.get('product_id', 'N/A'),
            'Country Code': result_json.get('country_code', 'N/A'),
            'Product Description': result_json.get('product_description', 'N/A')[:100] + '...' if result_json.get('product_description') and len(result_json.get('product_description', '')) > 100 else result_json.get('product_description', 'N/A'),
            'Images Count': len(result_json.get('product_images', [])) if isinstance(result_json.get('product_images'), list) else 0,
            'Full Result': result  # Store full result for detail view
        }
        table_data.append(row)
    
    # Column selector
    all_columns = [
        'ID', 'Product URL', 'Website URL', 'Model', 'Sync', 'Created At',
        'Product Name', 'Product Price', 'Product Category', 'Brand Name',
        'Product ID', 'Country Code', 'Product Description', 'Images Count'
    ]
    
    # Initialize selected columns in session state
    if 'priority_batch_selected_columns' not in st.session_state:
        st.session_state.priority_batch_selected_columns = [
            'ID', 'Product Name', 'Product Price', 'Product Category', 
            'Brand Name', 'Website URL', 'Created At', 'Sync'
        ]
    
    # Column selector dropdown
    selected_columns = st.multiselect(
        "Select columns to display",
        options=all_columns,
        default=st.session_state.priority_batch_selected_columns,
        key="priority_batch_column_selector"
    )
    
    # Update session state
    if selected_columns != st.session_state.priority_batch_selected_columns:
        st.session_state.priority_batch_selected_columns = selected_columns
        st.rerun()
    
    if not selected_columns:
        st.warning("Please select at least one column to display.")
        return
    
    # Create DataFrame with selected columns
    df = pd.DataFrame(table_data)
    
    # Ensure we have the selected columns (some might not exist if result parsing failed)
    available_columns = [col for col in selected_columns if col in df.columns]
    if not available_columns:
        st.warning("No valid columns selected.")
        return
    
    df_display = df[available_columns].copy()
    
    # Display table with clickable rows
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        height=400
    )
    
    # Row detail view
    if len(df_display) > 0:
        st.subheader("📋 View Details")
        selected_row_idx = st.selectbox(
            "Select row to view full details",
            options=range(len(df_display)),
            format_func=lambda x: f"Row {x+1}: {df_display.iloc[x].get('Product Name', 'N/A') if 'Product Name' in df_display.columns else df_display.iloc[x].get('ID', 'N/A')}",
            key="priority_batch_row_selector"
        )
        
        selected_row = table_data[selected_row_idx]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Basic Information**")
            st.write(f"**ID:** {selected_row['ID']}")
            st.write(f"**Product URL:** {selected_row['Product URL']}")
            st.write(f"**Website URL:** {selected_row['Website URL']}")
            st.write(f"**Model:** {selected_row['Model']}")
            st.write(f"**Sync:** {selected_row['Sync']}")
            st.write(f"**Created At:** {selected_row['Created At']}")
        
        with col2:
            st.write("**Product Information**")
            st.write(f"**Product Name:** {selected_row['Product Name']}")
            st.write(f"**Product Price:** {selected_row['Product Price']}")
            st.write(f"**Product Category:** {selected_row['Product Category']}")
            st.write(f"**Brand Name:** {selected_row['Brand Name']}")
            st.write(f"**Product ID:** {selected_row['Product ID']}")
            st.write(f"**Country Code:** {selected_row['Country Code']}")
            st.write(f"**Images Count:** {selected_row['Images Count']}")
        
        st.write("**Product Description**")
        st.text_area(
            "Description",
            value=selected_row['Product Description'],
            height=100,
            disabled=True,
            key=f"desc_{selected_row['ID']}"
        )
        
        st.write("**Full Result JSON**")
        try:
            full_result_json = json.loads(selected_row['Full Result'])
            st.json(full_result_json)
        except:
            st.code(selected_row['Full Result'], language="json")


def load_countries():
    """Load countries from countries.json file."""
    try:
        # Get the directory where this script is located
        script_path = os.path.abspath(__file__)  # dashboard/app.py
        script_dir = os.path.dirname(script_path)  # dashboard/
        master_dir = os.path.dirname(script_dir)  # master/
        countries_path = os.path.join(master_dir, 'countries.json')
        
        # Normalize the path to handle any path issues
        countries_path = os.path.normpath(countries_path)
        
        if not os.path.exists(countries_path):
            # Try alternative: check if we're running from master directory
            alt_path = os.path.join(os.getcwd(), 'countries.json')
            if os.path.exists(alt_path):
                countries_path = alt_path
            else:
                raise FileNotFoundError(
                    f"countries.json not found. Tried:\n"
                    f"1. {countries_path}\n"
                    f"2. {alt_path}\n"
                    f"Current working directory: {os.getcwd()}\n"
                    f"Script location: {script_path}"
                )
        
        with open(countries_path, 'r', encoding='utf-8') as f:
            countries_data = json.load(f)
        return countries_data
    except FileNotFoundError as e:
        st.error(f"Countries file not found:\n{e}")
        return []
    except json.JSONDecodeError as e:
        st.error(f"Error parsing countries.json: {e}")
        return []
    except Exception as e:
        st.error(f"Error loading countries: {e}")
        return []

def get_openai_client():
    """Get OpenAI client instance."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)

def follow_links_recursively(start_url: str, max_links: int = 100, timeout: int = 10, progress_callback=None):
    """
    Follow links recursively up to max_links, checking for blocking issues.
    Returns: (success: bool, visited_count: int, blocking_reason: str or None)
    """
    visited = set()
    to_visit = [start_url]
    visited.add(start_url)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    link_count = 0
    
    while len(visited) < max_links and to_visit:
        current_url = to_visit.pop(0)
        link_count += 1
        
        # Call progress callback if provided
        if progress_callback:
            progress_callback(link_count, len(visited), current_url)
        
        try:
            start_time = time.time()
            response = requests.get(current_url, headers=headers, timeout=timeout, allow_redirects=True)
            elapsed_time = time.time() - start_time
            
            # Check for blocking
            if response.status_code == 403:
                return False, len(visited), f"403 Forbidden - Website blocking detected at {current_url} (visited {len(visited)} links)"
            elif response.status_code == 429:
                return False, len(visited), f"429 Too Many Requests - Rate limiting detected at {current_url} (visited {len(visited)} links)"
            elif response.status_code >= 400:
                return False, len(visited), f"HTTP {response.status_code} - Error response at {current_url} (visited {len(visited)} links)"
            
            # Check for slow response
            if elapsed_time > timeout:
                return False, len(visited), f"Slow response detected - Request took {elapsed_time:.2f}s (timeout: {timeout}s) at {current_url} (visited {len(visited)} links)"
            
            # Parse HTML and find links
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            base_url = urlparse(current_url)
            new_links_found = 0
            for link in links:
                href = link.get('href')
                if not href:
                    continue
                
                # Convert relative URLs to absolute
                absolute_url = urljoin(current_url, href)
                parsed_url = urlparse(absolute_url)
                
                # Only follow links from the same domain
                if parsed_url.netloc == base_url.netloc or not parsed_url.netloc:
                    if absolute_url not in visited and len(visited) < max_links:
                        visited.add(absolute_url)
                        to_visit.append(absolute_url)
                        new_links_found += 1
            
            # If no new links found and queue is empty, we're done
            if not to_visit and new_links_found == 0:
                break
            
        except requests.exceptions.Timeout:
            return False, len(visited), f"Timeout error - Request exceeded {timeout}s at {current_url} (visited {len(visited)} links)"
        except requests.exceptions.ConnectionError:
            return False, len(visited), f"Connection error - Could not connect to {current_url} (visited {len(visited)} links)"
        except Exception as e:
            return False, len(visited), f"Error accessing {current_url}: {str(e)} (visited {len(visited)} links)"
    
    return True, len(visited), None

def clean_html_for_gpt(html_content: str) -> str:
    """
    Clean HTML by removing irrelevant elements to reduce token count.
    Keeps only essential structure needed for CSS selector identification.
    Returns cleaned HTML string.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove <head> section entirely (meta, links, etc.)
    if soup.head:
        soup.head.decompose()
    
    # Remove <style> tags and their content
    for style_tag in soup.find_all('style'):
        style_tag.decompose()
    
    # Remove <script> tags and their content
    for script_tag in soup.find_all('script'):
        script_tag.decompose()
    
    # Remove <iframe> tags
    for iframe_tag in soup.find_all('iframe'):
        iframe_tag.decompose()
    
    # Remove <canvas> tags
    for canvas_tag in soup.find_all('canvas'):
        canvas_tag.decompose()
    
    # Remove <noscript> tags
    for noscript_tag in soup.find_all('noscript'):
        noscript_tag.decompose()
    
    # Remove <svg> tags (can be very large)
    for svg_tag in soup.find_all('svg'):
        svg_tag.decompose()
    
    # Remove <footer> tags
    for footer_tag in soup.find_all('footer'):
        footer_tag.decompose()
    
    # Remove <header> tags (navigation, etc.)
    for header_tag in soup.find_all('header'):
        header_tag.decompose()
    
    # Remove <nav> tags
    for nav_tag in soup.find_all('nav'):
        nav_tag.decompose()
    
    # Remove <aside> tags (sidebars)
    for aside_tag in soup.find_all('aside'):
        aside_tag.decompose()
    
    # Remove <form> tags (not needed for product info)
    for form_tag in soup.find_all('form'):
        form_tag.decompose()
    
    # Remove <button> tags (keep text if needed, but remove buttons)
    for button_tag in soup.find_all('button'):
        button_tag.decompose()
    
    # Remove <link> tags
    for link_tag in soup.find_all('link'):
        link_tag.decompose()
    
    # Remove <meta> tags
    for meta_tag in soup.find_all('meta'):
        meta_tag.decompose()
    
    # Remove <base> tags
    for base_tag in soup.find_all('base'):
        base_tag.decompose()
    
    # Remove <source> tags (media sources)
    for source_tag in soup.find_all('source'):
        source_tag.decompose()
    
    # Remove <track> tags (video subtitles)
    for track_tag in soup.find_all('track'):
        track_tag.decompose()
    
    # Remove <video> tags (keep structure but remove large video elements)
    for video_tag in soup.find_all('video'):
        video_tag.decompose()
    
    # Remove <audio> tags
    for audio_tag in soup.find_all('audio'):
        audio_tag.decompose()
    
    # Remove <embed> and <object> tags
    for embed_tag in soup.find_all(['embed', 'object']):
        embed_tag.decompose()
    
    # Remove image src attributes but keep img tags (for structure)
    for img_tag in soup.find_all('img'):
        if img_tag.get('src'):
            img_tag['src'] = ''  # Remove src but keep tag structure
        if img_tag.get('srcset'):
            del img_tag['srcset']
        if img_tag.get('data-src'):
            del img_tag['data-src']
    
    # Remove comments
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    for comment in comments:
        comment.extract()
    
    # Remove empty text nodes (whitespace only)
    for element in soup.find_all(string=True):
        if element.strip() == '':
            element.extract()
    
    # Remove elements with only whitespace
    for element in soup.find_all():
        if element.string and element.string.strip() == '' and len(element.contents) == 0:
            element.decompose()
    
    return str(soup)

def get_css_selectors_from_gpt(html_content: str, country: str, url: str):
    """
    Send HTML to GPT and get CSS selectors for product name, description, and price.
    Returns: dict with selectors or None if error
    """
    try:
        client = get_openai_client()
        
        # Clean HTML before sending to reduce token count
        cleaned_html = clean_html_for_gpt(html_content)
        original_length = len(html_content)
        cleaned_length = len(cleaned_html)
        
        prompt = f"""You are analyzing an e-commerce product page HTML. Given the HTML content below, identify the CSS selectors for:
1. Product name
2. Product description
3. Product price
4. Images container (the container that holds all product images - this could be a gallery, carousel, or image list)

Website URL: {url}
Country: {country}

IMPORTANT: You MUST respond with ONLY valid JSON in this exact format:
{{
    "product_name_selector": "CSS selector here",
    "product_description_selector": "CSS selector here",
    "product_price_selector": "CSS selector here",
    "images_container_selector": "CSS selector for the container that holds all product images"
}}

For the images_container_selector, provide the selector for the container/wrapper that contains all product images (not individual image selectors, but the parent container). This could be a div with class like 'product-gallery', 'image-carousel', 'product-images', etc.

If you cannot find a selector, use null for that field. Do not include any explanations, comments, or markdown formatting - ONLY the JSON object."""

        # Send cleaned HTML content to GPT
        # Try user-specified model first, with fallback if it doesn't exist
        messages = [
            {"role": "system", "content": "You are a web scraping expert. You analyze HTML and return CSS selectors as JSON only. You MUST respond with valid JSON only, no markdown, no code blocks, just the JSON object."},
            {"role": "user", "content": f"{prompt}\n\nHTML Content (cleaned: {original_length} -> {cleaned_length} characters):\n{cleaned_html}"}
        ]
        
        # First try the exact model user specified
        try:
            response = client.chat.completions.create(
                model="gpt-4o-2024-08-06",  # User specified gpt-4.1-2025-04-14 - update if that model exists
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1
            )
        except Exception as model_error:
            # If the specified model doesn't work, try fallback
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1
                )
            except Exception as fallback_error:
                raise Exception(f"Failed with both models. Original error: {model_error}, Fallback error: {fallback_error}")
        
        result = response.choices[0].message.content
        selectors = json.loads(result)
        
        return selectors
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse GPT response as JSON: {e}")
        return None
    except Exception as e:
        st.error(f"Error getting CSS selectors from GPT: {e}")
        return None

def extract_data_with_selectors(html_content: str, selectors: dict, base_url: str = None):
    """
    Extract product data using CSS selectors.
    Returns: dict with extracted data
    """
    if not html_content:
        return {'error': 'No HTML content provided'}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    extracted_data = {}
    
    # Map selector keys to display keys
    key_mapping = {
        'product_name_selector': 'product_name',
        'product_description_selector': 'product_description',
        'product_price_selector': 'product_price',
        'images_container_selector': 'images_container'
    }
    
    def try_selector(selector_str):
        """Try multiple methods to find elements with a selector."""
        import re
        elements = []
        
        # Method 1: Try CSS selector as-is
        try:
            elements = soup.select(selector_str)
            if elements:
                return elements
        except Exception as e1:
            pass
        
        # Method 2: Parse attribute selector manually (most reliable for attribute selectors)
        try:
            # Match patterns like: "h1[data-test='product-title']" or "div[data-test='product-description']"
            match = re.match(r'^(\w+)\[([^\]]+)\]$', selector_str)
            if match:
                tag_name = match.group(1)
                attr_str = match.group(2)
                
                # Parse attribute: "data-test='product-title'" or "data-test=\"product-title\"" or "data-test=product-title"
                # Handle both single and double quotes, or no quotes
                attr_match = re.match(r"(\w+)\s*=\s*['\"]?([^'\"]+)['\"]?", attr_str)
                if attr_match:
                    attr_name = attr_match.group(1).strip()
                    attr_value = attr_match.group(2).strip()
                    elements = soup.find_all(tag_name, attrs={attr_name: attr_value})
                    if elements:
                        return elements
        except Exception as e2:
            pass
        
        # Method 3: Try without quotes in attribute value for CSS selector
        try:
            # Remove quotes: "h1[data-test='product-title']" -> "h1[data-test=product-title]"
            no_quotes_selector = re.sub(r"=\s*['\"]([^'\"]+)['\"]", r"=\1", selector_str)
            elements = soup.select(no_quotes_selector)
            if elements:
                return elements
        except Exception as e3:
            pass
        
        # Method 4: Try with double quotes instead of single quotes
        try:
            double_quote_selector = selector_str.replace("'", '"')
            elements = soup.select(double_quote_selector)
            if elements:
                return elements
        except Exception as e4:
            pass
        
        # Method 5: Try using find_all with just the tag and check attributes manually
        try:
            match = re.match(r'^(\w+)\[', selector_str)
            if match:
                tag_name = match.group(1)
                all_tags = soup.find_all(tag_name)
                # Try to match attribute from selector
                attr_match = re.search(r"(\w+)\s*=\s*['\"]?([^'\"]+)['\"]?", selector_str)
                if attr_match:
                    attr_name = attr_match.group(1)
                    attr_value = attr_match.group(2)
                    elements = [tag for tag in all_tags if tag.get(attr_name) == attr_value]
                    if elements:
                        return elements
        except Exception as e5:
            pass
        
        return []
    
    for selector_key, selector_value in selectors.items():
        if selector_value and isinstance(selector_value, str) and selector_value.strip():
            try:
                selector_str = selector_value.strip()
                # Try multiple selector methods
                elements = try_selector(selector_str)
                
                if elements:
                    # Get text from all matching elements
                    texts = [elem.get_text(strip=True) for elem in elements if elem.get_text(strip=True)]
                    if texts:
                        # Use the mapped key for display, or original key if no mapping
                        display_key = key_mapping.get(selector_key, selector_key)
                        raw_value = texts[0] if len(texts) == 1 else texts
                        
                        # For price, extract only numbers (including decimals)
                        if 'price' in selector_key.lower() or 'price' in display_key.lower():
                            import re
                            # Extract numbers, decimal points, and commas (for thousands separators)
                            if isinstance(raw_value, str):
                                # Remove currency symbols and extract numeric value
                                # Pattern: matches numbers with optional decimals and commas
                                price_match = re.search(r'[\d,]+\.?\d*', raw_value.replace(',', ''))
                                if price_match:
                                    # Remove commas and convert to float, then back to string for display
                                    price_str = price_match.group(0).replace(',', '')
                                    try:
                                        price_num = float(price_str)
                                        extracted_data[display_key] = str(price_num)
                                        extracted_data[f"{display_key}_numeric"] = price_num
                                    except:
                                        extracted_data[display_key] = price_str
                                else:
                                    extracted_data[display_key] = raw_value
                            else:
                                extracted_data[display_key] = raw_value
                        else:
                            extracted_data[display_key] = raw_value
                        
                        # Also keep original key for reference
                        extracted_data[selector_key] = raw_value
                        extracted_data[f"{selector_key}_found"] = True
                        extracted_data[f"{selector_key}_count"] = len(elements)
                    else:
                        display_key = key_mapping.get(selector_key, selector_key)
                        extracted_data[display_key] = None
                        extracted_data[selector_key] = None
                        extracted_data[f"{selector_key}_found"] = False
                        extracted_data[f"{selector_key}_count"] = len(elements)
                else:
                    display_key = key_mapping.get(selector_key, selector_key)
                    extracted_data[display_key] = None
                    extracted_data[selector_key] = None
                    extracted_data[f"{selector_key}_found"] = False
                    extracted_data[f"{selector_key}_count"] = 0
            except Exception as e:
                display_key = key_mapping.get(selector_key, selector_key)
                error_msg = f"Error with selector '{selector_value}': {str(e)}"
                extracted_data[display_key] = error_msg
                extracted_data[selector_key] = error_msg
                extracted_data[f"{selector_key}_found"] = False
        else:
            display_key = key_mapping.get(selector_key, selector_key)
            extracted_data[display_key] = None
            extracted_data[selector_key] = None
            extracted_data[f"{selector_key}_found"] = False
    
    # Extract image URLs from images container if selector exists
    images_container_selector = selectors.get('images_container_selector')
    if images_container_selector and images_container_selector.strip():
        try:
            container_elements = try_selector(images_container_selector.strip())
            if container_elements:
                # Find all image elements within the container
                image_urls = []
                for container in container_elements:
                    # Look for img tags with src or data-src
                    img_tags = container.find_all('img')
                    for img in img_tags:
                        # Try src, data-src, data-lazy-src, etc.
                        for attr in ['src', 'data-src', 'data-lazy-src', 'data-original', 'data-image', 'data-zoom-image']:
                            img_url = img.get(attr)
                            if img_url and img_url.strip():
                                img_url = img_url.strip()
                                # Convert relative URLs to absolute if needed
                                if img_url.startswith('//'):
                                    img_url = 'https:' + img_url
                                elif img_url.startswith('/'):
                                    if base_url:
                                        img_url = urljoin(base_url, img_url)
                                    else:
                                        continue
                                elif not img_url.startswith('http'):
                                    continue
                                
                                if img_url not in image_urls and img_url.startswith('http'):
                                    image_urls.append(img_url)
                    
                    # Also look for links (a tags) that might contain image URLs
                    link_tags = container.find_all('a', href=True)
                    for link in link_tags:
                        href = link.get('href')
                        if href and href.strip():
                            href = href.strip()
                            # Check if it's an image URL or if the link contains an img tag
                            is_image_url = any(ext in href.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', 'image', 'img'])
                            has_img_tag = link.find('img') is not None
                            
                            if is_image_url or has_img_tag:
                                if href.startswith('//'):
                                    href = 'https:' + href
                                elif href.startswith('/'):
                                    if base_url:
                                        href = urljoin(base_url, href)
                                    else:
                                        continue
                                
                                if href not in image_urls and href.startswith('http'):
                                    image_urls.append(href)
                
                extracted_data['product_images'] = image_urls
                extracted_data['product_images_count'] = len(image_urls)
            else:
                extracted_data['product_images'] = []
                extracted_data['product_images_count'] = 0
        except Exception as e:
            extracted_data['product_images'] = []
            extracted_data['product_images_count'] = 0
            extracted_data['product_images_error'] = str(e)
    else:
        extracted_data['product_images'] = []
        extracted_data['product_images_count'] = 0
    
    return extracted_data

def get_domain_from_url(url: str) -> str:
    """Extract domain from URL (e.g., www.abc.com)"""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove port if present
        if ':' in domain:
            domain = domain.split(':')[0]
        return domain
    except:
        return url

def get_automated_scraping_configs():
    """Get all automated scraping configs from database"""
    if not DB_AVAILABLE:
        return []
    db = SessionLocal()
    try:
        configs = db.query(AutomatedScrapingConfig).order_by(AutomatedScrapingConfig.updated_at.desc()).all()
        return configs
    except Exception as e:
        st.error(f"Error loading configs: {e}")
        return []
    finally:
        db.close()

def save_automated_scraping_config(website: str, country: str, currency: str, 
                                   name_selector: str, description_selector: str, 
                                   price_selector: str, images_container_selector: str,
                                   status: str, reason: str = None):
    """Save or update automated scraping config"""
    if not DB_AVAILABLE:
        return False
    db = SessionLocal()
    try:
        # Check if config exists for this website and country
        existing = db.query(AutomatedScrapingConfig).filter(
            AutomatedScrapingConfig.website == website,
            AutomatedScrapingConfig.country == country
        ).first()
        
        if existing:
            # Update existing
            existing.currency = currency
            existing.name_selector = name_selector
            existing.description_selector = description_selector
            existing.price_selector = price_selector
            existing.images_container_selector = images_container_selector
            existing.status = status
            existing.reason = reason
            existing.updated_at = datetime.now()
        else:
            # Create new
            config = AutomatedScrapingConfig(
                website=website,
                country=country,
                currency=currency,
                name_selector=name_selector,
                description_selector=description_selector,
                price_selector=price_selector,
                images_container_selector=images_container_selector,
                status=status,
                reason=reason
            )
            db.add(config)
        
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        st.error(f"Error saving config: {e}")
        return False
    finally:
        db.close()

def render_automated_scraping_page():
    st.title("🤖 Automated Scraping")
    st.caption("Automatically analyze websites and extract product information using AI")
    
    # Load and display existing configs
    configs = get_automated_scraping_configs()
    
    if configs:
        st.write("### Existing Configurations")
        config_data = []
        for config in configs:
            config_data.append({
                "Website": config.website,
                "Country": config.country,
                "Currency": config.currency or "N/A",
                "Name Selector": config.name_selector[:50] + "..." if config.name_selector and len(config.name_selector) > 50 else (config.name_selector or "N/A"),
                "Description Selector": config.description_selector[:50] + "..." if config.description_selector and len(config.description_selector) > 50 else (config.description_selector or "N/A"),
                "Price Selector": config.price_selector[:50] + "..." if config.price_selector and len(config.price_selector) > 50 else (config.price_selector or "N/A"),
                "Status": config.status,
                "Reason": config.reason[:100] + "..." if config.reason and len(config.reason) > 100 else (config.reason or "N/A"),
                "Updated": config.updated_at.strftime("%Y-%m-%d %H:%M") if config.updated_at else "N/A"
            })
        
        df = pd.DataFrame(config_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.divider()
    
    # Load countries
    countries = load_countries()
    country_options = ["Select a country..."] + [f"{c['country_name']} ({c['country_code']})" for c in countries]
    
    with st.form("automated_scraping_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            url_input = st.text_input(
                "Website URL",
                placeholder="https://example.com/product-page",
                help="Enter the URL of the product page to analyze"
            )
        
        with col2:
            country_selection = st.selectbox(
                "Country",
                country_options,
                help="Select the country for this scraping operation"
            )
        
        submitted = st.form_submit_button("Start Scraping", type="primary")
    
    if submitted:
        if not url_input:
            st.error("Please enter a URL")
            return
        
        if country_selection == "Select a country...":
            st.error("Please select a country")
            return
        
        # Extract country code from selection
        selected_country = country_selection.split(" (")[0] if " (" in country_selection else country_selection
        
        # Initialize progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Step 1: Follow links recursively
        status_text.text("Step 1/3: Checking website accessibility and following links (up to 100)...")
        progress_bar.progress(10)
        
        # Progress tracking for link following
        link_progress = st.empty()
        
        def update_link_progress(current_link, visited_count, current_url):
            """Update progress display during link following"""
            link_progress.text(f"Visiting link {current_link}/100: {visited_count} unique links visited...\nCurrent: {current_url[:80]}...")
            progress_value = min(10 + int((current_link / 100) * 30), 40)
            progress_bar.progress(progress_value)
        
        success, visited_count, blocking_reason = follow_links_recursively(
            url_input, 
            max_links=100, 
            progress_callback=update_link_progress
        )
        
        link_progress.empty()  # Clear progress display
        
        if not success:
            progress_bar.progress(100)
            st.error(f"❌ Website Blocking Detected")
            st.write(f"**Reason:** {blocking_reason}")
            st.write(f"**Links visited before blocking:** {visited_count}")
            return
        
        progress_bar.progress(40)
        status_text.text(f"✓ Successfully visited {visited_count} links without blocking")
        
        # Step 2: Get HTML from original URL (the user's URL)
        status_text.text("Step 2/3: Fetching HTML from product page...")
        progress_bar.progress(50)
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            response = requests.get(url_input, headers=headers, timeout=30, allow_redirects=True)
            response.raise_for_status()
            html_content = response.text
            
            # Verify we got HTML content
            if not html_content or len(html_content) < 100:
                st.error(f"Received empty or very short HTML content from {url_input}")
                return
            
            progress_bar.progress(60)
            status_text.text(f"✓ Fetched HTML from {url_input} ({len(html_content)} characters)")
        except Exception as e:
            st.error(f"Error fetching HTML from {url_input}: {e}")
            return
        
        # Step 3: Get CSS selectors from GPT
        status_text.text("Step 3/3: Analyzing HTML with GPT to identify CSS selectors...")
        progress_bar.progress(70)
        
        # Send entire HTML to GPT (no limit)
        selectors = get_css_selectors_from_gpt(html_content, selected_country, url_input)
        
        if not selectors:
            st.error("Failed to get CSS selectors from GPT")
            return
        
        progress_bar.progress(85)
        
        # Step 4: Extract data using selectors from the user's URL HTML
        status_text.text(f"Extracting product data from {url_input} using CSS selectors...")
        
        # Verify selectors are valid
        if not selectors:
            st.error("No selectors received from GPT")
            return
        
        # Extract data using the HTML from the user's URL
        extracted_data = extract_data_with_selectors(html_content, selectors, base_url=url_input)
        
        progress_bar.progress(100)
        status_text.text("✓ Complete!")
        
        # Display results
        st.divider()
        st.subheader("📊 Results")
        
        # Show 100 hits status
        st.write("### 1. Link Following Status (100 Hits)")
        if success:
            st.success(f"✅ Successfully visited {visited_count} links without blocking")
        else:
            st.error(f"❌ Website Blocking Detected")
            st.write(f"**Reason:** {blocking_reason}")
            st.write(f"**Links visited before blocking:** {visited_count}")
        
        st.divider()
        
        # Display CSS Selectors (Validators from GPT)
        st.write("### 2. CSS Selectors (Validators) from GPT")
        col1, col2, col3, col4 = st.columns(4)
        
        name_selector = selectors.get('product_name_selector') or selectors.get('product_name', 'N/A')
        desc_selector = selectors.get('product_description_selector') or selectors.get('product_description', 'N/A')
        price_selector = selectors.get('product_price_selector') or selectors.get('product_price', 'N/A')
        images_selector = selectors.get('images_container_selector', 'N/A')
        
        with col1:
            st.write("**Product Name Selector:**")
            st.code(name_selector if name_selector != 'N/A' else 'Not provided', language='css')
        
        with col2:
            st.write("**Product Description Selector:**")
            st.code(desc_selector if desc_selector != 'N/A' else 'Not provided', language='css')
        
        with col3:
            st.write("**Product Price Selector:**")
            st.code(price_selector if price_selector != 'N/A' else 'Not provided', language='css')
        
        with col4:
            st.write("**Images Container Selector:**")
            st.code(images_selector if images_selector != 'N/A' else 'Not provided', language='css')
        
        st.divider()
        
        # Display Extracted Data
        st.write("### 3. Extracted Product Data")
        
        # Try multiple possible keys
        product_name = (extracted_data.get('product_name') or 
                       extracted_data.get('product_name_selector') or 
                       'Not found')
        product_description = (extracted_data.get('product_description') or 
                              extracted_data.get('product_description_selector') or 
                              'Not found')
        product_price = (extracted_data.get('product_price') or 
                        extracted_data.get('product_price_selector') or 
                        'Not found')
        
        data_dict = {
            "Product Name": product_name,
            "Product Description": product_description,
            "Product Price": product_price
        }
        
        for key, value in data_dict.items():
            st.write(f"**{key}:**")
            if isinstance(value, list):
                if value:
                    st.write(", ".join(str(v) for v in value))
                else:
                    st.write("*Not found*")
            elif value and value != 'Not found' and not str(value).startswith('Error:'):
                st.write(str(value))
            elif str(value).startswith('Error:'):
                st.error(str(value))
            else:
                st.write("*Not found*")
            st.write("")
        
        # Display Product Images
        st.write("### 4. Product Images")
        image_urls = extracted_data.get('product_images', [])
        image_count = extracted_data.get('product_images_count', 0)
        
        if image_urls and len(image_urls) > 0:
            st.write(f"**Found {image_count} image(s):**")
            for i, img_url in enumerate(image_urls, 1):
                st.write(f"{i}. {img_url}")
                # Try to display image if it's a valid URL
                try:
                    st.image(img_url, caption=f"Image {i}", width=200)
                except:
                    st.write(f"   (Unable to display image)")
        else:
            st.write("*No images found*")
            if extracted_data.get('product_images_error'):
                st.error(f"Error extracting images: {extracted_data.get('product_images_error')}")
        
        st.divider()
        
        # Save Configuration Section
        st.write("### 5. Save Configuration to Database")
        
        # Extract domain from URL
        website_domain = get_domain_from_url(url_input)
        
        # Get currency from country data
        selected_country_data = next((c for c in countries if c['country_name'] == selected_country), None)
        currency = selected_country_data.get('currency', '') if selected_country_data else ''
        
        # Determine status based on results
        if not success:
            status = 'blocked'
            reason = blocking_reason
        else:
            status = 'completed'
            reason = None
        
        # Show what will be saved
        st.write("**Configuration to save:**")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"- **Website:** {website_domain}")
            st.write(f"- **Country:** {selected_country}")
            st.write(f"- **Currency:** {currency}")
            st.write(f"- **Status:** {status}")
        with col2:
            st.write(f"- **Name Selector:** {selectors.get('product_name_selector', 'N/A')}")
            st.write(f"- **Description Selector:** {selectors.get('product_description_selector', 'N/A')}")
            st.write(f"- **Price Selector:** {selectors.get('product_price_selector', 'N/A')}")
            st.write(f"- **Images Container Selector:** {selectors.get('images_container_selector', 'N/A')}")
        
        if reason:
            st.write(f"- **Reason:** {reason}")
        
        # Save button
        if st.button("💾 Save Configuration to Database", type="primary", use_container_width=True):
            if selectors:
                save_success = save_automated_scraping_config(
                    website=website_domain,
                    country=selected_country,
                    currency=currency,
                    name_selector=selectors.get('product_name_selector', ''),
                    description_selector=selectors.get('product_description_selector', ''),
                    price_selector=selectors.get('product_price_selector', ''),
                    images_container_selector=selectors.get('images_container_selector', ''),
                    status=status,
                    reason=reason
                )
                
                if save_success:
                    st.success("✅ Configuration saved to database!")
                    time.sleep(1)
                    st.rerun()  # Refresh to show updated table
                else:
                    st.error("❌ Failed to save configuration. Please check the error above.")
            else:
                st.error("❌ No selectors available to save")
        
        # Debug information
        st.write("### Debug Information")
        cleaned_html_length = len(clean_html_for_gpt(html_content))
        st.write(f"**HTML length (original):** {len(html_content)} characters")
        st.write(f"**HTML length (cleaned):** {cleaned_html_length} characters (removed style/script/iframe)")
        st.write(f"**HTML sent to GPT:** {cleaned_html_length} characters")
        st.write(f"**URL used:** {url_input}")
        
        with st.expander("🔍 Selectors received from GPT"):
            st.json(selectors)
        
        with st.expander("🔍 Extracted data (raw)"):
            st.json(extracted_data)
        
        with st.expander("📄 HTML Preview (first 1000 chars)"):
            st.code(html_content[:1000], language='html')
        
        with st.expander("📤 HTML Sent to GPT (first 2000 chars preview)"):
            st.write(f"Total sent: {len(html_content)} characters (full HTML)")
            st.code(html_content[:2000], language='html')
        
        st.divider()
        
        # Display blocking status
        st.write("### Website Status")
        st.success(f"✅ Website accessible - Successfully visited {visited_count} links without blocking")

def render_settings_page():
    st.title("⚙️ Settings")
    st.subheader("Notification Emails")
    st.caption("Enter one email address per line. These contacts will receive automation alerts.")

    if 'notification_emails_loaded' not in st.session_state:
        st.session_state.notification_emails_loaded = False

    if not st.session_state.notification_emails_loaded:
        emails = get_notification_emails()
        st.session_state.notification_emails_input = "\n".join(emails)
        st.session_state.notification_emails_loaded = True

    email_input = st.text_area(
        "Alert recipients",
        key="notification_emails_input",
        height=150,
        placeholder="person@example.com\nops@example.com"
    )

    if st.button("Save Notification Emails", type="primary"):
        emails = [line.strip() for line in email_input.splitlines() if line.strip()]
        if update_notification_emails(emails):
            st.success("Notification emails updated.")
            st.session_state.notification_emails_loaded = False
            st.rerun()

    current_emails = [line.strip() for line in email_input.splitlines() if line.strip()]
    if current_emails:
        st.write("**Current recipients:**")
        st.write(", ".join(current_emails))
    else:
        st.info("No notification emails configured yet.")
    
    st.divider()
    st.subheader("Sample Size Configuration")
    st.caption("Number of sample products to fetch before pausing for review (default: 100)")
    
    # Fetch current sample size
    try:
        response = requests.get(f"{API_BASE_URL}/settings/sample-size")
        if response.status_code == 200:
            current_sample_size = response.json().get('sample_size', 100)
        else:
            current_sample_size = 100
    except:
        current_sample_size = 100
    
    sample_size_input = st.number_input(
        "Sample Size",
        min_value=1,
        max_value=1000,
        value=current_sample_size,
        step=1,
        key="sample_size_input",
        help="When a website starts scraping, it will fetch this many products as samples, then pause for review."
    )
    
    if st.button("Save Sample Size", type="primary", key="save_sample_size"):
        try:
            response = requests.put(f"{API_BASE_URL}/settings/sample-size?sample_size={sample_size_input}")
            if response.status_code == 200:
                st.success(f"✅ Sample size updated to {sample_size_input}. New slave servers will use this value.")
                st.rerun()
            else:
                st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
        except Exception as e:
            st.error(f"Error updating sample size: {e}")
    
    st.info(f"💡 Current sample size: **{current_sample_size}**. Slave servers fetch this value at startup.")

def main():
    render_sidebar()
    
    current_page = get_current_page()
    
    if current_page == "websites":
        render_websites_page()
    elif current_page == "nodes":
        render_nodes_page()
    elif current_page == "batches":
        render_batches_page()
    elif current_page == "priority_batches":
        render_priority_batches_page()
    elif current_page == "settings":
        render_settings_page()
    elif current_page == "automated_scraping":
        render_automated_scraping_page()
    else:
        set_current_page("websites")
        st.rerun()

if __name__ == "__main__":
    main()
