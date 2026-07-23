# domain/ccs_chain.py
import numpy as np
from economics import Economics

class Storage(Economics):
    def __init__(
        self,
        name,
        storage_type,
        capacity,
        start_year,
        end_year,
        CCS_start_year,
    ):
        super().__init__(start_year, end_year, _storage = True)
        self._name = name
        self._storage_type = storage_type           # DSA, DHF
        self._capacity = capacity
        self._injection_rate = []
        self._depth = None
        

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if value is not None:
            self._name = value

    @property
    def storage_type(self):
        return self._storage_type

    @storage_type.setter
    def storage_type(self, value):
        if value in ["DSA", "DHF"]:
            self._storage_type = value

    @property
    def capacity(self):
        return self._capacity

    @capacity.setter
    def capacity(self, value):
        if value is not None:
            self._capacity = value

    @property
    def injection_rate(self):
        return self._injection_rate

    # Setter for injection_rate
    @injection_rate.setter
    def injection_rate(self, value):
        if isinstance(value, list):
            self._injection_rate = value
        else:
            self._injection_rate = np.array([value]*self._time_steps)

    # Getter for depth
    @property
    def depth(self):
        return self._depth

    # Setter for depth
    @depth.setter
    def depth(self, value):
        if value is not None:
            self._depth = value

   
    
"-------------------------------------------- Transport ---------------------------------------"
class Transport(Economics):
    def __init__(
        self,
        start_year,
        end_year
    ):
        super().__init__(start_year, end_year, _transport = True)
        self._section_name = 'section'
        self._flow_rate = None          # t/year
        self._transport_type = None
        self._distance = None
        self._CCS_start_year = None

    @property
    def transport_type(self):
        if not self._transport_type:
            return None
        else:
            return self._transport_type

    @property
    def distance(self):
        return self._distance
        
    @property
    def flow_rate(self):
        return self._flow_rate

    @flow_rate.setter
    def flow_rate(self, value):
        if value is not None:
            self._flow_rate = value
    
    @property
    def section_name(self):
        return self._section_name
    
    @section_name.setter
    def section_name(self, value):
        self._section_name = value


"-------------------------------------------- Emitter ---------------------------------------"
class Emitter(Economics):
    def __init__(
        self,
        name,
        emissions,
        start_year,
        end_year
    ):
        super().__init__(start_year, end_year, _emitter=True)
        self._name = name
        self._emissions = np.array([emissions], dtype=float)
        if len(self._emissions) == 1:
            self.emissions_change()
        self._capture_technology = None
        
    @property
    def capture_technology(self):
        return self._capture_technology
    
    @capture_technology.setter
    def capture_technology(self, value):
        capture_techs = ["PI", "NI", "OXY"]
        if value not in capture_techs:
            raise ValueError(f'one of capture techs expected {capture_techs}, passed {value}')
        self._capture_technology = value
           
    @property
    def name(self):
        return self._name

    @property
    def emissions(self):
        return self._emissions

    @emissions.setter
    def emissions(self, arr):
        if isinstance(arr, (list, np.ndarray)):
            pass
        else:
            self._emissions = np.array([arr]*self.nsteps, dtype=float)

    def emissions_change(self, a=0.0, c=1.0):
        yrs = self.nsteps
        if len(self._emissions) == 0:
            return
        E0 = self._emissions[0]
        b = a * E0
        new_vals = []
        for t in range(yrs):
            ec_t = E0 + b * (t ** c)
            new_vals.append(ec_t)
        self._emissions = np.array(new_vals, dtype=float)
