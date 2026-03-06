# -*- coding: utf-8 -*-

"""

Created on Sat Jul 12 20:53:10 2025

@author: domagoj

Extended visualization methods for GT_CCS_engineering comprehensive analysis

"""

import matplotlib.pyplot as plt
import numpy as np

class Visualization:

    def __init__(self):
        self._set_plot_style()

    def _set_plot_style(self):
        plt.style.use('ggplot')
        plt.rcParams.update({
            'figure.facecolor': 'white',
            'font.family': 'serif',
            'font.size': 12,
            'text.color': 'black',
            'axes.labelcolor': 'black',
            'axes.titlesize': 12,
            'axes.labelsize': 12,
            'xtick.labelsize': 10,
            'xtick.color': 'black',
            'ytick.labelsize': 10,
            'ytick.color': 'black',
            'legend.fontsize': 10,
            'figure.facecolor': 'white',
            'axes.facecolor': 'white',
            'grid.color': 'lightgray',
            'grid.linewidth': 0.5, # Thinner grid lines
            'axes.spines.left': True,
            'axes.spines.bottom': True,
            'axes.spines.top': False,
            'axes.spines.right': False,
            'axes.linewidth': 1.0,
        })

    def time_vs_CO2_stored_vs_bhp_vs_whp(self, mbal_df, bhp_df):
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('Uskladišteni CO₂ [Mt]', color='tab:blue')
        ax1.plot(mbal_df['Time, yr'], mbal_df['m_CO2, Mt'], color='tab:blue', label='Uskladišteni CO₂')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5) # Thinner grid
        ax1.legend(loc='lower right', bbox_to_anchor=(0.95, 0.35)) # Avoid overlap
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('tlak [bar]', color='tab:red')
        ax2.plot(bhp_df['Time [yr]'], bhp_df['BHP [bar]'], color='tab:green', label='BHP')
        ax2.plot(mbal_df['Time, yr'], mbal_df['DSA pressure, bar'], color='tab:red', label='DSA tlak')
        ax2.plot(bhp_df['Time [yr]'], bhp_df['CO2 WHP [bar]'], color='tab:purple', label='WHP')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='lower right', bbox_to_anchor=(1, 0.1)) # Avoid overlap
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)

        fig.tight_layout()
        fig.savefig('time_vs_co2_stored_bhp_whp_dsa.png', dpi=600)
        plt.show()

    def s_eff_vs_co2_stored_kr_co2(self, bhp_df, mbal_df):
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('efektivno zasićenje CO₂')
        ax1.set_ylabel('Uskladišteni CO₂ [Mt]', color='tab:blue')
        ax1.plot(bhp_df['S_eff'], mbal_df['m_CO2, Mt'], color='tab:blue', label='Uskladišteni CO₂')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5) # Thinner grid
        ax1.legend(loc='upper left', bbox_to_anchor=(0.05, 0.9)) # Avoid overlap
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('kr_co₂ [-]', color='tab:red')
        ax2.plot(bhp_df['S_eff'], bhp_df['kr_co2'], color='tab:red', label='kr_co₂')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='lower right', bbox_to_anchor=(0.9, 0.1)) # Avoid overlap
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)

        plt.xlim(0, 1)
        #plt.title('S_uk vs Uskladišteni CO₂ i kr_co₂')
        fig.tight_layout()
        fig.savefig('s_eff_vs_co2_stored_kr_co2.png', dpi = 600)
        plt.show()

    def bhp_vs_density_viscosity(self, bhp_df):
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('BHP [bar]')
        ax1.set_ylabel('gustoća [kg/m³]', color='tab:blue')
        ax1.plot(bhp_df['BHP [bar]'], bhp_df['density at BHP'], color='tab:blue', label='gustoća')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5) # Thinner grid
        ax1.legend(loc='upper left', bbox_to_anchor=(0.1, 0.9)) # Avoid overlap
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('viskoznost [mPas]', color='tab:red')
        ax2.plot(bhp_df['BHP [bar]'], bhp_df['viscosity at BHP [mPas]'], color='tab:red', label='viskoznost')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='lower right', bbox_to_anchor=(1, 0.2)) # Avoid overlap
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)

        #plt.title('BHP vs Gustoća i Viskoznost')
        fig.tight_layout()
        fig.savefig('bhp_vs_density_viscosity.png', dpi = 600)
        plt.show()

    def time_vs_power_vs_bhp_vs_pDSA(self, mbal_df, vfp_df):
        """
        Plots time vs compression power (left axis), and
        BHP, geological storage formation pressure ~ pDSA (right y-axis).
        """
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('snaga kompresora [kW]', color='tab:red')
        ax1.plot(vfp_df['Time [yr]'], vfp_df['CO2 comp. P [kW]'], color='tab:red', label='Snaga kompresora')
        ax1.tick_params(axis='y', labelcolor='tab:red')
        ax1.grid(True, linestyle=':', linewidth=0.5) # Thinner grid
        ax1.legend(loc='lower right', bbox_to_anchor=(0.95, 0.35)) # Avoid overlap
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:red')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('tlak [bar]', color='tab:blue')
        ax2.plot(vfp_df['Time [yr]'], vfp_df['BHP [bar]'], color='tab:green', label='BHP')
        ax2.plot(mbal_df['Time, yr'], mbal_df['DSA pressure, bar'], color='tab:blue', label='DSA tlak')
        ax2.tick_params(axis='y', labelcolor='tab:blue')
        ax2.legend(loc='lower right', bbox_to_anchor=(1, 0.1)) # Avoid overlap
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:blue')
        ax2.spines['right'].set_linewidth(1.0)

        fig.tight_layout()
        fig.savefig('time_vs_power_bhp_pDSA.png', dpi=600)
        plt.show()


    def time_vs_geothermal_flow_temperature(self, mbal_df, vfp_gt_df):
        """
        Prikazuje vremensku evoluciju geotermalne proizvodnje:
        protok geotermalne vode (lijeva os) i proizvodnu temperaturu (desna os).
        """
        font_title = 16
        font_labels = 14
        font_ticks = 12
        font_legend = 1
        
        fig, ax1 = plt.subplots(figsize=(10, 6))
        ax1.set_xlabel('vrijeme [god]', fontsize = font_labels)
        ax1.set_ylabel('protok geotermalne vode [kg/s]', color='tab:blue', fontsize = font_labels)
        ax1.plot(mbal_df['Time, yr'], mbal_df['m_dot geothermal [kg/s]'], 
                color='tab:blue', linewidth=2, label='m_dot geotermalna voda')
        ax1.tick_params(axis='x', labelsize=font_ticks)
        ax1.tick_params(axis='y', labelcolor='tab:blue', labelsize=font_ticks)
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        ax1.legend(loc='upper left', bbox_to_anchor=(0.05, 0.95))
        
        # 1. SPRIJEČI ZNANSTVENI FORMAT NA OSI
        # Postavlja običan numerički format umjesto znanstvenog
        ax1.ticklabel_format(style='plain', axis='y')
        
        # 2. POSTAVI GRANICE ZA PRIMARNU OS (lijevu)
        y_min1, y_max1 = ax1.get_ylim()
        
        # Zaokruži granice na "lijepo" vrijeme
        y_min1 = max(0, np.floor(y_min1))  # Osiguraj da donja granica nije negativna
        y_max1 = np.ceil(y_max1)
        
        # Ako je raspon vrlo mali, proširi ga za bolji prikaz
        if y_max1 - y_min1 < 1:
            y_max1 = y_min1 + 1
        
        ax1.set_ylim(y_min1, y_max1)
        
        # Dodaj crte za osi
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)
    
        ax2 = ax1.twinx()
        ax2.set_ylabel('proizvodna temperatura [°C]', color='tab:red')
        ax2.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['prod t, °C'], 
                color='tab:red', linewidth=2, linestyle='--', label='T proizvodnja')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='upper right', bbox_to_anchor=(0.95, 0.95))
        
        # 1. SPRIJEČI ZNANSTVENI FORMAT NA OSI (za sekundarnu os)
        ax2.ticklabel_format(style='plain', axis='y')
        
        # 2. POSTAVI GRANICE ZA SEKUNDARNU OS (desnu)
        y_min2, y_max2 = ax2.get_ylim()
        
        # Zaokruži granice na cijele brojeve
        y_min2 = max(0, np.floor(y_min2))  # Temperatura ne može biti negativna
        y_max2 = np.ceil(y_max2)
        
        # Provjeri da je maksimalna temperatura manja od tipične maksimalne geotermalne temperature
        if y_max2 > 200:
            y_max2 = 200
        
        # Provjeri da je minimalna temperatura veća od tipične minimalne temperature
        if y_min2 < 30:
            y_min2 = 30
        
        ax2.set_ylim(y_min2, y_max2)
        
        # Dodaj desnu os
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)
    
        fig.tight_layout()
        fig.savefig('time_vs_geothermal_flow_temperature.png', dpi=600, bbox_inches='tight')
        plt.show()

    def time_vs_power(self, vfp_gt_df, vfp_co2_df):
        """
        Prikazuje vremensku evoluciju snaga u GT-CCS sustavu:
        ORC snaga, snaga pumpe, neto GT snaga i snaga CO₂ kompresije.
        """
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('snaga [kW]', color='black')
        ax1.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['ORC power, kW'], 
                color='tab:blue', linewidth=2, label='ORC snaga')
        ax1.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['pump power, kW'], 
                color='tab:orange', linewidth=2, linestyle=':', label='snaga pumpe')
        ax1.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['net power GT, kW']-vfp_co2_df['CO2 comp. P [kW]'], 
                color='tab:green', linewidth=2, linestyle='--', label='ukupna neto snaga')
        ax1.plot(vfp_co2_df['Time [yr]'], vfp_co2_df['CO2 comp. P [kW]'], 
                color='tab:red', linewidth=2, linestyle='-.', label='CO₂ kompresija')
        ax1.tick_params(axis='y', labelcolor='black')
        ax1.grid(True, linestyle=':', linewidth=0.5)
        ax1.legend(loc='upper left', bbox_to_anchor=(0.05, 0.95))
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('black')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)
    
        fig.tight_layout()
        fig.savefig('time_vs_power.png', dpi=600)
        plt.show()


    def time_vs_co2_density_vs_geothermal_density(self, mbal_df):
        """
        Usporedba gustoće uskladištenog CO₂ i geotermalne vode kroz vrijeme.
        """
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('gustoća CO₂ [kg/m³]', color='tab:blue')
        ax1.plot(mbal_df['Time, yr'], mbal_df['CO2_stored density, kg/m³'], 
                color='tab:blue', linewidth=2, label='ρ CO₂ uskladišten')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5)
        ax1.legend(loc='upper left', bbox_to_anchor=(0.05, 0.95))
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('gustoća geotermalne vode [kg/m³]', color='tab:red')
        ax2.plot(mbal_df['Time, yr'], mbal_df['rho geoth. [kg/m3]'], 
                color='tab:red', linewidth=2, linestyle='--', label='ρ geotermalna voda')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='upper right', bbox_to_anchor=(0.95, 0.95))
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)

        fig.tight_layout()
        fig.savefig('time_vs_co2_density_vs_geothermal_density.png', dpi=600)
        plt.show()
        
        
    def time_vs_geothermal_co2_bhp_whp_comparison(self, vfp_gt_df, vfp_co2_df):
        """
        Usporedba tlakova na dnu i na ušću geotermalne i CO₂ bušotine kroz vrijeme.
        Geotermalni BHP/WHP (lijeva os), CO₂ BHP/WHP (desna os).
        """
        fig, ax1 = plt.subplots(figsize=(10, 6))
        
        # Plot geothermal data
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('tlak [bar]', color='black')  # Changed to black for single axis
        
        # Geothermal production BHP
        ax1.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['prod BHP [bar]'], 
                color='tab:blue', linewidth=2, linestyle='-', label='GT BHP proizvodnja')
        
        # Geothermal injection BHP
        ax1.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['inj BHP [bar]'], 
                color='tab:green', linewidth=2, linestyle='-', label='GT BHP utiskivanje')
        
        # Geothermal production WHP
        ax1.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['prod WHP [bar]'], 
                color='tab:blue', linewidth=2, linestyle='--',
                label='GT WHP proizvodnja')
        
        # Geothermal injection WHP
        ax1.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['inj WHP [bar]'], 
                color='tab:green', linewidth=2, linestyle='--', 
                label='GT WHP utiskivanje')
        
        # CO2 BHP
        ax1.plot(vfp_co2_df['Time [yr]'], vfp_co2_df['BHP [bar]'], 
                color='tab:red', linewidth=2, linestyle='-',
                label='CO₂ BHP utiskivanje')
        
        # CO2 WHP
        ax1.plot(vfp_co2_df['Time [yr]'], vfp_co2_df['CO2 WHP [bar]'], 
                color='tab:red', linewidth=2, linestyle='--',
                label='CO₂ WHP utiskivanje')
        
        # Configure grid
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        
        # Customize axis lines - make all visible and colored
        ax1.spines['bottom'].set_color('black')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['bottom'].set_visible(True)
        
        ax1.spines['left'].set_color('black')
        ax1.spines['left'].set_linewidth(1.0)
        ax1.spines['left'].set_visible(True)
        
        ax1.spines['right'].set_color('black')
        ax1.spines['right'].set_linewidth(1.0)
        ax1.spines['right'].set_visible(True)
        
        ax1.spines['top'].set_color('black')
        ax1.spines['top'].set_linewidth(1.0)
        ax1.spines['top'].set_visible(True)
        
        ax1.grid(True, linestyle=':', linewidth=0.5)
        
        # Place legend outside the plot area
        ax1.legend(loc='center left', bbox_to_anchor=(1.05, 0.5), 
                  frameon=True, fancybox=True, shadow=True)
        
        # Adjust layout to make space for the legend
        fig.tight_layout()
        fig.subplots_adjust(right=0.8)  # Make more space for legend
        
        fig.savefig('time_vs_geothermal_co2_bhp_whp_comparison.png', dpi=600, 
                    bbox_inches='tight')
        plt.show()


    def thermal_front_progression(self, doublet_results):
        """
        Prikazuje napredovanje termičke fronte kroz rezervoar:
        temperatura proizvodnje (lijeva os) i radijus fronte (desna os).
        """
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('proizvodna temperatura [°C]', color='tab:blue')
        ax1.plot(doublet_results['time, years'], doublet_results['temperature, °C'], 
                color='tab:blue', linewidth=2, label='T proizvodnja')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5)
        ax1.legend(loc='lower left', bbox_to_anchor=(0.05, 0.05))
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('radijus termičke fronte [m]', color='tab:red')
        ax2.plot(doublet_results['time, years'], doublet_results['front radius, m'], 
                color='tab:red', linewidth=2, linestyle='--', label='r termičke fronte')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='upper right', bbox_to_anchor=(0.95, 0.95))
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)

        fig.tight_layout()
        fig.savefig('thermal_front_progression.png', dpi=600)
        plt.show()

    def co2_vs_geothermal_energy_balance(self, mbal_df, vfp_co2_df, vfp_gt_df):
        """
        Energetska bilanca: snaga potrebna za CO₂ kompresiju vs. neto geotermalna snaga.
        """
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('CO₂ kompresija [kW]', color='tab:blue')
        ax1.plot(vfp_co2_df['Time [yr]'], vfp_co2_df['CO2 comp. P [kW]'], 
                color='tab:blue', linewidth=2, label='snaga CO₂ kompresije')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5)
        ax1.legend(loc='upper left', bbox_to_anchor=(0.05, 0.95))
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('neto geotermalna snaga [kW]', color='tab:red')
        ax2.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['net power GT, kW'], 
                color='tab:red', linewidth=2, linestyle='--', label='neto GT snaga')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='upper right', bbox_to_anchor=(0.95, 0.95))
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)

        fig.tight_layout()
        fig.savefig('co2_vs_geothermal_energy_balance.png', dpi=600)
        plt.show()

    def volumetric_flow_comparison(self, mbal_df):
        """
        Usporedba volumetrijskog protoka geotermalne vode kroz vrijeme
        s količinom uskladištenog CO₂.
        """
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('protok geotermalne vode [rm³/dan]', color='tab:blue')
        ax1.plot(mbal_df['Time, yr'], mbal_df['q geothermal [rm3/d]'], 
                color='tab:blue', linewidth=2, label='q geotermalna')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5)
        ax1.legend(loc='upper left', bbox_to_anchor=(0.05, 0.95))
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('uskladišteni CO₂ [Mt]', color='tab:red')
        ax2.plot(mbal_df['Time, yr'], mbal_df['m_CO2, Mt'], 
                color='tab:red', linewidth=2, linestyle='--', marker='o', 
                markersize=3, label='CO₂ uskladišten')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='upper right', bbox_to_anchor=(0.95, 0.95))
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)

        fig.tight_layout()
        fig.savefig('volumetric_flow_comparison.png', dpi=600)
        plt.show()

    def pressure_efficiency_correlation(self, vfp_co2_df, vfp_gt_df):
        """
        Korelacija između tlakova CO₂ sustava i učinkovitosti geotermalne proizvodnje.
        """
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('CO₂ BHP [bar]')
        ax1.set_ylabel('snaga CO₂ kompresije [kW]', color='tab:blue')
        ax1.scatter(vfp_co2_df['BHP [bar]'], vfp_co2_df['CO2 comp. P [kW]'], 
                   color='tab:blue', s=30, alpha=0.7, label='kompresijska snaga')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5)
        ax1.legend(loc='upper left', bbox_to_anchor=(0.05, 0.95))
        
        # Add axis lines
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)

        ax2 = ax1.twinx()
        ax2.set_ylabel('neto GT snaga [kW]', color='tab:red')
        ax2.scatter(vfp_co2_df['BHP [bar]'], vfp_gt_df['net power GT, kW'], 
                   color='tab:red', s=30, alpha=0.7, marker='s', label='neto GT snaga')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='upper right', bbox_to_anchor=(0.95, 0.95))
        
        # Add right axis line
        ax2.spines['right'].set_color('tab:red')
        ax2.spines['right'].set_linewidth(1.0)

        fig.tight_layout()
        fig.savefig('pressure_efficiency_correlation.png', dpi=600)
        plt.show()

    def comprehensive_system_overview(self, mbal_df, vfp_co2_df, vfp_gt_df):
        """
        Sveobuhvatan prikaz ključnih parametara sustava kroz vrijeme:
        4 subplot-a za različite aspekte GT-CCS sustava.
        """
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        # Subplot 1: CO₂ storage and pressure
        ax1.set_xlabel('vrijeme [god]')
        ax1.set_ylabel('uskladišteni CO₂ [Mt]', color='tab:blue')
        line1 = ax1.plot(mbal_df['Time, yr'], mbal_df['m_CO2, Mt'], 
                        color='tab:blue', linewidth=2, label='CO₂ uskladišten')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.grid(True, linestyle=':', linewidth=0.5)
        
        # Add axis lines for subplot 1
        ax1.spines['bottom'].set_color('black')
        ax1.spines['left'].set_color('tab:blue')
        ax1.spines['bottom'].set_linewidth(1.0)
        ax1.spines['left'].set_linewidth(1.0)
        
        ax1_twin = ax1.twinx()
        ax1_twin.set_ylabel('DSA tlak [bar]', color='tab:red')
        line2 = ax1_twin.plot(mbal_df['Time, yr'], mbal_df['DSA pressure, bar'], 
                             color='tab:red', linewidth=2, linestyle='--', label='DSA tlak')
        ax1_twin.tick_params(axis='y', labelcolor='tab:red')
        ax1_twin.spines['right'].set_color('tab:red')
        ax1_twin.spines['right'].set_linewidth(1.0)
        
        # Combined legend
        lines1 = line1 + line2
        labels1 = [l.get_label() for l in lines1]
        ax1.legend(lines1, labels1, loc='upper left')
        ax1.set_title('CO₂ uskladištenje i tlak')

        # Subplot 2: Geothermal production
        ax2.set_xlabel('vrijeme [god]')
        ax2.set_ylabel('protok [kg/s]', color='tab:green')
        line3 = ax2.plot(mbal_df['Time, yr'], mbal_df['m_dot geothermal [kg/s]'], 
                        color='tab:green', linewidth=2, label='m_dot GT')
        ax2.tick_params(axis='y', labelcolor='tab:green')
        ax2.grid(True, linestyle=':', linewidth=0.5)
        
        # Add axis lines for subplot 2
        ax2.spines['bottom'].set_color('black')
        ax2.spines['left'].set_color('tab:green')
        ax2.spines['bottom'].set_linewidth(1.0)
        ax2.spines['left'].set_linewidth(1.0)
        
        ax2_twin = ax2.twinx()
        ax2_twin.set_ylabel('temperatura [°C]', color='tab:orange')
        line4 = ax2_twin.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['prod t, °C'], 
                             color='tab:orange', linewidth=2, linestyle='--', label='T proizvodnja')
        ax2_twin.tick_params(axis='y', labelcolor='tab:orange')
        ax2_twin.spines['right'].set_color('tab:orange')
        ax2_twin.spines['right'].set_linewidth(1.0)
        
        lines2 = line3 + line4
        labels2 = [l.get_label() for l in lines2]
        ax2.legend(lines2, labels2, loc='upper right')
        ax2.set_title('Geotermalna proizvodnja')

        # Subplot 3: Power comparison
        ax3.set_xlabel('vrijeme [god]')
        ax3.set_ylabel('snaga [kW]')
        ax3.plot(vfp_co2_df['Time [yr]'], vfp_co2_df['CO2 comp. P [kW]'], 
                color='tab:red', linewidth=2, label='CO₂ kompresija')
        ax3.plot(vfp_gt_df['Time [yr]'], vfp_gt_df['net power GT, kW'], 
                color='tab:green', linewidth=2, label='neto GT snaga')
        ax3.tick_params(axis='y')
        ax3.grid(True, linestyle=':', linewidth=0.5)
        ax3.legend()
        ax3.set_title('Energetska bilanca')
        
        # Add axis lines for subplot 3
        ax3.spines['bottom'].set_color('black')
        ax3.spines['left'].set_color('black')
        ax3.spines['bottom'].set_linewidth(1.0)
        ax3.spines['left'].set_linewidth(1.0)

        # Subplot 4: System efficiency indicators  
        ax4.set_xlabel('vrijeme [god]')
        ax4.set_ylabel('efikasnost [-]', color='tab:purple')
        
        # Calculate energy efficiency ratio
        energy_ratio = vfp_gt_df['net power GT, kW'] / vfp_co2_df['CO2 comp. P [kW]']
        line5 = ax4.plot(vfp_gt_df['Time [yr]'], energy_ratio, 
                        color='tab:purple', linewidth=2, label='GT/CO₂ omjer snage')
        ax4.tick_params(axis='y', labelcolor='tab:purple')
        ax4.grid(True, linestyle=':', linewidth=0.5)
        
        # Add axis lines for subplot 4
        ax4.spines['bottom'].set_color('black')
        ax4.spines['left'].set_color('tab:purple')
        ax4.spines['bottom'].set_linewidth(1.0)
        ax4.spines['left'].set_linewidth(1.0)
        
        ax4_twin = ax4.twinx()
        ax4_twin.set_ylabel('S_eff CO₂ [-]', color='tab:brown')
        line6 = ax4_twin.plot(vfp_co2_df['Time [yr]'], vfp_co2_df['S_eff'], 
                             color='tab:brown', linewidth=2, linestyle=':', label='S_eff CO₂')
        ax4_twin.tick_params(axis='y', labelcolor='tab:brown')
        ax4_twin.spines['right'].set_color('tab:brown')
        ax4_twin.spines['right'].set_linewidth(1.0)
        
        lines4 = line5 + line6
        labels4 = [l.get_label() for l in lines4]
        ax4.legend(lines4, labels4, loc='upper left')
        ax4.set_title('Pokazatelji učinkovitosti sustava')

        fig.tight_layout()
        fig.savefig('comprehensive_system_overview.png', dpi=600)
        plt.show()