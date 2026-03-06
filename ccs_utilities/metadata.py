# -*- coding: utf-8 -*-
"""
Created on Wed Jul  9 23:54:11 2025

@author: domagoj
"""

class ParamMetadata:
    """
    Base class for OOP CCS classes with parameter metadata, readable get/set/str behavior.
    You can inherit from this class to avoid repeating code for parameter dict/metadata, __getattr__, __setattr__, etc.
    """
    PARAM_METADATA = {}
    def __init__(self, **kwargs):
        self.params = {k: None for k in self.PARAM_METADATA}
        for k, v in kwargs.items():
            if k in self.PARAM_METADATA:
                self.params[k] = v

    def get_param(self, param):
        if param in self.params:
            unit, desc = self.PARAM_METADATA[param]
            return {'value': self.params[param], 'unit': unit, 'description': desc}
        return None

    def __getattr__(self, name):
        if name in self.params:
            return self.params[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name != 'params' and hasattr(self, 'PARAM_METADATA') and name in self.PARAM_METADATA:
            self.params[name] = value
        else:
            super().__setattr__(name, value)

    def __str__(self):
        return "\n".join(
            f"{param}: {self.params[param]} [{self.PARAM_METADATA[param][0]}]" for param in self.params
            )