"""Expose Tk controls through Windows' HWND accessibility annotations."""

from ctypes import windll
from tkinter import TclError

from comtypes import COMError, GUID
from comtypes.client import CreateObject, GetModule


OBJID_CLIENT = 0xFFFFFFFC
CHILDID_SELF = 0
NAME = GUID("{608D3DF8-8128-4AA7-A428-F55E49267291}")
UIA_NAME = GUID("{C3A6921B-4A99-44F1-BCA6-61187052C431}")
ROLE = GUID("{CB905FF2-7BD1-4C05-B3C8-E2C241364D70}")
CONTROL_TYPE = GUID("{CA774FEA-28AC-4BC2-94CA-ACEC6D6C10A3}")
VALUE = GUID("{123FE443-211A-4615-9527-C45A7E93717A}")
UIA_VALUE = GUID("{E95F5E64-269F-4A85-BA99-4092C3EA2986}")
READ_ONLY = GUID("{EB090F30-E24C-4799-A705-0D247BC037F8}")
ENABLED = GUID("{2109427F-DA60-4FED-BF1B-264BDCE6EB3A}")
FOCUSABLE = GUID("{F7B8552A-0859-4B37-B9CB-51E72092F29F}")
LIVE_SETTING = GUID("{C12BCD8E-2A8E-4950-8AE7-3625111D58EB}")
PROPERTIES = (GUID * 10)(NAME, UIA_NAME, ROLE, CONTROL_TYPE, VALUE, UIA_VALUE, READ_ONLY, ENABLED,
                        FOCUSABLE, LIVE_SETTING)
ROLES = {
    "button": (0x2B, 50000),
    "choice": (0x2E, 50003),
    "edit": (0x2A, 50004),
    "tabs": (0x3C, 50018),
    "text": (0x29, 50020),
}
EVENT_FOCUS = 0x8005
EVENT_NAME = 0x800C
EVENT_VALUE = 0x800E
EVENT_LIVE_REGION = 0x8019


class Accessibility:
    def __init__(self):
        self.controls = {}
        try:
            module = GetModule("oleacc.dll")
            self.service = CreateObject(module.CAccPropServices, interface=module.IAccPropServices)
        except (OSError, COMError, ImportError):
            self.service = None

    def register(self, widget, role, read_name, *, read_value=None, live=False):
        if self.service is None:
            return widget
        hwnd = widget.winfo_id()
        identity = (hwnd, OBJID_CLIENT, CHILDID_SELF)
        legacy_role, control_type = ROLES[role]
        try:
            self.service.SetHwndProp(*identity, ROLE, legacy_role)
            self.service.SetHwndProp(*identity, CONTROL_TYPE, control_type)
            self.service.SetHwndProp(*identity, FOCUSABLE, role != "text")
            if live:
                self.service.SetHwndProp(*identity, LIVE_SETTING, 1)  # Polite
        except COMError:
            self.clear(widget, identity)
            return widget
        self.controls[widget] = (identity, role, read_name, read_value, live, {})
        widget.bind("<Destroy>", lambda _event: self.clear(widget, identity), add="+")
        if role != "text":
            widget.bind("<FocusIn>", lambda _event: self.refresh(widget, EVENT_FOCUS), add="+")
        self.refresh(widget)
        return widget

    def clear(self, widget, identity):
        self.controls.pop(widget, None)
        try:
            self.service.ClearHwndProps(*identity, PROPERTIES, len(PROPERTIES))
        except COMError:
            pass

    def refresh(self, widget, event=None):
        if widget not in self.controls:
            return
        identity, role, read_name, read_value, live, previous = self.controls[widget]
        try:
            name = read_name()
            if previous.get("name") != name:
                self.service.SetHwndPropStr(*identity, NAME, name)
                self.service.SetHwndPropStr(*identity, UIA_NAME, name)
                previous["name"] = name
                if live and name and widget.winfo_viewable():
                    self.notify(identity, EVENT_LIVE_REGION)
                elif widget.winfo_viewable():
                    self.notify(identity, EVENT_NAME)
            if role in ("button", "choice") and "state" in widget.keys():
                disabled = widget.instate(["disabled"]) if hasattr(widget, "instate") else widget["state"] == "disabled"
                if previous.get("disabled") != disabled:
                    self.service.SetHwndProp(*identity, ENABLED, not disabled)
                    previous["disabled"] = disabled
            if role in ("edit", "choice"):
                read_only = role == "choice" or widget["state"] == "disabled"
                if previous.get("read_only") != read_only:
                    self.service.SetHwndProp(*identity, READ_ONLY, read_only)
                    previous["read_only"] = read_only
            if read_value is not None:
                value = read_value()
                if previous.get("value") != value:
                    self.service.SetHwndPropStr(*identity, VALUE, value)
                    self.service.SetHwndPropStr(*identity, UIA_VALUE, value)
                    previous["value"] = value
                    if event != EVENT_FOCUS and widget == widget.focus_get():
                        self.notify(identity, EVENT_VALUE)
            if event is not None:
                self.notify(identity, event)
        except (COMError, TclError):
            pass

    @staticmethod
    def notify(identity, event):
        hwnd, object_id, child_id = identity
        windll.user32.NotifyWinEvent(event, hwnd, object_id, child_id)
