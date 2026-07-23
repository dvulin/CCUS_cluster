# economics.py
import numpy as np
import pandas as pd

class Economics:
    def __init__(
        self,
        start_year,
        end_year,
        OPEX_per_ton=0.0,
        interest_rate=0.05,
        inflation_rate=0.05,
        price_scenario=0,
        _storage = None, 
        _emitter = None, 
        _transport = None,
    ):

        self._start_year = start_year
        self._end_year = end_year
        self._nsteps = self.end_year - self.start_year + 1
        self._CCS_start_year = None
        
        self.__storage = _storage
        self.__emitter = _emitter
        self.__transport = _transport

        self._OPEX_per_ton = OPEX_per_ton
        self._interest_rate = interest_rate
        self._inflation_rate = inflation_rate
        self._price_scenario = price_scenario

        self._CO2_price = self._generate_CO2_price()

        self._payments = None
        self._payments_future = None
        self._CO2_tax = None
        self._CCS_savings = None
        self._NPV = None

        self._CAPEX = []
        self._OPEX = []

        #self._compute_all_properties()
        
    def _generate_CO2_price(self):
        # Starting at year of 2025, should delete values as years pass by
        scenarios = [
            [64, 94, 105, 115, 122, 129, 131, 135, 140, 144, 144, 145, 146, 149, 150, 151, 153, 154, 157, 157, 160, 163, 166, 170, 173, 184],
            [64, 68, 71, 75, 79, 82, 83, 87, 89, 92, 93, 95, 97, 99, 100, 103, 105, 107, 111, 114, 118, 122, 125, 130, 136, 144],
            [64, 43, 40, 39, 40, 42, 43, 44, 45, 47, 46, 48, 50, 52, 53, 55, 59, 59, 58, 62, 67, 68, 70, 76, 78, 82]
            ]
        
        scenario_names = ['pessimistic', 'conservative', 'optimistic']
        if self._price_scenario in [-1, 0, 1]:
            scenario = self._price_scenario + 1
        elif self._price_scenario.lower() in scenario_names:
            scenario = scenario_names.index(self._price_scenario.lower())
        else:
            scenario = 0
            
        CO2_prices = scenarios[scenario]
        CO2_prices = CO2_prices[:self._nsteps]
        return CO2_prices
    
    def set_cash_flow(self):
        """
        very extendable (kind of) abstract method

        Returns
        -------
        sets various properties taht describe elements of cash flow time series

        """
        self._compute_all_properties()

    def _compute_all_properties(self):
        """
        set of hidden properties to display them as "read only properties"/getters
        
        Returns
        -------
        """
        self.__payments = self._calc_payments()
        self.__payments_future = self._calc_payments_future_values()
        if self.__emitter:
            self.__CO2_tax = self._calc_CO2_tax()
            self.__CCS_savings = self._calc_CCS_savings()
        self.__NPV = self._calc_CCS_NPV()

    def _calc_payments(self):
        return self._CAPEX + self._OPEX

    def _calc_payments_future_values(self):
        """
        these are costs of CCS implementation (non-discountable OPEX)

        Returns
        -------
        pfv : real
            payments with inflation rate

        """
        pfv = np.zeros(self._nsteps, dtype=float)
        idx_start = self._CCS_start_year - self._start_year
        for i in range(self._nsteps):
            t_rel = max(0, i - idx_start)
            pfv[i] = self.__payments[i] * (1.0 + self.inflation_rate) ** t_rel
        return pfv

    def _calc_CO2_tax(self):
        return self._CO2_price * self.emissions

    def _calc_CCS_savings(self):
        savings = np.zeros(self._nsteps, dtype=float)
        for i in range(self._nsteps):
            if self.__payments_future[i] > 0:
                savings[i] = self.__CO2_tax[i] - self.__payments_future[i]
            else:
                savings[i] = -self.__CO2_tax[i]
        return savings

    def _calc_CCS_NPV(self):
        npv_arr = np.zeros(self._nsteps, dtype=float)
        idx_start = self._CCS_start_year - self._start_year
        for i in range(1, self._nsteps):
            t_rel = max(0, i - idx_start)
            if self.__emitter:
                npv_arr[i] = -self._CAPEX[i] + npv_arr[i - 1] + self.__CCS_savings[i] * ((1.0 + self.interest_rate) ** t_rel)
            else:
                npv_arr[i] = -self._CAPEX[i] + npv_arr[i - 1] + self._OPEX[i] * ((1.0 + self.interest_rate) ** t_rel)
        return npv_arr
    
    @property
    def end_year(self):
        return self._end_year
    
    @property
    def start_year(self):
        return self._start_year
    
    @property 
    def CCS_start_year(self):
        return self._CCS_start_year
    
    @CCS_start_year.setter
    def CCS_start_year(self, value):
        self._CCS_start_year = value
    
    @property
    def CAPEX(self):
        return self._CAPEX

    @CAPEX.setter
    def CAPEX(self, value):
        if isinstance(value, (float, int)):
            self._CAPEX = np.zeros(self._nsteps, dtype=float)
            idx = self._CCS_start_year - self._start_year
            if 0 <= idx < self._nsteps:
                self._CAPEX[idx] = float(value)
        else:
            arr = np.array(value, dtype=float)
            if len(arr) != self._nsteps:
                raise ValueError("CAPEX array length mismatch.")
            self._CAPEX = arr

    @property
    def OPEX(self):
        return self._OPEX

    @OPEX.setter
    def OPEX(self, arg):
        self._OPEX = arg

    def set_OPEX(self, CO2_flow=None):
        if isinstance(CO2_flow, (list)):
            CO2_flow = np.array([CO2_flow], dtype=float)
        elif isinstance(CO2_flow, (int, float)):
            CO2_flow = np.array([CO2_flow]*self.nsteps, dtype=float)
        elif isinstance(CO2_flow, np.ndarray):
            pass
        else:
            CO2_flow = self.emissions
        
        self._OPEX= self._OPEX_per_ton * CO2_flow
        self._OPEX[:(self.CCS_start_year - self.start_year+1)] = 0

    @property
    def payments(self):
        return self.__payments

    @property
    def payments_future_values(self):
        return self.__payments_future

    @property
    def CO2_tax(self):
        return self.__CO2_tax

    @property
    def CCS_savings(self):
        return self.__CCS_savings

    @property
    def NPV(self):
        return self.__NPV

    @property
    def OPEX_per_ton(self):
        return self._OPEX_per_ton

    @OPEX_per_ton.setter
    def OPEX_per_ton(self, value):
        self._OPEX_per_ton = float(value)

    @property
    def inflation_rate(self):
        return self._inflation_rate

    @inflation_rate.setter
    def inflation_rate(self, val):
        self._inflation_rate = float(val)
        self._compute_all_properties()

    @property
    def interest_rate(self):
        return self._interest_rate

    @interest_rate.setter
    def interest_rate(self, val):
        self._interest_rate = float(val)
        self._compute_all_properties()

    @property
    def CO2_price(self):
        return self._CO2_price
    
    @property
    def nsteps(self):
        return self._nsteps
