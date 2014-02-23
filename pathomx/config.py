# -*- coding: utf-8 -*-
# Experimental data manager
# Loads a csv data file and extracts key information into usable structures for analysis

# Import PyQt5 classes
from PyQt5.QtGui import *
from PyQt5.QtCore import *
#from PyQt5.QtWebKit import *
from PyQt5.QtNetwork import *
from PyQt5.QtWidgets import *
#from PyQt5.QtWebKitWidgets import *
from PyQt5.QtPrintSupport import *
import os
import sys
import re
import base64
import numpy as np
import types

from collections import defaultdict
import operator
import json

from copy import copy, deepcopy

RECALCULATE_ALL = 1
RECALCULATE_VIEW = 2


def build_dict_mapper(mdict):
    rdict = {v: k for k, v in mdict.iteritems()}
    return (
        lambda x: mdict[x] if x in mdict else x,
        lambda x: rdict[x] if x in rdict else x,
        )


# CUSTOM HANDLERS

# QComboBox
def _get_QComboBox(self):
    return self._get_map(self.currentText())


def _set_QComboBox(self, v):
    self.setCurrentText(self._set_map(v))


def _event_QComboBox(self):
    return self.currentTextChanged


# QCheckBox
def _get_QCheckBox(self):
    return self.isChecked()


def _set_QCheckBox(self, v):
    self.setChecked(v)


def _event_QCheckBox(self):
    return self.stateChanged


# QAction
def _get_QAction(self):
    return self.isChecked()


def _set_QAction(self, v):
    self.setChecked(v)


def _event_QAction(self):
    return self.toggled


# QAction
def _get_QPushButton(self):
    return self.isChecked()


def _set_QPushButton(self, v):
    self.setChecked(v)


def _event_QPushButton(self):
    return self.toggled


# QSpinBox
def _get_QSpinBox(self):
    return self.value()


def _set_QSpinBox(self, v):
    self.setValue(v)


def _event_QSpinBox(self):
    return self.valueChanged


# QDoubleSpinBox
def _get_QDoubleSpinBox(self):
    return self.value()


def _set_QDoubleSpinBox(self, v):
    self.setValue(v)


def _event_QDoubleSpinBox(self):
    return self.valueChanged


# QPlainTextEdit
def _get_QPlainTextEdit(self):
    return self.document().toPlainText()


def _set_QPlainTextEdit(self, v):
    self.setPlainText(v)


def _event_QPlainTextEdit(self):
    return self.sourceChangesApplied


# CodeEditor
def _get_CodeEditor(self):
    return self._get_QPlainTextEdit(o)


def _set_CodeEditor(self, v):
    self._set_QPlainTextEdit(o, v)


def _event_CodeEditor(self):
    return self._event_QPlainTextEdit(o)


# QListWidget
def _get_QListWidget(self):
    print 'selected:', [self._get_map(s.text()) for s in self.selectedItems()]
    return [self._get_map(s.text()) for s in self.selectedItems()]


def _set_QListWidget(self, v):
    if v:
        for s in v:
            self.findItems(self._set_map(s), Qt.MatchExactly)[0].setSelected(True)


def _event_QListWidget(self):
    return self.itemSelectionChanged


# ConfigManager handles configuration for a given appview
# Supports default values, change signals, export/import from file (for workspace saving)
class ConfigManager(QObject):

    # Signals
    updated = pyqtSignal(int)  # Triggered anytime configuration is changed (refresh)

    def __init__(self, defaults={}, *args, **kwargs):
        super(ConfigManager, self).__init__(*args, **kwargs)

        self.reset()
        self.defaults = defaults  # Same mapping as above, used when config not set

    # Get config
    def get(self, key):
        if key in self.config:
            return self.config[key]
        elif key in self.defaults:
            return self.defaults[key]
        else:
            return None

    def set(self, key, value, trigger_update=True):
        if key in self.config and self.config[key] == value:
            return False  # Not updating

        # Set value
        self.config[key] = value

        if key in self.handlers:
            # Trigger handler to update the view
            getter = self.handlers[key].getter  # (self, '_get_%s' % self.handlers[key].__class__.__name__, False)
            setter = self.handlers[key].setter  # getattr(self, '_set_%s' % self.handlers[key].__class__.__name__, False)

            if setter and getter() != self.config[key]:
                setter(self.config[key])

        # Trigger update notification
        if trigger_update:
            self.updated.emit(self.eventhooks[key] if key in self.eventhooks else RECALCULATE_ALL)

        return True

    # Defaults are used in absence of a set value (use for base settings)
    def set_default(self, key, value, eventhook=RECALCULATE_ALL):
        self.defaults[key] = value
        self.eventhooks[key] = eventhook
        self.updated.emit(eventhook)

    def set_defaults(self, keyvalues, eventhook=RECALCULATE_ALL):
        for key, value in keyvalues.items():
            self.defaults[key] = value
            self.eventhooks[key] = eventhook

        # Updating the defaults may update the config (if anything without a config value
        # is set by it; should check)
        self.updated.emit(eventhook)
    # Completely replace current config (wipe all other settings)

    def replace(self, keyvalues):
        self.config = []
        self.set_many(keyvalues)

    def set_many(self, keyvalues, trigger_update=True):
        has_updated = False
        for k, v in keyvalues.items():
            u = self.set(k, v, trigger_update=False)
            print 'Workflow config; setting %s to %s' % (k, v)
            has_updated = has_updated or u

        if has_updated and trigger_update:
            self.updated.emit(RECALCULATE_ALL)
    # HANDLERS

    # Handlers are UI elements (combo, select, checkboxes) that automatically update
    # and updated from the config manager. Allows instantaneous updating on config
    # changes and ensuring that elements remain in sync

    def add_handler(self, key, handler, mapper=(lambda x: x, lambda x: x)):


    # Add map handler for converting displayed values to internal config data
        if type(mapper) == dict:  # By default allow dict types to be used
            mapper = build_dict_mapper(mapper)

        handler._get_map, handler._set_map = mapper

        self.handlers[key] = handler

        handler.setter = types.MethodType(globals().get('_set_%s' % handler.__class__.__name__), handler, handler.__class__)
        handler.getter = types.MethodType(globals().get('_get_%s' % handler.__class__.__name__), handler, handler.__class__)
        handler.updater = types.MethodType(globals().get('_event_%s' % handler.__class__.__name__), handler, handler.__class__)

        print "Add handler %s for %s" % (handler.__class__.__name__, key)
        handler.updater().connect(lambda x = None: self.set(key, handler.getter()))

        # Keep handler and data consistent
        if key not in self.config:
            # If the key is in defaults; set the handler to the default state (but don't add to config)
            if key in self.defaults:
                handler.setter(self.defaults[key])

            # If the key is not in defaults, set the config to match the handler
            else:
                self.config[key] = handler.getter()

    def add_handlers(self, keyhandlers):
        for key, handler in keyhandlers.items():
            self.add_handler(key, handler)

    # JSON
    def json_dumps(self):
        return json.dumps(self.config)

    def json_loads(self, json):
        self.config = json.loads(json)

    def reset(self):
        self.config = {}
        self.handlers = {}
        self.defaults = {}
        self.maps = {}
        self.eventhooks = {}
