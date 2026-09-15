"""Gas-value and environmental impact.

Nothing here is a hardcoded currency figure. Every number is derived from the
economic assumptions in config.py, and those assumptions travel with the result
so the UI can show what the money was built from.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from ..config import get_settings

HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365


@dataclass
class FinancialImpact:
    currency: str
    gas_value_lost_omr: float  # value of the gas released by THIS event
    loss_rate_omr_per_hour: float
    daily_loss_omr: float  # projection: if this recurred continuously
    annual_loss_omr: float  # projection
    recoverable_annual_omr: float  # captured by repairing the source
    gas_value_lost_usd: float
    assumptions: dict
    projection_note: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class EnvironmentalImpact:
    ch4_kg: float
    co2e_t_100yr: float
    co2e_t_20yr: float
    co2e_t_year_if_recurring_100yr: float
    equivalent_cars_year: float
    assumptions: dict

    def as_dict(self) -> dict:
        return asdict(self)


def gas_value_omr(mass_kg: float) -> float:
    s = get_settings()
    mmbtu = mass_kg * s.ch4_energy_mmbtu_per_kg
    return mmbtu * s.gas_price_omr_per_mmbtu


def financial_impact(
    total_mass_kg: float,
    duration_s: float,
    peak_rate_kg_h: float,
    recurrence_factor: float = 1.0,
) -> FinancialImpact:
    """`recurrence_factor` scales the projections: 1.0 means "assume this release
    repeats at the same duty cycle", which is what an intermittent source does."""
    s = get_settings()
    value_now = gas_value_omr(total_mass_kg)
    hours = max(duration_s / 3600.0, 1e-6)
    rate_omr_h = value_now / hours

    # An intermittent event is projected from its own duty cycle, not from the
    # peak rate held flat for a year — that would overstate the loss wildly.
    daily = rate_omr_h * HOURS_PER_DAY * recurrence_factor
    annual = daily * DAYS_PER_YEAR

    return FinancialImpact(
        currency=s.display_currency,
        gas_value_lost_omr=round(value_now, 3),
        loss_rate_omr_per_hour=round(rate_omr_h, 3),
        daily_loss_omr=round(daily, 2),
        annual_loss_omr=round(annual, 2),
        recoverable_annual_omr=round(annual, 2),
        gas_value_lost_usd=round(value_now * s.usd_per_omr, 3),
        assumptions={
            "gas_price": f"{s.gas_price_omr_per_mmbtu} {s.display_currency}/MMBtu",
            "methane_energy_content": f"{s.ch4_energy_mmbtu_per_kg} MMBtu/kg (LHV)",
            "fx_rate": f"1 {s.display_currency} = {s.usd_per_omr} USD",
            "recurrence_factor": recurrence_factor,
            "basis": "Saleable-gas value of methane released; excludes carbon pricing, "
                     "repair cost and production deferment",
        },
        projection_note="Daily and annual figures are PROJECTIONS assuming the release "
                        "recurs at the observed duty cycle. They are not measured losses.",
    )


def environmental_impact(
    total_mass_kg: float, duration_s: float, recurrence_factor: float = 1.0
) -> EnvironmentalImpact:
    s = get_settings()
    hours = max(duration_s / 3600.0, 1e-6)
    annual_kg = (total_mass_kg / hours) * HOURS_PER_DAY * DAYS_PER_YEAR * recurrence_factor

    co2e_100 = total_mass_kg * s.gwp100_ch4 / 1000.0
    co2e_20 = total_mass_kg * s.gwp20_ch4 / 1000.0
    annual_co2e_100 = annual_kg * s.gwp100_ch4 / 1000.0

    return EnvironmentalImpact(
        ch4_kg=round(total_mass_kg, 4),
        co2e_t_100yr=round(co2e_100, 4),
        co2e_t_20yr=round(co2e_20, 4),
        co2e_t_year_if_recurring_100yr=round(annual_co2e_100, 2),
        # 4.6 tCO2e/year is the widely used average passenger-car figure.
        equivalent_cars_year=round(annual_co2e_100 / 4.6, 1),
        assumptions={
            "gwp100": s.gwp100_ch4,
            "gwp20": s.gwp20_ch4,
            "gwp_source": "IPCC AR6, fossil methane, including climate-carbon feedbacks",
            "car_equivalence": "4.6 tCO2e per passenger vehicle per year",
            "recurrence_factor": recurrence_factor,
        },
    )
