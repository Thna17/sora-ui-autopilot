#!/usr/bin/env python3
import json, sys, os
from pathlib import Path
import subprocess

def run_cmd(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

def main(input_json_path: str):
    with open(input_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    story_id = data["storyId"]
    clips = data["clips"]
    music = data.get("musicPath")
    out_dir = data["outputDir"]

    os.makedirs(out_dir, exist_ok=True)

    # OUTPUTS
    output_video = str(Path(out_dir) / f"{story_id}_final.mp4")
    output_srt = str(Path(out_dir) / f"{story_id}.srt")

    # TODO: replace these with your real pipeline
    # Example placeholder: just concat with ffmpeg concat demuxer
    concat_list = Path(out_dir) / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{c}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", output_video]
    code, so, se = run_cmd(cmd)

    merged_done = (code == 0) and Path(output_video).exists()

    result = {
        "merged_done": merged_done,
        "output_video": output_video if merged_done else "",
        "output_srt": output_srt if Path(output_srt).exists() else "",
        "input_count": len(clips),
    }

    print("__RESULT__=" + json.dumps(result))

    return 0 if merged_done else 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Missing input json path")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
