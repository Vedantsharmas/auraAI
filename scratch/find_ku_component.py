import re

print("Searching ku = chunk-by-chunk...")
with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    chunk_size = 65536
    overlap = 1000
    pos = 0
    buffer = ""
    while True:
        data = f.read(chunk_size)
        if not data:
            break
        buffer += data
        
        # Search for matches
        for m in re.finditer(r'\bku\s*=\s*', buffer):
            match_pos = pos + m.start()
            print(f"Found match at position {match_pos}:")
            print(buffer[m.start() : m.start() + 1500])
            print("---------------------------------------")
            
        pos += len(data)
        buffer = buffer[-overlap:]
