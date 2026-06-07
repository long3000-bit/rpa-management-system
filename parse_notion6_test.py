import re

# Read the file
with open(r'C:\Users\ADMINI~1\AppData\Local\Temp\trae\toolcall-output\8a54ae90-0aa5-410f-9693-8243cfa6b86c.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# Find content section
content_match = re.search(r'<content>(.+?)</content>', content, re.DOTALL)
if content_match:
    page_content = content_match.group(1)
    # Decode escaped characters
    page_content = page_content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
    
    # Find test results section - look for "测试" or "问题"
    lines = page_content.split('\n')
    
    # Print all content
    print(page_content[-8000:])  # Print last part to see test results
else:
    print("未找到content部分")
    print(content[:5000])