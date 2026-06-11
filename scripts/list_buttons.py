import re
import pathlib

base = pathlib.Path('app/ui/pages')
for p in sorted(base.glob('*.py')):
    text = p.read_text(encoding='utf-8')
    buttons = re.findall(r'QPushButton\("([^"]+)"\)', text)
    if buttons:
        print('\nFILE', p)
        for b in buttons:
            print('  BTN:', b)
