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
      "a": "Mars",
      "b": "Saturn",
      "type": "conjunction",
      "orb": 1.19
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
      "a": "Neptune",
      "b": "Pluto",
      "type": "sextile",
      "orb": 5.21
    }
  ]
};
