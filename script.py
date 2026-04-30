import os
import cv2
import subprocess
import random
from faster_whisper import WhisperModel

INPUT_DIR = "input"
APP_DIR = "app"
MUSIC_DIR = "music"
OUTPUT_DIR = "output"

MODEL = WhisperModel("base")

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

# -----------------------
# 1. Download videos
# -----------------------
def download_all():
    os.makedirs(INPUT_DIR, exist_ok=True)
    with open("urls.txt") as f:
        for url in f:
            url = url.strip()
            if url:
                run(f'yt-dlp -o "{INPUT_DIR}/%(id)s.%(ext)s" "{url}"')

# -----------------------
# 2. Detect split (more stable)
# -----------------------
def detect_split(video):
    cap = cv2.VideoCapture(video)

    if not cap.isOpened():
        return 0

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total == 0:
        return 0

    limit = int(total * 0.6)

    prev = None
    max_diff = 0
    split = 0

    for i in range(limit):
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if prev is not None:
            diff = cv2.absdiff(prev, gray).mean()
            if diff > max_diff:
                max_diff = diff
                split = i

        prev = gray

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30

    cap.release()
    return split / fps

# -----------------------
# 3. Captions
# -----------------------
def get_captions(video):
    segments, _ = MODEL.transcribe(video)
    return [(s.start, s.end, s.text.strip()) for s in segments]

# -----------------------
# 4. ASS conversion (fixed formatting)
# -----------------------
def format_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02}:{s:05.2f}"

def make_ass(subs, filename):
    path = f"{filename}.ass"

    with open(path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\n\n")
        f.write("[V4+ Styles]\n")
        f.write("Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BorderStyle,Outline\n")
        f.write("Style: Default,Arial,60,&H00FFFFFF,&H00000000,1,3\n\n")
        f.write("[Events]\n")
        f.write("Format: Start,End,Style,Text\n")

        for s, e, t in subs:
            t = t.replace(",", " ")  # prevent ASS break
            f.write(f"Dialogue: {format_time(s)},{format_time(e)},Default,{t}\n")

    return path

# -----------------------
# 5. Processing
# -----------------------
def process(video):
    name = os.path.splitext(os.path.basename(video))[0]

    split = detect_split(video)

    before = f"{name}_b.mp4"
    after = f"{name}_a.mp4"
    merged = f"{name}_m.mp4"
    final = os.path.join(OUTPUT_DIR, f"{name}_final.mp4")

    app = os.path.join(APP_DIR, random.choice(os.listdir(APP_DIR)))
    music = os.path.join(MUSIC_DIR, random.choice(os.listdir(MUSIC_DIR)))

    # Split safely
    run(f'ffmpeg -y -i "{video}" -t {split} -c copy "{before}"')
    run(f'ffmpeg -y -i "{video}" -ss {split} -c copy "{after}"')

    # Concat
    with open("list.txt", "w") as f:
        f.write(f"file '{before}'\n")
        f.write(f"file '{app}'\n")
        f.write(f"file '{after}'\n")

    run(f'ffmpeg -y -f concat -safe 0 -i list.txt -c copy "{merged}"')

    # Captions
    subs = get_captions(merged)
    ass = make_ass(subs, name)

    hook = "This changed everything"

    # -----------------------
    # FIXED FFMPEG PIPELINE
    # -----------------------
    subtitle_path = ass.replace("\\", "/").replace(":", "\\:")

    run(
        f'ffmpeg -y -i "{merged}" -i "{music}" '
        f'-filter_complex "'
        f'[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,'
        f'subtitles=\'{subtitle_path}\','
        f'drawtext=text=\'{hook}\':fontcolor=white:fontsize=80:x=(w-text_w)/2:y=100[v];'
        f'[1:a]volume=0.4[a1];'
        f'[0:a][a1]amix=inputs=2:duration=shortest[aout]" '
        f'-map "[v]" -map "[aout]" -shortest "{final}"'
    )

    # Cleanup
    for f in [before, after, merged, "list.txt", ass]:
        if os.path.exists(f):
            os.remove(f)

    print("Done:", final)

# -----------------------
# 6. Run
# -----------------------
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    download_all()

    for file in os.listdir(INPUT_DIR):
        if file.endswith(".mp4"):
            process(os.path.join(INPUT_DIR, file))

if __name__ == "__main__":
    main()