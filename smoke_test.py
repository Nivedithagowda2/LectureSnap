import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

os.chdir(r'c:\Users\Niveditha gowda\Downloads\lecturesnapfull (3)\lecturesnapfull')
sys.path.insert(0, os.getcwd())
import main

p1 = Path('test1.png')
p2 = Path('test2.png')
Image.new('RGB', (1280, 720), (255, 0, 0)).save(p1)
Image.new('RGB', (1280, 720), (0, 0, 255)).save(p2)

subprocess.run(
    ['ffmpeg', '-y', '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=2', '-vn', '-ac', '1', '-ar', '44100', 'test.mp3'],
    capture_output=True,
    text=True,
    check=False,
)

main.assemble_video([str(p1), str(p2)], 'test.mp3', 'out.mp4', ['A', 'B'])

out = Path('out.mp4')
print('out_exists', out.exists(), 'size', out.stat().st_size if out.exists() else None)
