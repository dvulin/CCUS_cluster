# -*- coding: utf-8 -*-
"""
Created on Wed Jul  9 23:40:36 2025

@author: domagoj
"""

from .metadata import ParamMetadata

class Pipeline(ParamMetadata):
    PARAM_METADATA = {
        'm_dot': ('kg/s', 'Maseni protok CO2')
    }

    def __init__(self, inputs):
        super().__init__(**{k: getattr(inputs, k) for k in self.PARAM_METADATA})
        self.inputs = inputs
    
    def calculate_pressure_drop(self, m_dot, length, diameter):
        """Calculate pipeline pressure drop (to be implemented)."""
        pass