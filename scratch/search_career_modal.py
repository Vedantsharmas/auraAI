with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

idx = js.find("Hello Kinjal hear")
if idx != -1:
    print("\n--- Hello Kinjal hear Context ---")
    print(js[idx-500:idx+2500])
