#!/bin/bash
# KDP Auto-Generate — runs daily at 10:00 ICT (03:00 UTC)
# Invokes Claude Code with kdp-writer skill to create a new ebook

export PATH="/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export HOME="/root"

LOG_DIR="/root/kdp/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

echo "=== KDP Auto-Generate $(date) ===" >> "$LOG_FILE"

# Build the prompt: check existing books first, then create new one
EXISTING=$(for f in /root/kdp/*/listing.json; do
  [ -f "$f" ] && python3 -c "import sys,json; d=json.load(open('$f')); print(f\"- {d.get('title','')} ({d.get('language','')})\")" 2>/dev/null
done)

PROMPT="I need you to create a new KDP ebook using the kdp-writer skill.

Here are the ebooks already created (DO NOT duplicate these topics):
$EXISTING

Instructions:
1. Check the list above to avoid duplicates
2. Use the kdp-writer skill Step 2A to evaluate and choose a marketplace — do NOT default to Brazil. Spread across different marketplaces and languages (Spanish, German, French, Italian, etc.). Check which languages are already overrepresented in existing books and pick a DIFFERENT one.
3. Research a NEW profitable niche in the chosen marketplace
4. Pick a different topic/profession/angle from what's already been done
5. Follow the full kdp-writer pipeline: research → write → listing → cover → EPUB → queue
6. Make sure the ebook appears in Libra queue with status 'ready'

Go!"

# Run codex in non-interactive mode (subscription auth, NOT API key).
# gpt-5.4 + low reasoning effort = plenty for content writing, keeps plan quota low.
codex --search exec --skip-git-repo-check --ephemeral -s danger-full-access \
  -m gpt-5.4 -c model_reasoning_effort="low" -c approval_policy="never" \
  -C /root "$PROMPT" >> "$LOG_FILE" 2>&1

# Send Telegram notification for any new books created today
python3 /opt/libra/notify-new-books.py >> "$LOG_FILE" 2>&1

echo "=== Finished $(date) ===" >> "$LOG_FILE"
