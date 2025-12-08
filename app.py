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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

def get_headers():
    """Get headers with clean token value."""
    return {
        "Authorization": ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

# Global DataFrame to store ClickUp data
df = None

# ==================== AI QUERY PROCESSOR ====================
def ai_process_query(query, data):
    """Use OpenAI to intelligently process complex queries with a 2-step approach:
       1. Generate Python code to filter/aggregate the data (Quantitative)
       2. Analyze the filtered data to answer the user (Qualitative)
    """
    if not OPENAI_API_KEY:
        print("⚠️ OPENAI_API_KEY not found in environment variables")
        return None
    
    try:
        # Step 1: Quantitative - Get the data
        print(f"🔮 AI Step 1: Generating data fetch code for: {query}")
        
        columns = list(data.columns)
        schema_context = f"""
DataFrame `df` has columns: {columns}
Sample values:
- Status: {data['Status'].unique().tolist() if 'Status' in data.columns else []}
- Priority: {data['Priority'].dropna().unique().tolist() if 'Priority' in data.columns else []}
- Folder: {data['Folder'].unique().tolist() if 'Folder' in data.columns else []}

User Query: "{query}"

Write a Python snippet to filter `df` into `result_df`. 
- Use standard pandas filtering. 
- Handle string matching case-insensitively (e.g. .str.contains(..., case=False)). 
- If the user asks for specific columns, still filter the full rows first.
- Handle None/NaN values safely.
- Assign the final filtered DataFrame to the variable `result_df`.
- Return ONLY JSON with a single key "code".
Example: {{"code": "result_df = df[df['Status'] == 'Open']"}}
"""

        response1 = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",  # Use smarter model for code generation
                "messages": [
                    {"role": "system", "content": "You are a Python Data Expert. Generate pandas code to filter dataframes."},
                    {"role": "user", "content": schema_context}
                ],
                "temperature": 0.0,
                "response_format": { "type": "json_object" } 
            },
            timeout=30
        )
        
        if response1.status_code != 200:
            print(f"❌ OpenAI API error (Step 1): {response1.status_code} - {response1.text}")
            return None
            
        code_result = response1.json()["choices"][0]["message"]["content"]
        generated_code = json.loads(code_result)["code"]
        print(f"💻 Generated Code: {generated_code}")
        
        # Safe execution environment
        local_vars = {"df": data, "pd": pd, "result_df": None}
        
        try:
            exec(generated_code, {}, local_vars)
            result_df = local_vars["result_df"]
        except Exception as exec_err:
            print(f"❌ Code execution failed: {exec_err}")
            # Fallback to empty df or original df if filtering fails?
            result_df = pd.DataFrame() 

        # Step 2: Qualitative - Analyze the result
        print(f"🔮 AI Step 2: Analyzing {len(result_df) if result_df is not None else 0} rows")
        
        if result_df is None or result_df.empty:
            data_context = "No tasks found matching the criteria."
        else:
            # Prepare context for analysis
            stats = {
                "count": len(result_df),
                "statuses": result_df['Status'].value_counts().to_dict() if 'Status' in result_df else {},
                "assignees": result_df['Assignees'].value_counts().head(5).to_dict() if 'Assignees' in result_df else {},
                "priorities": result_df['Priority'].value_counts().to_dict() if 'Priority' in result_df else {}
            }
            
            # Serialize a subset of data for the LLM to read
            # Sort by updated date if possible to show recent context
            if "Date Updated" in result_df:
                result_df = result_df.sort_values("Date Updated", ascending=False)
                
            records = result_df.head(30).to_dict(orient='records')
            data_str = json.dumps(records, default=str)
            
            data_context = f"""
Quantitative Data (Exact Match):
- Total Matches: {stats['count']}
- Status Breakdown: {stats['statuses']}
- Top Assignees: {stats['assignees']}

Details of top 30 filtered tasks:
{data_str}
"""

        analysis_system_prompt = f"""You are a ClickUp analyst. 
User Query: "{query}"

Analyze the provided data to answer the user's question qualitatively.
1. Start with the direct Quantitative answer (e.g., "Found 5 tasks...").
2. Provide Qualitative analysis based on the task descriptions, priorities, and statuses.
3. Highlight any concerns (e.g., stalled tasks, high priority items, overdue dates).
4. Be comprehensive.

Return response as JSON:
{{
  "answer": "Your detailed analysis here...",
  "data": [list of task dictionaries to display in UI table, map fields to: 'Task Name', 'Status', 'Assignees', 'Priority', 'Folder', 'Due Date', 'URL'],
  "type": "table" (if data is present) or "text"
}}
"""

        response2 = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": analysis_system_prompt},
                    {"role": "user", "content": f"Here is the data:\n{data_context}"}
                ],
                "temperature": 0.4,
                "response_format": { "type": "json_object" }
            },
            timeout=60
        )
        
        if response2.status_code != 200:
            print(f"❌ OpenAI API error (Step 2): {response2.status_code} - {response2.text}")
            return None
            
        final_result = response2.json()["choices"][0]["message"]["content"]
        parsed = json.loads(final_result)
        
        # If the generated code produced a result_df, ensure we pass that back if the LLM didn't populate 'data' well
        if (not parsed.get("data") or len(parsed.get("data")) == 0) and result_df is not None and not result_df.empty:
             parsed["data"] = result_df.head(20).to_dict(orient='records')
             parsed["type"] = "table"

        return {
            "type": parsed.get("type", "text"),
            "title": "🤖 AI Analysis",
            "data": parsed.get("data", []),
            "summary": parsed.get("answer", "Analysis complete."),
            "message": parsed.get("answer", "Analysis complete."),
            "ai_powered": True
        }

    except Exception as e:
        print(f"❌ AI processing exception: {e}")
        import traceback
        traceback.print_exc()
        return {
            "type": "text", 
            "message": f"⚠️ AI Error: {str(e)}", 
            "ai_powered": True
        }

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
    try:
        response = requests.get(url, headers=get_headers())
        data = response.json()
        if "err" in data:
            print(f"ClickUp API Error (folders): {data}")
            return []
        return data.get("folders", [])
    except Exception as e:
        print(f"Error fetching folders: {e}")
        return []

