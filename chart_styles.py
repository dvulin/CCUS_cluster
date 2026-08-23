"""Central chart styling shared by Streamlit and Matplotlib outputs.

Change ``CHART_FONT_SIZE_OFFSET`` to increase or decrease every chart font
while preserving the intentional size differences between labels, titles,
ticks, legends and annotations.
"""

from __future__ import annotations


# One global control for every diagram font.  The requested migration adds
# three to all previously configured sizes.
CHART_FONT_SIZE_OFFSET = 3


def chart_font_size(
    base_size: int | float,
    additional_offset: int | float = 0,
) -> int | float:
    """Return a chart font size adjusted by the global offset."""
    return base_size + CHART_FONT_SIZE_OFFSET + additional_offset


def vega_lite_chart_config(additional_font_size_offset: int | float = 0) -> dict:
    """Return the shared high-contrast Vega-Lite chart configuration."""
    return {
        "axis": {
            "labelColor": "#000000",
            "labelFontSize": chart_font_size(15, additional_font_size_offset),
            "labelFontWeight": 500,
            "titleColor": "#000000",
            "titleFontSize": chart_font_size(17, additional_font_size_offset),
            "titleFontWeight": 600,
            "domain": True,
            "domainColor": "#000000",
            "domainWidth": 1.5,
            "ticks": True,
            "tickColor": "#000000",
            "tickSize": 7,
            "tickWidth": 1.5,
            "gridColor": "#D9D9D9",
            "gridOpacity": 0.7,
        },
        "legend": {
            "labelColor": "#000000",
            "labelFontSize": chart_font_size(15, additional_font_size_offset),
            "titleColor": "#000000",
            "titleFontSize": chart_font_size(16, additional_font_size_offset),
            "orient": "bottom",
            "direction": "horizontal",
        },
        "title": {
            "color": "#000000",
            "fontSize": chart_font_size(17, additional_font_size_offset),
        },
    }


def uncertainty_matplotlib_rc_params() -> dict:
    """Return publication-style defaults for uncertainty figures."""
    return {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": chart_font_size(10),
        "axes.titlesize": chart_font_size(12.5),
        "axes.labelsize": chart_font_size(12),
        "axes.linewidth": 0.8,
        "xtick.labelsize": chart_font_size(10),
        "ytick.labelsize": chart_font_size(10),
        "legend.fontsize": chart_font_size(8),
        "legend.title_fontsize": chart_font_size(10),
        "figure.titlesize": chart_font_size(12),
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
    }


def uncertainty_annotation_font_size() -> int | float:
    """Return the shared size for uncertainty-figure annotations."""
    return chart_font_size(7)


LEGACY_MATPLOTLIB_STYLE_NAME = "ggplot"


def legacy_matplotlib_rc_params() -> dict:
    """Return defaults for the legacy ``outputs.visualization`` figures."""
    return {
        "figure.facecolor": "white",
        "font.family": "serif",
        "font.size": chart_font_size(12),
        "text.color": "black",
        "axes.labelcolor": "black",
        "axes.titlesize": chart_font_size(12),
        "axes.labelsize": chart_font_size(12),
        "xtick.labelsize": chart_font_size(10),
        "xtick.color": "black",
        "ytick.labelsize": chart_font_size(10),
        "ytick.color": "black",
        "legend.fontsize": chart_font_size(10),
        "legend.title_fontsize": chart_font_size(10),
        "figure.titlesize": chart_font_size(12),
        "axes.facecolor": "white",
        "grid.color": "lightgray",
        "grid.linewidth": 0.5,
        "axes.spines.left": True,
        "axes.spines.bottom": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 1.0,
    }


def legacy_geothermal_font_sizes() -> dict[str, int | float]:
    """Return sizes used by the specialized legacy geothermal figure."""
    return {
        "title": chart_font_size(16),
        "labels": chart_font_size(14),
        "ticks": chart_font_size(12),
        "legend": chart_font_size(10),
    }
