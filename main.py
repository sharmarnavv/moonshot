import os
import time
import re
import ollama
import subprocess
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler
from concurrent.futures import ThreadPoolExecutor

# --- conifg ---
WATCH_FOLDER = os.path.expanduser("~/Desktop")
MODEL_NAME = "moondream"
# Matches default macOS screenshot format
SCREENSHOT_PATTERN = re.compile(r"Screenshot \d{4}-\d{2}-\d{2}.*\.png")

class SmartRenamer(FileSystemEventHandler):
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=3)

    def on_any_event(self, event):
        """debug catch-all to see what's happening."""
        print(f"event: {event.event_type} | {event.src_path}")

    def on_created(self, event):
        if event.is_directory:
            return
        self.check_and_process(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        self.check_and_process(event.dest_path)

    def check_and_process(self, filepath):
        filename = os.path.basename(filepath)
        print(f"debug: checking file: {filename}") # debug print
        
        # Filter
        if not SCREENSHOT_PATTERN.match(filename):
            print(f"DEBUG: Regex did not match: {filename}")
            return

        print(f"debug: match found! queueing {filename}")
        self.executor.submit(self.process_file, filepath, filename)

    def process_file(self, filepath, filename):
        # wait for macos to finish writing the file (floating thumbnail lock)
        time.sleep(3.0)
        print(f"detected: {filename}")
        
        if not self.wait_for_file_ready(filepath):
            print(f"timed out waiting for file: {filename}")
            return

        try:
            new_name = self.get_ai_filename(filepath)
            final_path = self.rename_file(filepath, new_name)
            self.send_notification("Renamed Screenshot", f"{filename} ➡️ {os.path.basename(final_path)}")
        except Exception as e:
            print(f"error processing {filename}: {e}")

    def wait_for_file_ready(self, filepath, timeout=10):
        """waits until file size is stable. added timeout to prevent zombies."""
        historical_size = -1
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                current_size = os.path.getsize(filepath)
                if current_size == historical_size and current_size > 0:
                    return True
                historical_size = current_size
                time.sleep(1)
            except OSError:
                time.sleep(1)
        return False

    def get_ai_filename(self, filepath):
        """Asks Ollama for a description and sanitizes it safely."""
        # improved prompt: ask for a full description, then we summarize it in python.
        prompt = "Describe this image in 3 words or less."
        
        print(f"   asking ollama ({MODEL_NAME}) to describe {os.path.basename(filepath)}...")
        start_t = time.time()
        
        # FIX: Read as bytes to avoid path/unicode issues with Ollama
        try:
            with open(filepath, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            print(f"error reading file: {e}")
            return "unknown_screenshot"

        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [image_bytes]
            }]
        )
        print(f"   ollama replied in {time.time() - start_t:.1f}s")
        
        
        description = response['message']['content'].strip()
        print(f"   ai description: '{description}'")

        # python-side "smart" summarizer
        # 1. remove non-alphanumeric
        clean = re.sub(r'[^\w\s]', '', description.lower())
        # 2. split into words
        words = clean.split()
        # 3. filter out stop words (common filler)
        stop_words = {"a", "an", "the", "image", "of", "screenshot", "showing", "with", "is", "in", "on", "at", "to", "this"}
        keywords = [w for w in words if w not in stop_words]
        
        # 4. take first 4 valid keywords (or words if keywords empty)
        final_words = keywords[:4] if keywords else words[:4]
        
        # 5. join with snake_case
        clean_name = "_".join(final_words)
        
        return clean_name if clean_name else "unknown_screenshot"

    def rename_file(self, old_path, new_name):
        folder = os.path.dirname(old_path)
        extension = os.path.splitext(old_path)[1]
        new_filename = f"{new_name}{extension}"
        new_path = os.path.join(folder, new_filename)

        counter = 1
        while os.path.exists(new_path):
            new_path = os.path.join(folder, f"{new_name}_{counter}{extension}")
            counter += 1

        os.rename(old_path, new_path)
        os.rename(old_path, new_path)
        print(f"   renamed to: {os.path.basename(new_path)}")
        return new_path

    def send_notification(self, title, message):
        """Native macOS notification."""
        try:
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script])
        except Exception:
            pass

if __name__ == "__main__":
    try:
        ollama.list()
    except Exception:
        print(f"could not connect to ollama. is it running? (`ollama serve`)")
        exit(1)

    if not os.access(WATCH_FOLDER, os.R_OK):
        print(f"PERMISSION DENIED: cannot read {WATCH_FOLDER}.")
        print("   please allow your terminal 'Full Disk Access' in System Settings > Privacy & Security.")
        exit(1)
    
    print(f"watching: {os.path.abspath(WATCH_FOLDER)}")

    observer = Observer(timeout=1.0) # Polling every 1 second
    event_handler = SmartRenamer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    
    print(f"smart renamer running on {WATCH_FOLDER}")
    
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        event_handler.executor.shutdown(wait=False) # Kill threads on exit
    observer.join()