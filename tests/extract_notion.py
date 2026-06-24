"""Extract test results from Notion page dump"""
import json, re, sys

with open(r'C:\Users\ADMINI~1\AppData\Local\Temp\trae\toolcall-output\a655d6c0-80e0-4d2f-8031-1dd08b1208e3.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

# Parse the outer wrapper
outer = json.loads(raw.replace('The MCP server responded with: ', '', 1))
text = outer[0]['text']
inner = json.loads(text)
page_text = inner['text']

# Decode escaped newlines
page_text = page_text.replace('\\n', '\n')

# Print ALL lines from line 200 onwards
lines = page_text.split('\n')
for i, line in enumerate(lines):
    if 1000 <= i <= 1200:
        print(f"L{i}: {line[:300]}")

