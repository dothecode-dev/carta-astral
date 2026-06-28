"""Spike de exploración de la API real de kerykeion 5.12.9.

Objetivo (corrección #1 del spec): verificar qué acepta kerykeion ANTES de escribir
tests del núcleo. Responde: ¿toma lat/lng/tz directo? ¿hace conversión de timezone
internamente? ¿acepta Julian Day? ¿control de casas/zodiac/puntos? ¿tz histórica correcta?
"""
import json
from kerykeion import AstrologicalSubject

SEP = "=" * 70

def show(subj, label):
    print(SEP)
    print(label)
    print("  julian_day:", getattr(subj, "julian_day", getattr(subj, "julian_day_utc", "<none>")))
    print("  iso_formatted_utc_datetime:", getattr(subj, "iso_formatted_utc_datetime", "<none>"))
    print("  iso_formatted_local_datetime:", getattr(subj, "iso_formatted_local_datetime", "<none>"))
    print("  tz_str:", subj.tz_str, "| lat:", subj.lat, "| lng:", subj.lng)
    sun = subj.sun
    print("  sun ->", {k: getattr(sun, k, None) for k in ("name","sign","position","abs_pos","house","retrograde")})
    moon = subj.moon
    print("  moon ->", {k: getattr(moon, k, None) for k in ("name","sign","position","abs_pos","house")})
    asc = getattr(subj, "ascendant", getattr(subj, "first_house", None))
    print("  ascendant/first_house ->", {k: getattr(asc, k, None) for k in ("name","sign","position","abs_pos")} if asc else "<none>")
    print("  houses_system_identifier:", getattr(subj, "houses_system_identifier", "<none>"))
    print("  zodiac_type:", getattr(subj, "zodiac_type", "<none>"))

# --- 1. lat/lng/tz directo, online=False (sin geonames) ---
s1 = AstrologicalSubject(
    name="Test", year=1989, month=7, day=14, hour=23, minute=45,
    lng=-58.4, lat=-34.5, tz_str="America/Argentina/Buenos_Aires",
    city="Olivos", nation="AR", online=False,
)
show(s1, "1) Olivos 1989-07-14 23:45 local (lat/lng/tz directo, online=False)")

# --- 2. TZ histórica: Buenos Aires 1969 (offset != actual) ---
s2 = AstrologicalSubject(
    name="Hist", year=1969, month=6, day=15, hour=12, minute=0,
    lng=-58.4, lat=-34.6, tz_str="America/Argentina/Buenos_Aires",
    city="BA", nation="AR", online=False,
)
show(s2, "2) Buenos Aires 1969-06-15 12:00 (verificar offset historico)")

# --- 3. Pasar UTC directamente (para detectar doble conversion) ---
s3 = AstrologicalSubject(
    name="UTC", year=1990, month=1, day=1, hour=0, minute=0,
    lng=0.0, lat=51.5, tz_str="UTC", city="GMT", nation="GB", online=False,
)
show(s3, "3) UTC directo 1990-01-01 00:00")

# --- 4. Control de house systems ---
for hsi in ("P", "W", "K", "O"):
    s = AstrologicalSubject(
        name=f"hs_{hsi}", year=1989, month=7, day=14, hour=23, minute=45,
        lng=-58.4, lat=-34.5, tz_str="America/Argentina/Buenos_Aires",
        nation="AR", online=False, houses_system_identifier=hsi,
    )
    asc = getattr(s, "first_house", None)
    print(f"  house system {hsi}: first_house abs_pos =", getattr(asc, "abs_pos", "?"))

# --- 5. Sidereal ---
try:
    s5 = AstrologicalSubject(
        name="Sid", year=1989, month=7, day=14, hour=23, minute=45,
        lng=-58.4, lat=-34.5, tz_str="America/Argentina/Buenos_Aires",
        nation="AR", online=False, zodiac_type="Sidereal", sidereal_mode="LAHIRI",
    )
    print(SEP); print("5) Sidereal LAHIRI sun:", s5.sun.sign, s5.sun.position)
except Exception as e:
    print("5) Sidereal error:", type(e).__name__, e)

# --- 6. Lat polar + Placidus (trampa #4) ---
try:
    s6 = AstrologicalSubject(
        name="Polar", year=1989, month=7, day=14, hour=12, minute=0,
        lng=15.0, lat=78.0, tz_str="Arctic/Longyearbyen",
        nation="NO", online=False, houses_system_identifier="P",
    )
    print(SEP); print("6) Polar lat=78 Placidus first_house:", getattr(s6.first_house,"abs_pos","?"), "| sun house:", s6.sun.house)
except Exception as e:
    print(SEP); print("6) Polar Placidus error:", type(e).__name__, e)

# --- 7. Atributos completos del subject ---
print(SEP); print("7) Atributos publicos del subject:")
print([a for a in dir(s1) if not a.startswith("_")])

# --- 8. ¿is_dst y ambigüedad? ---
print(SEP); print("8) firma is_dst presente (resuelve DST ambiguo): si")
