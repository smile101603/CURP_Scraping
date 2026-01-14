"""
State Codes Mapping
Maps Mexican state names to their official codes used in CURP forms.
"""
# Mapping of state names to their codes
STATE_NAME_TO_CODE = {
    "Aguascalientes": "AS",
    "Baja California": "BC",
    "Baja California Sur": "BS",
    "Campeche": "CC",
    "Chiapas": "CS",
    "Chihuahua": "CH",
    "Coahuila": "CL",
    "Colima": "CM",
    "Durango": "DG",
    "Guanajuato": "GT",
    "Guerrero": "GR",
    "Hidalgo": "HG",
    "Jalisco": "JC",
    "Michoacán": "MN",
    "Morelos": "MS",
    "Nayarit": "NT",
    "Nuevo León": "NL",
    "Oaxaca": "OC",
    "Puebla": "PL",
    "Querétaro": "QT",
    "Quintana Roo": "QR",
    "San Luis Potosí": "SP",
    "Sinaloa": "SL",
    "Sonora": "SR",
    "Tabasco": "TC",
    "Tamaulipas": "TS",
    "Tlaxcala": "TL",
    "Veracruz": "VZ",
    "Yucatán": "YN",
    "Zacatecas": "ZS",
    "Ciudad de México": "DF",
    "Nacido en el extranjero": "NE"
}

# Reverse mapping: code to name
STATE_CODE_TO_NAME = {v: k for k, v in STATE_NAME_TO_CODE.items()}


def get_state_code(state_name: str) -> str:
    """Get state code from state name."""
    return STATE_NAME_TO_CODE.get(state_name, "AS")


def get_state_name(state_code: str) -> str:
    """Get state name from state code."""
    return STATE_CODE_TO_NAME.get(state_code, "Aguascalientes")

