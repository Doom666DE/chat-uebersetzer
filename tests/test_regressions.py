from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pywintypes

import app_update as updater
import chat_uebersetzer as app


class UpdateTests(unittest.TestCase):
    def test_recovers_when_windows_moves_old_file_and_then_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / ".chat-update-test"
            folder.mkdir()
            target = root / "Translator.exe"
            target.write_bytes(b"previous file")
            payload = folder / updater.ASSET
            payload.write_bytes(b"new file")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            args = ["--apply-update", str(target), digest, "1", "2",
                    updater.EVENT_PREFIX + "1" * 32, "en"]

            def fail_after_move(source, target_path, backup):
                target_path.rename(backup)
                raise pywintypes.error(1177, "ReplaceFile", "simulated incomplete replacement")

            with (
                patch.object(updater, "is_portable", return_value=True),
                patch.object(updater.sys, "executable", str(folder / updater.HELPER)),
                patch.object(updater, "wait_for_exit"),
                patch.object(updater, "replace_executable", side_effect=fail_after_move),
                patch.object(updater, "start_independently") as restart,
                patch.object(updater.win32api, "MessageBox") as dialog,
            ):
                self.assertTrue(updater.apply_update(args))

            self.assertEqual(target.read_bytes(), b"previous file")
            self.assertEqual(payload.read_bytes(), b"new file")
            self.assertEqual(restart.call_args.args[0][0], str(target))
            self.assertIn("previous version is still available", dialog.call_args.args[1])


class ReplyLanguageTests(unittest.TestCase):
    def test_unknown_selection_requires_explicit_target(self):
        with (
            TemporaryDirectory() as directory,
            patch.object(app, "PREFERENCES", Path(directory) / "interface-language.txt"),
            patch.object(app, "watch_mouse"),
            patch.object(app.TranslatorWindow, "translate_jobs"),
            patch.object(app.TranslatorWindow, "arrange"),
            patch.object(app, "is_foreground", return_value=True),
        ):
            root = tk.Tk()
            ui = app.TranslatorWindow(root)
            try:
                ui.start_translation(1, "Cześć!")
                ui.apply_detected_language("pl")
                self.assertEqual(ui.target, "pl")
                ui.start_translation(1, "OK")
                ui.apply_detected_language(None)
                ui.draft.insert("1.0", "I will call tomorrow.")
                ui.start_reply()
                self.assertIsNone(ui.target)
                self.assertTrue(ui.reply_translate.instate(["disabled"]))
                self.assertFalse(any(job[0] == "reply" for job in ui.jobs.queue))
                ui.target_picker.current(list(app.REPLY_LANGUAGES).index("de"))
                ui.select_reply_language(None)
                ui.start_reply()
                self.assertEqual(ui.jobs.queue[-1][-1], "de")
                ui.apply_detected_language("tr")
                self.assertEqual(ui.target, "de")
            finally:
                for pending in root.tk.splitlist(root.tk.call("after", "info")):
                    root.after_cancel(pending)
                ui.close()


class TextTests(unittest.TestCase):
    def test_preserves_paragraphs_at_chunk_boundaries(self):
        @contextmanager
        def echo(_path, payload, _cancelled):
            text = payload["messages"][-1]["content"]
            response = {"message": {"content": text}, "done": True}
            yield io.BytesIO((json.dumps(response) + "\n").encode())

        text = ("one long paragraph " * 140).strip() + "\n\n" + ("second paragraph " * 110).strip()
        with patch.object(app, "require_local_model"), patch.object(app, "ollama_request", side_effect=echo):
            self.assertEqual(app.translate(text, Event(), lambda _: None), text)

    def test_discord_selection_outside_message_rows_is_ignored(self):
        span = SimpleNamespace(CompareEndpoints=lambda *args: -1)
        ranges = SimpleNamespace(Length=1, GetElement=lambda _: span)
        pattern = SimpleNamespace(GetSelection=lambda: ranges)
        document = SimpleNamespace(
            GetCurrentPattern=lambda _: SimpleNamespace(QueryInterface=lambda _: pattern),
            FindAll=lambda *_: SimpleNamespace(Length=0),
        )
        automation = SimpleNamespace(
            ElementFromHandle=lambda _: SimpleNamespace(FindFirst=lambda *_: document),
            CreatePropertyCondition=lambda *_: None,
        )
        uia = SimpleNamespace(TreeScope_Descendants=0, UIA_ControlTypePropertyId=0,
                              UIA_DocumentControlTypeId=0, UIA_TextPatternId=0, IUIAutomationTextPattern=0,
                              TextPatternRangeEndpoint_Start=0, TextPatternRangeEndpoint_End=1,
                              UIA_ListItemControlTypeId=0)
        self.assertEqual(app.read_selected_text(automation, uia, 1), "")

    def test_cancellation_interrupts_stalled_ollama_response(self):
        request_arrived = Event()
        release_server = Event()
        cancelled = Event()
        result = []

        class StalledServer(BaseHTTPRequestHandler):
            def do_GET(self):
                request_arrived.set()
                release_server.wait(4)

        with ThreadingHTTPServer(("127.0.0.1", 0), StalledServer) as server:
            http = app.HTTPConnection
            server_thread = Thread(target=server.serve_forever)
            server_thread.start()

            def request():
                try:
                    with app.ollama_request("/api/tags", cancelled=cancelled):
                        pass
                except InterruptedError:
                    result.append("cancelled")

            with patch.object(app, "HTTPConnection", side_effect=lambda host, _port, **options:
                              http(host, server.server_port, **options)):
                worker = Thread(target=request)
                worker.start()
                try:
                    self.assertTrue(request_arrived.wait(3))
                    cancelled.set()
                    worker.join(2)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(result, ["cancelled"])
                finally:
                    release_server.set()
                    worker.join(5)
                    server.shutdown()
                    server_thread.join(5)


if __name__ == "__main__":
    unittest.main()
