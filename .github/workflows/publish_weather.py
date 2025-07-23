name: Publish Weather Updates

on:
  workflow_dispatch:
  schedule:
    - cron: '0 0 * * *'
    - cron: '0 12 * * *'

jobs:
  publish:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      with:
        persist-credentials: true
        fetch-depth: 0

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'

    - name: Install dependencies
      run: |
        pip install requests python-telegram-bot Pillow httpx PyYAML

    - name: Create backgrounds folders
      run: |
        mkdir -p backgrounds/Пномпень
        mkdir -p backgrounds/Сиануквиль
        mkdir -p backgrounds/Сиемреап

    - name: Run Python script
      env:
        TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
        ACCUWEATHER_API_KEY: ${{ secrets.ACCUWEATHER_API_KEY }}
        TARGET_CHAT_ID: ${{ secrets.TARGET_CHAT_ID }}
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      run: python weather_publisher.py

    - name: Commit and Push Changes
      run: |
        git config user.name "GitHub Actions Bot"
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git add message_ids.yml
        git commit -m "chore: Save sent message IDs for deletion" || echo "No changes to commit"
        git push || echo "No new commits to push"
