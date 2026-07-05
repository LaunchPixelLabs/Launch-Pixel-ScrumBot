#!/bin/bash

# Start the DevOps / JIRA Bot
echo "🤖 Starting Launch Pixel JIRA Bot..."
python bot.py &

# Start the AI Scrum Master Bot
echo "🕵️‍♂️ Starting Launch Pixel AI Scrum Master Bot..."
python scrum_bot.py &

# Wait for any process to exit
wait -n

# Exit with status of the process that exited first
exit $?