def get_folderless_lists():
    """Get lists that are not inside folders."""
    url = f"https://api.clickup.com/api/v2/space/{SPACE_ID}/list"
    try:
        response = requests.get(url, headers=get_headers())
        data = response.json()
        if "err" in data:
            print(f"ClickUp API Error (folderless lists): {data}")
            return []
        return data.get("lists", [])
    except Exception as e:
        print(f"Error fetching folderless lists: {e}")
        return []

def get_lists(folder_id):
    url = f"https://api.clickup.com/api/v2/folder/{folder_id}/list"
    try:
        response = requests.get(url, headers=get_headers())
        data = response.json()
        if "err" in data:
            print(f"ClickUp API Error (lists): {data}")
            return []
        return data.get("lists", [])
    except Exception as e:
        print(f"Error fetching lists: {e}")
        return []

def get_tasks(list_id):
    url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
    try:
        response = requests.get(url, headers=get_headers())
        data = response.json()
        if "err" in data:
            print(f"ClickUp API Error (tasks): {data}")
            return []
        return data.get("tasks", [])
    except Exception as e:
        print(f"Error fetching tasks: {e}")
        return []


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
    
    # Fetch tasks from folders
    folders = get_folders()
    print(f"Found {len(folders)} folders")
    for folder in folders:
        folder_name = folder["name"]
        folder_id = folder["id"]
        lists = get_lists(folder_id)
        print(f"  Folder '{folder_name}' has {len(lists)} lists")
        for lst in lists:
            list_name = lst["name"]
            list_id = lst["id"]
            tasks = get_tasks(list_id)
            print(f"    List '{list_name}' has {len(tasks)} tasks")
            for task in tasks:
                rows.append(extract_task(task, list_name, folder_name))
    
    # Fetch tasks from folderless lists
    folderless_lists = get_folderless_lists()
    print(f"Found {len(folderless_lists)} folderless lists")
    for lst in folderless_lists:
        list_name = lst["name"]
        list_id = lst["id"]
        tasks = get_tasks(list_id)
        print(f"  Folderless list '{list_name}' has {len(tasks)} tasks")
        for task in tasks:
            rows.append(extract_task(task, list_name, "(No Folder)"))
    
    print(f"Total tasks fetched: {len(rows)}")
    return pd.DataFrame(rows)

