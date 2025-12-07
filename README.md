# ClickUp Intelligence Agent

AI-powered chat interface for analyzing your ClickUp workspace data.

## Features

- 💬 Natural language queries about your tasks
- 📊 Task distribution by status, priority, assignee
- ⚠️ Overdue task detection
- 📁 Folder/list filtering
- 📥 Export to CSV or Excel

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `CLICKUP_ACCESS_TOKEN` | Your ClickUp API token | Yes |
| `CLICKUP_SPACE_ID` | Your ClickUp Space ID | Yes |
| `PORT` | Server port (default: 5000) | No |

## Deployment

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

1. Connect your GitHub repo
2. Set environment variables in Railway dashboard
3. Deploy!

## Example Queries

- "Show task distribution by status"
- "List high priority tasks"
- "Who has the most tasks?"
- "Show overdue tasks"
- "Export to CSV"
