"""Bounded JSON-lines client for the isolated, programmatic Rime C API probe."""
from pathlib import Path
import json
import queue
import subprocess
import threading


class EngineProbe:
    def __init__(self, executable, dll, shared, user, *, schema="study"):
        user = Path(user)
        user.mkdir(parents=True, exist_ok=True)
        self.queue = queue.Queue()
        self.error_log = (user / "engine-probe.log").open("wb")
        self.process = subprocess.Popen([str(executable), str(dll), str(shared), str(user), schema],
            cwd=user, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_log,
            text=True, encoding="utf-8", bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.queue.put(json.loads(line))
                except ValueError:
                    self.queue.put(RuntimeError("Unexpected probe output: " + line[:200]))
        finally:
            self.queue.put(None)

    def receive(self, timeout=20):
        try:
            result = self.queue.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Rime probe response timed out") from None
        if result is None: raise RuntimeError("Rime probe exited before completing the request")
        if isinstance(result, Exception): raise result
        return result

    def command(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        return self.receive()

    def find(self, pinyin, chinese, *, pages=30):
        self.command("clear")
        current = self.command("type " + pinyin)
        first_page = [item["text"] for item in current["candidates"]]
        for _ in range(pages):
            for index, candidate in enumerate(current["candidates"]):
                if candidate["text"] == chinese:
                    return current, index
            if current["last"]: break
            current = self.command("key 65366 0")
        raise ValueError("Expected word absent from first " + str(pages) + " pages; first page: " + repr(first_page))

    def close(self):
        try:
            if self.process.poll() is None:
                self.process.stdin.write("quit\n")
                self.process.stdin.flush()
                self.process.stdin.close()
                if self.process.wait(timeout=15): raise RuntimeError("Rime probe exited unsuccessfully")
            elif self.process.returncode:
                raise RuntimeError("Rime probe exited " + str(self.process.returncode))
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self.reader.join(timeout=2)
            self.process.stdout.close()
            self.error_log.close()
