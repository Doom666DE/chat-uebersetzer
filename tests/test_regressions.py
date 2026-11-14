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
    @contextmanager
    def window(self, scale=None):
        with (
            TemporaryDirectory() as directory,
            patch.object(app, "PREFERENCES", Path(directory) / "interface-language.txt"),
            patch.object(app, "watch_mouse"),
            patch.object(app.TranslatorWindow, "translate_jobs"),
            patch.object(app.TranslatorWindow, "arrange"),
            patch.object(app, "is_foreground", return_value=True),
        ):
            root = tk.Tk()
            if scale is not None:
                root.tk.call("tk", "scaling", scale)
            ui = app.TranslatorWindow(root)
            try:
                yield root, ui
            finally:
                for pending in root.tk.splitlist(root.tk.call("after", "info")):
                    root.after_cancel(pending)
                ui.close()

    def test_unknown_selection_requires_explicit_target(self):
        with self.window() as (_, ui):
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

    def test_edited_reply_survives_selection_and_failed_replacement(self):
        with self.window() as (_, ui):
            ui.start_translation(1, "Cześć!")
            ui.apply_detected_language("pl")
            ui.draft.insert("1.0", "Hallo")
            ui.start_reply()
            ui.events.put(("result", "reply", ui.reply_number, "Cześć"))
            ui.read_events()
            ui.reply_output.insert("end-1c", " 😊")
            ui.start_translation(1, "Jak się masz?")
            ui.apply_detected_language("pl")
            self.assertEqual(ui.status_messages[ui.reply_output_label][0], "translated_reply_language")
            ui.start_translation(1, "Merhaba!")
            ui.apply_detected_language("tr")
            self.assertEqual(ui.status_messages[ui.reply_output_label], ("previous_reply_language", {"language": "pl"}))
            with patch.object(app, "win32clipboard") as clipboard:
                ui.copy_button.invoke()
                clipboard.SetClipboardText.assert_called_once_with("Cześć 😊", app.win32con.CF_UNICODETEXT)
            ui.draft.replace("1.0", "end-1c", "Bis später!")
            ui.start_reply()
            request = ui.reply_number
            ui.events.put(("partial", "reply", request, "Sonra"))
            ui.events.put(("error", "reply", request, app.UserError("translate_failed")))
            ui.read_events()
            self.assertEqual(ui.reply_output.get("1.0", "end-1c"), "Cześć 😊")
            ui.start_reply()
            ui.events.put(("result", "reply", request, "stale"))
            ui.events.put(("result", "reply", ui.reply_number, "Sonra görüşürüz!"))
            ui.read_events()
            self.assertEqual(ui.reply_output.get("1.0", "end-1c"), "Sonra görüşürüz!")
            self.assertEqual(ui.status_messages[ui.reply_output_label], ("translated_reply_language", {"language": "tr"}))

    def test_copy_button_fits_at_minimum_window_size(self):
        for scale in (1.33, 2.0):
            with self.window(scale=scale) as (root, ui):
                width, height = root.minsize()
                root.geometry(f"{width}x{height}")
                ui.tabs.select(1)
                for language in ("de", "en"):
                    ui.interface_picker.set(app.INTERFACE_LANGUAGES[language])
                    ui.change_interface()
                    ui.set_reply_target("pl")
                    ui.show_reply("Cześć!", finished=True)
                    ui.set_reply_target(None)
                    ui.set_status(ui.language_status, "unknown")
                    ui.set_status(ui.reply_status, "copied")
                    root.update_idletasks()
                    with self.subTest(scale=scale, language=language):
                        self.assertTrue(ui.copy_button.winfo_viewable())
                        bottom = ui.copy_button.winfo_rooty() + ui.copy_button.winfo_height()
                        self.assertLessEqual(bottom, root.winfo_rooty() + root.winfo_height())
                        self.assertGreaterEqual(ui.reply_output.winfo_height(), 30)


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
