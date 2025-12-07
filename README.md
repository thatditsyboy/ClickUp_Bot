# ClickUp Intelligence Agent 🤖

AI-powered chat interface for analyzing your ClickUp workspace data.

![ClickUp Agent](https://img.shields.io/badge/Deployed-Vercel-black?style=for-the-badge&logo=vercel)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-2.3-green?style=for-the-badge&logo=flask)

## ✨ Features

- 💬 **Natural language queries** about your tasks
- 📊 **Task distribution** by status and priority
- 👥 **Workload analysis** by assignee
- ⚠️ **Overdue task detection**
- 📁 **Folder/list filtering**
- 📥 **Export to CSV or Excel**

## 🚀 Deployment

This application is deployed on **Vercel**.

### Deploy Your Own

1. Fork this repository
2. Connect to Vercel
3. Add environment variables:

| Variable | Description |
|----------|-------------|
| `CLICKUP_ACCESS_TOKEN` | Your ClickUp API token |
| `CLICKUP_SPACE_ID` | Your ClickUp Space ID |

4. Deploy!

## 💻 Local Development

```bash
# Clone the repo
git clone https://github.com/thatditsyboy/ClickUp_Bot.git
cd ClickUp_Bot

# Install dependencies
pip install -r requirements.txt

# Set environment variables (or use defaults in code for testing)
export CLICKUP_ACCESS_TOKEN="your_token_here"
export CLICKUP_SPACE_ID="your_space_id"

# Run the app
python app.py
```

Open http://localhost:5000

## 📝 Example Queries

- "Show task distribution by status"
- "List high priority tasks"
- "Who has the most tasks?"
- "Show overdue tasks"
- "Give me a workspace summary"
- "Export to CSV"

## 🛠️ Tech Stack

- **Backend**: Flask + Python
- **Frontend**: HTML/CSS/JS with glassmorphic design
- **Data**: Pandas for analysis
- **API**: ClickUp REST API v2
- **Hosting**: Vercel

## 📁 Project Structure

```
├── app.py              # Flask backend
├── requirements.txt    # Python dependencies
├── vercel.json        # Vercel configuration
├── templates/
│   └── index.html     # Chat UI
└── static/
    ├── styles.css     # Glassmorphic styling
    └── app.js         # Frontend logic
```

## 🔒 Security

- API tokens are stored as environment variables
- Tokens are never exposed in client-side code
- Debug endpoint masks sensitive data

## 📄 License

MIT
