import pyttsx3

try:
    e = pyttsx3.init()
    voices = e.getProperty("voices")
    print("=== 系统可用声音（SAPI）===")
    for i, v in enumerate(voices):
        langs = getattr(v, "languages", [])
        lang = langs[0] if langs else "?"
        print(f"  [{i}] {v.name}")
        print(f"      lang={lang}")
        print(f"      id={v.id}")
        print(f"      gender={getattr(v, 'gender', '?')}")
        print(f"      age={getattr(v, 'age', '?')}")
        print()
    print(f"共 {len(voices)} 个声音")
except Exception as exc:
    print("pyttsx3 初始化失败:", exc)
