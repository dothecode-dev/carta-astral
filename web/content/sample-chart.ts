// Carta de ejemplo de la web. Datos calculados con el motor del backend, no
// escritos a mano: son las posiciones reales para esa fecha, hora y lugar.
//
// Para regenerarlos, desde backend/ con el venv activo:
//
//   python -c "
//   import datetime, json
//   from core.models import BirthInput
//   from core.ephemeris import build_chart
//   bi = BirthInput(name='Camila', date=datetime.date(1994,3,12),
//                   time=datetime.time(7,20), time_known=True,
//                   lat=-34.6118, lng=-58.3960,
//                   house_system='Placidus', zodiac='Tropical')
//   ...
//   "
//
// Camila es un ejemplo: los datos de nacimiento son inventados, el cálculo no.

export type SamplePlanet = { name: string; lon: number; house: string; retro: boolean };
export type SampleAspect = { a: string; b: string; type: string; orb: number };

export type SampleChart = {
  planets: SamplePlanet[];
  houses: number[];
  angles: { Ascendant: number; Medium_Coeli: number; Descendant: number; Imum_Coeli: number };
  aspects: SampleAspect[];
};

export const SAMPLE_BIRTH = {
  name: "Camila",
  date: "1994-03-12",
  time: "07:20",
  place: "Buenos Aires, Argentina",
  coords: "34\u00b036\u2032S 58\u00b023\u2032O",
  system: "Placidus \u00b7 Tropical",
} as const;

