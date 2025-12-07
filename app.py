from flask import Flask, render_template, request, jsonify, send_file
import requests
import pandas as pd
from datetime import datetime
import io
import json
import re
import os

app = Flask(__name__)

# ==================== CONFIGURATION ====================
# Use environment variables for production, fallback to defaults for local dev
ACCESS_TOKEN = os.environ.get("CLICKUP_ACCESS_TOKEN", "94935933_740ec3faec5725148497a165331e94893f5e265c14dd7085c5f468ec9fb80be5").strip()
SPACE_ID = os.environ.get("CLICKUP_SPACE_ID", "90162405715").strip()

def get_headers():
    """Get headers with clean token value."""
    return {
        "Authorization": ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

# Global DataFrame to store ClickUp data
df = None

# ==================== HELPERS ====================
def to_datetime(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None

def get_folders():
    url = f"https://api.clickup.com/api/v2/space/{SPACE_ID}/folder"
    response = requests.get(url, headers=get_headers())
    return response.json().get("folders", [])

def get_lists(folder_id):
    url = f"https://api.clickup.com/api/v2/folder/{folder_id}/list"
    response = requests.get(url, headers=get_headers())
    return response.json().get("lists", [])

def get_tasks(list_id):
    url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
    response = requests.get(url, headers=get_headers())
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

def fetch_clickup_data():
    rows = []
    folders = get_folders()
    for folder in folders:
        folder_name = folder["name"]
        folder_id = folder["id"]
        lists = get_lists(folder_id)
        for lst in lists:
            list_name = lst["name"]
            list_id = lst["id"]
            tasks = get_tasks(list_id)
            for task in tasks:
                rows.append(extract_task(task, list_name, folder_name))
    return pd.DataFrame(rows)

# ==================== QUERY PROCESSOR ====================
def process_query(query, data):
    """Process natural language queries and return results."""
    query_lower = query.lower()
    
    if data is None or data.empty:
        return {"type": "error", "message": "No data available. Please refresh the data first."}
    
    # Status distribution
    if any(word in query_lower for word in ["status", "distribution", "breakdown"]):
        result = data.groupby("Status").size().reset_index(name="Count")
        result = result.sort_values("Count", ascending=False)
        return {
            "type": "table",
            "title": "📊 Task Distribution by Status",
            "data": result.to_dict(orient="records"),
            "summary": f"Total: {len(data)} tasks across {len(result)} statuses"
        }
    
    # Priority tasks
    if "priority" in query_lower:
        if "high" in query_lower:
            filtered = data[data["Priority"] == "high"]
        elif "urgent" in query_lower:
            filtered = data[data["Priority"] == "urgent"]
        elif "low" in query_lower:
            filtered = data[data["Priority"] == "low"]
        else:
            result = data.groupby("Priority").size().reset_index(name="Count")
            result = result.sort_values("Count", ascending=False)
            return {
                "type": "table",
                "title": "🎯 Tasks by Priority",
                "data": result.to_dict(orient="records"),
                "summary": f"Priority breakdown for {len(data)} tasks"
            }
        
        display_cols = ["Task Name", "Status", "Assignees", "Folder", "Due Date"]
        return {
            "type": "table",
            "title": f"🔴 High Priority Tasks",
            "data": filtered[display_cols].to_dict(orient="records"),
            "summary": f"Found {len(filtered)} high priority tasks"
        }
    
    # Assignee workload
    if any(word in query_lower for word in ["assignee", "assigned", "workload", "who has"]):
        # Split assignees and count
        all_assignees = []
        for assignees in data["Assignees"].dropna():
            if assignees:
                all_assignees.extend([a.strip() for a in assignees.split(",")])
        
        from collections import Counter
        counts = Counter(all_assignees)
        result = pd.DataFrame(counts.items(), columns=["Assignee", "Tasks"])
        result = result.sort_values("Tasks", ascending=False)
        return {
            "type": "table",
            "title": "👥 Workload by Assignee",
            "data": result.to_dict(orient="records"),
            "summary": f"{len(result)} team members with assigned tasks"
        }
    
    # Overdue tasks
    if "overdue" in query_lower:
        now = datetime.now()
        data_with_due = data[data["Due Date"].notna()].copy()
        data_with_due["Due Date Parsed"] = pd.to_datetime(data_with_due["Due Date"])
        overdue = data_with_due[data_with_due["Due Date Parsed"] < now]
        
        display_cols = ["Task Name", "Status", "Assignees", "Priority", "Due Date"]
        return {
            "type": "table",
            "title": "⚠️ Overdue Tasks",
            "data": overdue[display_cols].to_dict(orient="records"),
            "summary": f"Found {len(overdue)} overdue tasks that need attention"
        }
    
    # Folder filter
    if "folder" in query_lower:
        folders = data["Folder"].unique()
        for folder in folders:
            if folder.lower() in query_lower:
                filtered = data[data["Folder"] == folder]
                display_cols = ["Task Name", "Status", "Assignees", "Priority", "List"]
                return {
                    "type": "table",
                    "title": f"📁 Tasks in {folder}",
                    "data": filtered[display_cols].to_dict(orient="records"),
                    "summary": f"Found {len(filtered)} tasks in {folder}"
                }
        
        # Show all folders
        result = data.groupby("Folder").size().reset_index(name="Tasks")
        return {
            "type": "table",
            "title": "📁 All Folders",
            "data": result.to_dict(orient="records"),
            "summary": f"{len(result)} folders in your workspace"
        }
    
    # List all tasks
    if any(word in query_lower for word in ["all tasks", "show all", "list all", "everything"]):
        display_cols = ["Task Name", "Status", "Assignees", "Folder", "Priority"]
        return {
            "type": "table",
            "title": "📋 All Tasks",
            "data": data[display_cols].head(50).to_dict(orient="records"),
            "summary": f"Showing first 50 of {len(data)} total tasks"
        }
    
    # Export commands
    if any(word in query_lower for word in ["export", "download", "csv", "excel"]):
        return {
            "type": "export",
            "message": "Click the export button below to download your data.",
            "format": "excel" if "excel" in query_lower else "csv"
        }
    
    # Summary / overview
    if any(word in query_lower for word in ["summary", "overview", "stats", "statistics"]):
        total = len(data)
        by_status = data.groupby("Status").size().to_dict()
        by_priority = data.groupby("Priority").size().to_dict()
        folders = data["Folder"].nunique()
        
        return {
            "type": "summary",
            "title": "📈 Workspace Overview",
            "stats": {
                "Total Tasks": total,
                "Folders": folders,
                "Statuses": by_status,
                "Priorities": by_priority
            }
        }
    
    # Default: show help
    return {
        "type": "help",
        "message": "I can help you with:",
        "suggestions": [
            "Show task distribution by status",
            "List all high priority tasks",
            "Who has the most tasks?",
            "Show overdue tasks",
            "Give me a summary",
            "Export to CSV"
        ]
    }

# ==================== ROUTES ====================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    global df
    data = request.json
    query = data.get("message", "")
    
    if not query:
        return jsonify({"error": "No message provided"}), 400
    
    result = process_query(query, df)
    return jsonify(result)

@app.route("/api/refresh", methods=["GET"])
def refresh_data():
    global df
    try:
        df = fetch_clickup_data()
        return jsonify({
            "success": True,
            "message": f"✅ Data refreshed! Loaded {len(df)} tasks.",
            "count": len(df)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"❌ Error: {str(e)}"
        }), 500

@app.route("/api/export/<format>", methods=["GET"])
def export_data(format):
    global df
    if df is None or df.empty:
        return jsonify({"error": "No data to export"}), 400
    
    if format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name="clickup_export.csv"
        )
    elif format == "excel":
        output = io.BytesIO()
        df.to_excel(output, index=False, engine="openpyxl")
        output.seek(0)
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="clickup_export.xlsx"
        )
    else:
        return jsonify({"error": "Invalid format"}), 400

@app.route("/api/stats", methods=["GET"])
def get_stats():
    global df
    if df is None or df.empty:
        return jsonify({"loaded": False, "count": 0})
    return jsonify({"loaded": True, "count": len(df)})

if __name__ == "__main__":
    print("🚀 Starting ClickUp Intelligence Agent...")
    print("📊 Fetching initial data from ClickUp...")
    try:
        df = fetch_clickup_data()
        print(f"✅ Loaded {len(df)} tasks!")
    except Exception as e:
        print(f"⚠️ Could not load initial data: {e}")
        df = pd.DataFrame()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG", "false").lower() == "true")