# ==================== QUERY PROCESSOR ====================
# ==================== QUERY PROCESSOR ====================
def process_query(query, data, export_mode=False):
    """
    Process natural language queries.
    STRICT LOGIC: Only trigger "Fast Path" (pre-coded logic) if the user enters
    an exact "Try Asking" suggestion.
    Everything else falls through to AI for deep analysis.
    """
    query_lower = query.lower().strip()
    
    if data is None or data.empty:
        if export_mode: return None
        return {"type": "error", "message": "No data available. Please refresh the data first."}

    # ================= STRICT FAST PATHS =================
    # Only exact matches or very close variations of UI buttons
    
    # 1. Status Distribution
    if query_lower in ["task distribution by status", "show task distribution by status", "status breakdown"]:
        result = data.groupby("Status").size().reset_index(name="Count")
        result = result.sort_values("Count", ascending=False)
        if export_mode: return result
        return {
            "type": "table",
            "title": "📊 Task Distribution by Status",
            "data": result.to_dict(orient="records"),
            "summary": f"Total: {len(data)} tasks across {len(result)} statuses",
            "exportable": True
        }

    # 2. Priority Tasks (High)
    if query_lower in ["high priority tasks", "list all high priority tasks", "show high priority tasks"]:
        filtered = data[data["Priority"] == "high"]
        if export_mode: return filtered
        display_cols = ["Task Name", "Status", "Assignees", "Folder", "Due Date", "URL"]
        return {
            "type": "table",
            "title": f"🔴 High Priority Tasks",
            "data": filtered[display_cols].to_dict(orient="records"),
            "summary": f"Found {len(filtered)} high priority tasks",
            "exportable": True
        }

    # 3. Assignee Workload
    if query_lower in ["who has the most tasks?", "who has the most tasks", "workload by assignee"]:
        all_assignees = []
        for assignees in data["Assignees"].dropna():
            if assignees:
                all_assignees.extend([a.strip() for a in assignees.split(",")])
        
        from collections import Counter
        counts = Counter(all_assignees)
        result = pd.DataFrame(counts.items(), columns=["Assignee", "Tasks"])
        result = result.sort_values("Tasks", ascending=False)
        if export_mode: return result
        return {
            "type": "table",
            "title": "👥 Workload by Assignee",
            "data": result.to_dict(orient="records"),
            "summary": f"{len(result)} team members with assigned tasks",
            "exportable": True
        }

    # 4. Overdue Tasks
    if query_lower in ["overdue tasks", "show overdue tasks"]:
        now = datetime.now()
        data_with_due = data[data["Due Date"].notna()].copy()
        data_with_due["Due Date Parsed"] = pd.to_datetime(data_with_due["Due Date"])
        overdue = data_with_due[data_with_due["Due Date Parsed"] < now]
        if export_mode: return overdue
        
        display_cols = ["Task Name", "Status", "Assignees", "Priority", "Due Date", "URL"]
        return {
            "type": "table",
            "title": "⚠️ Overdue Tasks",
            "data": overdue[display_cols].to_dict(orient="records"),
            "summary": f"Found {len(overdue)} overdue tasks that need attention",
            "exportable": True
        }

    # 5. Workspace Summary
    if query_lower in ["workspace summary", "give me a summary", "summary"]:
        if export_mode: return None
        total = len(data)
        by_status = data.groupby("Status").size().to_dict()
        by_priority = data.groupby("Priority").size().to_dict()
        folders = data["Folder"].nunique()
        
        if "Date Created" in data.columns and data["Date Created"].notna().any():
            dates = pd.to_datetime(data["Date Created"].dropna())
            oldest = dates.min().strftime("%Y-%m-%d") if len(dates) > 0 else "N/A"
            newest = dates.max().strftime("%Y-%m-%d") if len(dates) > 0 else "N/A"
            date_range = f"{oldest} to {newest}"
        else:
            date_range = "N/A"
        
        return {
            "type": "summary",
            "title": "📈 Workspace Overview",
            "stats": {
                "Total Tasks": total,
                "Folders": folders,
                "Date Range": date_range,
                "Statuses": by_status,
                "Priorities": by_priority
            },
            "drill_down_hint": "💡 Tip: Click any status or priority name to see those tasks, or try 'show tasks from last 3 months'"
        }

    # 6. Time Filter (Last 3 months fallback/shortcut)
    if query_lower in ["show tasks from last 3 months", "tasks from last 3 months"]:
        now = datetime.now()
        data_with_date = data[data["Date Created"].notna()].copy()
        data_with_date["Created Parsed"] = pd.to_datetime(data_with_date["Date Created"])
        cutoff = now - pd.Timedelta(days=90)
        filtered_data = data_with_date[data_with_date["Created Parsed"] >= cutoff]
        if export_mode: return filtered_data
        
        total = len(filtered_data)
        by_status = filtered_data.groupby("Status").size().to_dict() if total > 0 else {}
        by_priority = filtered_data.groupby("Priority").size().to_dict() if total > 0 else {}
        
        return {
            "type": "summary",
            "title": f"📈 Tasks from Last 3 Months",
            "stats": {
                "Total Tasks": total,
                "Original Total": len(data),
                "Statuses": by_status,
                "Priorities": by_priority
            },
            "filter_info": f"Showing tasks created in the last 90 days"
        }

    # 7. Complete/In Progress (Simple Status)
    if query_lower in ["show complete tasks", "complete tasks"]:
        filtered = data[data["Status"].str.lower() == "complete"]
        if export_mode: return filtered
        display_cols = ["Task Name", "Assignees", "Priority", "Folder", "Due Date", "URL"]
        return {
            "type": "table",
            "title": "📋 Complete Tasks",
            "data": filtered[display_cols].head(50).to_dict(orient="records"),
            "summary": f"Found {len(filtered)} completed tasks",
            "exportable": True
        }
    
    if query_lower in ["show in progress tasks", "in progress tasks"]:
        filtered = data[data["Status"].str.lower() == "in progress"]
        if export_mode: return filtered
        display_cols = ["Task Name", "Assignees", "Priority", "Folder", "Due Date", "URL"]
        return {
            "type": "table",
            "title": "📋 In Progress Tasks",
            "data": filtered[display_cols].head(50).to_dict(orient="records"),
            "summary": f"Found {len(filtered)} in-progress tasks",
            "exportable": True
        }

    # 8. List All
    if query_lower in ["list all tasks", "show all tasks", "everything"]:
        if export_mode: return data
        display_cols = ["Task Name", "Status", "Assignees", "Folder", "Priority", "Due Date", "URL"]
        return {
            "type": "table",
            "title": "📋 All Tasks",
            "data": data[display_cols].head(50).to_dict(orient="records"),
            "summary": f"Showing first 50 of {len(data)} total tasks",
            "exportable": True
        }
    
    # ================= AI FALLBACK =================
    # If NO match found above, send to AI.
    
    if not export_mode:
        print(f"🤖 No strict pattern match for '{query}', sending to AI...")
        ai_result = ai_process_query(query, data)
        if ai_result:
            return ai_result
    
    if export_mode: return None
    
    # Default: show help
    return {
        "type": "help",
        "message": "I can help you with:",
        "suggestions": [
            "Show task distribution by status",
            "List all high priority tasks",
            "Show complete tasks",
            "Show in progress tasks",
            "Show tasks from last 3 months",
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
    try:
        data = request.json
        query = data.get("message", "")
        
        if not query:
            return jsonify({"error": "No message provided"}), 400
        
        result = process_query(query, df)
        # Echo back the original query to allow frontend to request export
        if isinstance(result, dict):
            result["query"] = query
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "type": "error", 
            "message": f"🔥 System Error: {str(e)}"
        })

