"""Constants for the Belkin Wemo component."""

from enum import IntEnum

DOMAIN = "wemo"

SERVICE_SET_HUMIDITY = "set_humidity"
SERVICE_RESET_FILTER_LIFE = "reset_filter_life"
SERVICE_SET_CROCKPOT_COOK_TIME = "set_crockpot_cook_time"

WEMO_SUBSCRIPTION_EVENT = f"{DOMAIN}_subscription_event"

ATTR_TARGET_HUMIDITY = "target_humidity"

class CrockPotMode(IntEnum):
    """CrockPot Mode Enum."""

    Off = 0
    Warm = 50
    Low = 51
    High = 52


CROCKPOT_MODE_MAP = {
    CrockPotMode.Off: "Turned Off",
    CrockPotMode.Warm: "Warm",
    CrockPotMode.Low: "Low",
    CrockPotMode.High: "High",
}
