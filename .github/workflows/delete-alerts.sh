#!/bin/bash


# Prompt for variables
read -p "GitHub owner: " OWNER
read -p "Repository name: " REPO
read -s -p "GitHub Personal Access Token: " TOKEN
echo

# Get all code scanning alerts
alerts=$(curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/code-scanning/alerts" | jq '.[].number')

# Loop through and delete each alert
for alert_number in $alerts; do
  echo "Deleting alert $alert_number..."
  curl -s -X DELETE -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/$OWNER/$REPO/code-scanning/alerts/$alert_number"
done

echo "All code scanning alerts deleted."