@app.route("/api/chat/export", methods=["POST"])
def export_chat_result():
    global df
    try:
        data = request.json
        query = data.get("query", "")
        if not query:
            return jsonify({"error": "No query provided"}), 400
            
        result_df = process_query(query, df, export_mode=True)
        
        if result_df is None or result_df.empty:
            return jsonify({"error": "No data to export for this query"}), 400
            
        output = io.BytesIO()
        result_df.to_excel(output, index=False, engine="openpyxl")
        output.seek(0)
        
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"export_{int(datetime.now().timestamp())}.xlsx"
        )
    except Exception as e:
        print(f"Export error: {e}")
        return jsonify({"error": str(e)}), 500

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

@app.route("/api/debug", methods=["GET"])
def debug_info():
    """Debug endpoint to check environment variables and API connectivity."""
    # Check env vars (hide most of token for security)
    token_preview = ACCESS_TOKEN[:10] + "..." if len(ACCESS_TOKEN) > 10 else ACCESS_TOKEN
    openai_preview = OPENAI_API_KEY[:5] + "..." if len(OPENAI_API_KEY) > 5 else "NOT SET"
    
    # Test API call
    try:
        url = f"https://api.clickup.com/api/v2/space/{SPACE_ID}/folder"
        response = requests.get(url, headers=get_headers())
        api_response = response.json()
        api_status = "OK" if "folders" in api_response else f"Error: {api_response}"
        folder_count = len(api_response.get("folders", []))
    except Exception as e:
        api_status = f"Exception: {str(e)}"
        folder_count = 0
    
    return jsonify({
        "token_preview": token_preview,
        "token_length": len(ACCESS_TOKEN),
        "space_id": SPACE_ID,
        "space_id_length": len(SPACE_ID),
        "api_status": api_status,
        "folder_count": folder_count,
        "openai_key_set": bool(OPENAI_API_KEY),
        "openai_preview": openai_preview
    })

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