export const SAMPLE_CHART: SampleChart = {
  "planets": [
    {
      "name": "Sun",
      "lon": 351.6125,
      "house": "Twelfth_House",
      "retro": false
    },
    {
      "name": "Moon",
      "lon": 353.125,
      "house": "Twelfth_House",
      "retro": false
    },
    {
      "name": "Mercury",
      "lon": 325.0602,
      "house": "Eleventh_House",
      "retro": false
    },
    {
      "name": "Venus",
      "lon": 4.7634,
      "house": "First_House",
      "retro": false
    },
    {
      "name": "Mars",
      "lon": 333.9103,
      "house": "Twelfth_House",
      "retro": false
    },
    {
      "name": "Jupiter",
      "lon": 224.4359,
      "house": "Eighth_House",
      "retro": true
    },
    {
      "name": "Saturn",
      "lon": 335.0989,
      "house": "Twelfth_House",
      "retro": false
    },
    {
      "name": "Uranus",
      "lon": 295.344,
      "house": "Tenth_House",
      "retro": false
    },
    {
      "name": "Neptune",
      "lon": 292.8261,
      "house": "Tenth_House",
      "retro": false
    },
    {
      "name": "Pluto",
      "lon": 238.038,
      "house": "Ninth_House",
      "retro": true
    },
    {
      "name": "Chiron",
      "lon": 154.9479,
      "house": "Sixth_House",
      "retro": true
    },
    {
      "name": "True_North_Lunar_Node",
      "lon": 235.8838,
      "house": "Ninth_House",
      "retro": true
    },
    {
      "name": "Mean_Lilith",
      "lon": 27.1636,
      "house": "Second_House",
      "retro": false
    },
    {
      "name": "True_South_Lunar_Node",
      "lon": 55.8838,
      "house": "Third_House",
      "retro": true
    }
  ],
  "houses": [
    357.0153,
    23.9026,
    54.2709,
    86.7349,
    119.227,
    149.7514,
    177.0153,
    203.9026,
    234.2709,
    266.7349,
    299.227,
    329.7514
  ],
  "angles": {
    "Ascendant": 357.0153,
    "Medium_Coeli": 266.7349,
    "Descendant": 177.0153,
    "Imum_Coeli": 86.7349
  },
  "aspects": [
    {
      "a": "Sun",
      "b": "Moon",
      "type": "conjunction",
      "orb": 1.51
    },
    {
      "a": "Sun",
      "b": "Jupiter",
      "type": "trine",
      "orb": 7.18
    },
    {
      "a": "Sun",
      "b": "Uranus",
      "type": "sextile",
      "orb": 3.73
    },
    {
      "a": "Sun",
      "b": "Neptune",
      "type": "sextile",
      "orb": 1.21
    },
    {
      "a": "Sun",
      "b": "Pluto",
      "type": "trine",
      "orb": 6.43
    },
    {
      "a": "Sun",
      "b": "True_North_Lunar_Node",
      "type": "trine",
      "orb": 4.27
    },
    {
      "a": "Sun",
      "b": "Ascendant",
      "type": "conjunction",
      "orb": 5.4
    },
    {
      "a": "Sun",
      "b": "Descendant",
      "type": "opposition",
      "orb": 5.4
    },
    {
      "a": "Sun",
      "b": "True_South_Lunar_Node",
      "type": "sextile",
      "orb": 4.27
    },
    {
      "a": "Moon",
      "b": "Uranus",
      "type": "sextile",
      "orb": 2.22
    },
    {
      "a": "Moon",
      "b": "Neptune",
      "type": "sextile",
      "orb": 0.3
    },
    {
      "a": "Moon",
      "b": "Pluto",
      "type": "trine",
      "orb": 4.91
    },
    {
      "a": "Moon",
      "b": "True_North_Lunar_Node",
      "type": "trine",
      "orb": 2.76
    },
    {
      "a": "Moon",
      "b": "Ascendant",
      "type": "conjunction",
      "orb": 3.89
    },
    {
      "a": "Moon",
      "b": "Medium_Coeli",
      "type": "square",
      "orb": 3.61
    },
    {
      "a": "Moon",
      "b": "Descendant",
      "type": "opposition",
      "orb": 3.89
    },
    {
      "a": "Moon",
      "b": "Imum_Coeli",
      "type": "square",
      "orb": 3.61
    },
    {
      "a": "Moon",
      "b": "True_South_Lunar_Node",
      "type": "sextile",
      "orb": 2.76
    },
    {
      "a": "Mercury",
      "b": "Mars",
      "type": "conjunction",
      "orb": 8.85
    },
    {
      "a": "Mercury",
      "b": "Pluto",
      "type": "square",
      "orb": 2.98
    },
    {
      "a": "Mercury",
      "b": "True_North_Lunar_Node",
      "type": "square",
      "orb": 0.82
    },
    {
      "a": "Mercury",
      "b": "Chiron",
      "type": "opposition",
      "orb": 9.89
    },
    {
      "a": "Mercury",
      "b": "Medium_Coeli",
      "type": "sextile",
      "orb": 1.67
    },
    {
      "a": "Mercury",
      "b": "Imum_Coeli",
      "type": "trine",
      "orb": 1.67
    },
    {
      "a": "Mercury",
      "b": "Mean_Lilith",
      "type": "sextile",
      "orb": 2.1
    },
    {
      "a": "Mercury",
      "b": "True_South_Lunar_Node",
      "type": "square",
      "orb": 0.82
    },
    {
      "a": "Venus",
      "b": "Neptune",
      "type": "quintile",
      "orb": 0.06
    },
    {
      "a": "Venus",
      "b": "Pluto",
      "type": "trine",
      "orb": 6.73
    },
    {
      "a": "Venus",
      "b": "Ascendant",
      "type": "conjunction",
      "orb": 7.75
    },
    {
      "a": "Venus",
      "b": "Descendant",
      "type": "opposition",
      "orb": 7.75
    },
    {
      "a": "Mars",
      "b": "Saturn",
      "type": "conjunction",
      "orb": 1.19
    },
    {
      "a": "Mars",
      "b": "Chiron",
      "type": "opposition",
      "orb": 1.04
    },
    {
      "a": "Mars",
      "b": "Imum_Coeli",
      "type": "trine",
      "orb": 7.18
    },
    {
      "a": "Saturn",
      "b": "Chiron",
      "type": "opposition",
      "orb": 0.15
    },
    {
      "a": "Uranus",
      "b": "Neptune",
      "type": "conjunction",
      "orb": 2.52
    },
    {
      "a": "Uranus",
      "b": "Pluto",
      "type": "sextile",
      "orb": 2.69
    },
    {
      "a": "Uranus",
      "b": "True_North_Lunar_Node",
      "type": "sextile",
      "orb": 0.54
    },
    {
      "a": "Uranus",
      "b": "Ascendant",
      "type": "sextile",
      "orb": 1.67
    },
    {
      "a": "Uranus",
      "b": "Descendant",
      "type": "trine",
      "orb": 1.67
    },
    {
      "a": "Uranus",
      "b": "Mean_Lilith",
      "type": "square",
      "orb": 1.82
    },
    {
      "a": "Uranus",
      "b": "True_South_Lunar_Node",
      "type": "trine",
      "orb": 0.54
    },
    {
      "a": "Neptune",
      "b": "Pluto",
      "type": "sextile",
      "orb": 5.21
    },
    {
      "a": "Neptune",
      "b": "True_North_Lunar_Node",
      "type": "sextile",
      "orb": 3.06
    },
    {
      "a": "Neptune",
      "b": "Ascendant",
      "type": "sextile",
      "orb": 4.19
    },
    {
      "a": "Neptune",
      "b": "Descendant",
      "type": "trine",
      "orb": 4.19
    },
    {
      "a": "Neptune",
      "b": "Mean_Lilith",
      "type": "square",
      "orb": 4.34
    },
    {
      "a": "Neptune",
      "b": "True_South_Lunar_Node",
      "type": "trine",
      "orb": 3.06
    },
    {
      "a": "Pluto",
      "b": "True_North_Lunar_Node",
      "type": "conjunction",
      "orb": 2.15
    },
    {
      "a": "Pluto",
      "b": "Ascendant",
      "type": "trine",
      "orb": 1.02
    },
    {
      "a": "Pluto",
      "b": "Descendant",
      "type": "sextile",
      "orb": 1.02
    },
    {
      "a": "Pluto",
      "b": "True_South_Lunar_Node",
      "type": "opposition",
      "orb": 2.15
    },
    {
      "a": "True_North_Lunar_Node",
      "b": "Ascendant",
      "type": "trine",
      "orb": 1.13
    },
    {
      "a": "True_North_Lunar_Node",
      "b": "Descendant",
      "type": "sextile",
      "orb": 1.13
    },
    {
      "a": "Chiron",
      "b": "Mean_Lilith",
      "type": "trine",
      "orb": 7.78
    },
    {
      "a": "Ascendant",
      "b": "Medium_Coeli",
      "type": "square",
      "orb": 0.28
    },
    {
      "a": "Ascendant",
      "b": "Imum_Coeli",
      "type": "square",
      "orb": 0.28
    },
    {
      "a": "Ascendant",
      "b": "True_South_Lunar_Node",
      "type": "sextile",
      "orb": 1.13
    },
    {
      "a": "Medium_Coeli",
      "b": "Descendant",
      "type": "square",
      "orb": 0.28
    },
    {
      "a": "Medium_Coeli",
      "b": "Mean_Lilith",
      "type": "trine",
      "orb": 0.43
    },
    {
      "a": "Descendant",
      "b": "Imum_Coeli",
      "type": "square",
      "orb": 0.28
    },
    {
      "a": "Descendant",
      "b": "True_South_Lunar_Node",
      "type": "trine",
      "orb": 1.13
    },
    {
      "a": "Imum_Coeli",
      "b": "Mean_Lilith",
      "type": "sextile",
      "orb": 0.43
    }
  ]
};
