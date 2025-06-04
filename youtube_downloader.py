import sys
import os
import subprocess
import json

# This script is designed to be called by the Flask backend.
# It downloads a YouTube video using yt-dlp and prints the path on success.

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python youtube_downloader.py <youtube_id> <download_dir>")
        sys.exit(1)

    youtube_id = sys.argv[1]
    download_dir = sys.argv[2]
    video_url = f"https://www.youtube.com/watch?v={youtube_id}"

    os.makedirs(download_dir, exist_ok=True)

    # yt-dlp options
    # -f 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' for mp4
    # --output specifies the output template
    # --restrict-filenames to keep filenames simple
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(download_dir, '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'restrictfilenames': True,
        'quiet': True,
        'no_warnings': True,
        'progress': True, # This will make yt-dlp print progress, which can be parsed
    }

    try:
        # Use subprocess to run yt-dlp
        # We capture stdout and stderr to report back to the Flask app
        command = [
            sys.executable, '-m', 'yt_dlp',
            '--format', ydl_opts['format'],
            '--output', ydl_opts['outtmpl'],
            '--merge-output-format', ydl_opts['merge_output_format'],
            '--restrict-filenames',
            '--quiet',
            '--no-warnings',
            video_url
        ]
        
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        
        # Parse the output to find the downloaded filename
        # yt-dlp usually prints the final filename on a line like "[download] Destination: ..."
        downloaded_file = None
        for line in process.stdout.splitlines():
            if "[download] Destination:" in line:
                downloaded_file = line.split("Destination:")[1].strip()
                break
            elif "[Merger] Merging formats into" in line:
                downloaded_file = line.split("into")[1].strip().replace('"', '')
                break

        if downloaded_file and os.path.exists(downloaded_file):
            print(f"DOWNLOAD_SUCCESS: {downloaded_file}")
        else:
            print(f"DOWNLOAD_FAILED: Could not determine downloaded file path. Stderr: {process.stderr}")
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"DOWNLOAD_FAILED: yt-dlp failed with error:\n{e.stderr}")
        sys.exit(1)
    except Exception as e:
        print(f"DOWNLOAD_FAILED: An unexpected error occurred: {e}")
        sys.exit(1)

