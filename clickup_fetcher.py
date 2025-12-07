import requests
import pandas as pd
from datetime import datetime

import os

# CONFIGURATION
# Use environment variables for production, fallback to defaults for local dev
ACCESS_TOKEN = os.environ.get("CLICKUP_ACCESS_TOKEN", "94935933_740ec3faec5725148497a165331e94893f5e265c14dd7085c5f468ec9fb80be5").strip()
SPACE_ID = os.environ.get("CLICKUP_SPACE_ID", "90162405715").strip()

headers = {
    "Authorization": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

# HELPERS
def to_datetime(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None

def get_folders():
    url = f"https://api.clickup.com/api/v2/space/{SPACE_ID}/folder"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error fetching folders: {response.text}")
        return []
    return response.json().get("folders", [])

def get_lists(folder_id):
    url = f"https://api.clickup.com/api/v2/folder/{folder_id}/list"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error fetching lists for folder {folder_id}: {response.text}")
        return []
    return response.json().get("lists", [])

def get_tasks(list_id):
    url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
    # Note: Default limit is usually 100.
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error fetching tasks for list {list_id}: {response.text}")
        return []
    return response.json().get("tasks", [])

def safe_priority(task):
    p = task.get("priority")
    return p.get("priority") if isinstance(p, dict) else None

def extract_task(task, list_name, folder_name):
    return {
        "Task ID": task.get("id"),
        "Task Name": task.get("name"),
        "Status": task.get("status", {}).get("status"),
        "Assignees": ", ".join([a.get("username", "") for a in task.get("assignees", [])]),
        "List": list_name,
        "Folder": folder_name,
        "Priority": safe_priority(task),
        "Due Date": to_datetime(task.get("due_date")),
        "Date Created": to_datetime(task.get("date_created")),
        "Date Updated": to_datetime(task.get("date_updated")),
        "URL": task.get("url"),
        "Description": task.get("text_content"),
    }

# EXECUTION FUNCTION
def fetch_clickup_data():
    rows = []
    folders = get_folders()
    print(f"Found {len(folders)} folders.")
    for folder in folders:
        folder_name = folder["name"]
        folder_id = folder["id"]
        lists = get_lists(folder_id)
        print(f"  Folder '{folder_name}' has {len(lists)} lists.")
        for lst in lists:
            list_name = lst["name"]
            list_id = lst["id"]
            tasks = get_tasks(list_id)
            print(f"    List '{list_name}' has {len(tasks)} tasks.")
            for task in tasks:
                rows.append(extract_task(task, list_name, folder_name))

    return pd.DataFrame(rows)

if __name__ == "__main__":
    print("Loading data from ClickUp...")
    df = fetch_clickup_data()
    print(f"Data loaded. Rows: {len(df)}")
    # Save to CSV for persistence across sessions if needed, or just for debugging
    df.to_csv("clickup_data.csv", index=False)
    print("Data saved to clickup_data.csv")
