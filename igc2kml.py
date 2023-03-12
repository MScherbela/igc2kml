#!/usr/bin/python3
import datetime
import dataclasses
from typing import List, Optional
import argparse
import math
import os.path

EARTH_RADIUS = 6371e3 # radius of the earth in meters
# Add launch-sites in format (latitude, longitude) in decimal notation
LAUNCH_SITES = {"Sonnwendstein": (47.622361, 15.8575),
                'Hohe Wand': (47.829167, 16.041111),
                'Invermere': (50.521301, -116.005644),
                'York Soaring': (43.838098, -80.440351)}


@dataclasses.dataclass
class FlightData:
    t: List[datetime.datetime]
    lat: List[float]
    lon: List[float]
    alt: List[float]
    vario: Optional[List[float]] = None
    x: Optional[List[float]] = None
    y: Optional[List[float]] = None
    speed: Optional[List[float]] = None

    @property
    def n_samples(self):
        return len(self.t)

class Units:
    x: str
    y: str
    alt: str
    xfactor: Optional[float] = None
    yfactor: Optional[float] = None
    altfactor: Optional[float] = None

def get_distance(lat1, lon1, lat2, lon2):
    a = math.sin(lat1 * math.pi / 180) * math.sin(lat2 * math.pi / 180)
    b = math.cos(lat1 * math.pi / 180) * math.cos(lat2 * math.pi / 180) * math.cos((lon2 - lon1) * math.pi / 180)
    return math.acos(a+b) * EARTH_RADIUS

def _parse_H_record(line):
    tokens = line.split(':')
    return tokens[0], ':'.join(tokens[1:])

def _parse_B_record(line, date):
    MILLIMINUTES_IN_DEG =  1e-3 / 60
    t = date + datetime.timedelta(hours=int(line[1:3]), minutes=int(line[3:5]), seconds=int(line[5:7]))
    lat = float(line[7:9]) + float(line[9:14]) * MILLIMINUTES_IN_DEG
    if line[14] == 'S':
        lat *= -1
    lon = float(line[15:18]) + float(line[18:23]) * MILLIMINUTES_IN_DEG
    if line[23] == 'W':
        lon *= -1
    is_3D_fix = line[24] == 'A'
    alt_baro = float(line[25:30])
    alt_gps = float(line[30:35])
    return t, lat, lon, is_3D_fix, alt_baro, alt_gps

def parse_igc(fname):
    meta_data = dict()
    data = []
    with open(fname) as f:
        for line in f:
            if len(line) == 0:
                continue
            if line[0] == 'B':
                data.append(_parse_B_record(line, date))
            elif line.startswith('HFDTE'):
                date = datetime.datetime.strptime(line[5:11], "%d%m%y")
                meta_data['date'] = date
            elif line.startswith('HFTZNTIMEZONE'):
                date += datetime.timedelta(hours=float(line[14:]))
            elif line[0] == 'H':
                key, value = _parse_H_record(line)
                meta_data[key] = value
            elif line[0] == 'A':
                meta_data['serial_nr'] = line.split(':')[-1]

    t, lat, lon, _, _, alt_gps = zip(*data)
    return FlightData(t=t, lat=lat, lon=lon, alt=alt_gps), meta_data

def _write_kml_timeseries(f, data, color_data, color_map_name, cmin, cmax, n_colors, units, name="", postfix=""):
    f.write("<Folder>\n")
    f.write(f"<name>{name}</name>")
    for i in range(data.n_samples - 1):
        f.write('<Placemark>\n')
        ind_color = int(n_colors * (color_data[i] - cmin) / (cmax - cmin) + 0.5)
        if ind_color >= n_colors:
            ind_color = n_colors - 1
        elif ind_color < 0:
            ind_color = 0
        f.write(f'\t<styleUrl>#{color_map_name}{ind_color}</styleUrl>\n')
        f.write(f'\t<name>{data.t[i].hour}:{data.t[i].minute}:{data.t[i].second}, {data.alt[i]*units.altfactor:.0f}{units.alt}, {color_data[i]:.0f}{postfix}</name>')
        f.write('\t<LineString>\n')
        f.write('\t<altitudeMode>absolute</altitudeMode>\n')
        f.write('\t<coordinates>\n')
        f.write(f'  {data.lon[i]:.6f},{data.lat[i]:.6f},{data.alt[i]:.0f}\n')
        f.write(f'  {data.lon[i + 1]:.6f},{data.lat[i + 1]:.6f},{data.alt[i + 1]:.0f}\n')
        f.write('\t</coordinates>\n')
        f.write('\t</LineString>\n')
        f.write('</Placemark>\n')
    f.write("</Folder>\n")

def _write_kml_path(f, data):
    """Adds an extruded 'curtain' between the flight-path and the ground to easier visualize altitude above ground."""
    f.write('<Placemark>\n')
    f.write(f'\t<styleUrl>polyline</styleUrl>\n')
    f.write(f'\t<name>Flight Path</name>')
    f.write('\t<LineString>\n')
    f.write('\t<altitudeMode>absolute</altitudeMode>\n')
    f.write('\t<extrude>1</extrude>\n')
    f.write('\t<tesselate>1</tesselate>\n')
    f.write('\t<coordinates>\n')
    for i in range(data.n_samples - 1):
        f.write(f'  {data.lon[i]:.6f},{data.lat[i]:.6f},{data.alt[i]:.0f}\n')
    f.write('\t</coordinates>\n')
    f.write('\t</LineString>\n')
    f.write('</Placemark>\n')


def _write_kml_colormap(f, name, values):
    for i, c in enumerate(values):
        f.write(f'<Style id="{name}{i}">\n')
        f.write('\t<LineStyle>\n')
        f.write(f'\t<color>{c}</color>\n')
        f.write('\t<width>3</width>\n')
        f.write('\t</LineStyle>\n')
        f.write('</Style>\n')
    f.write('<Style id="polyline">\n')
    f.write('<LineStyle>\n')
    f.write('<color>00ff0000</color>\n')
    f.write('<width>1</width>\n')
    f.write('</LineStyle>\n')
    f.write('<PolyStyle>\n')
    f.write('<color>7fffffff</color>\n')
    f.write('</PolyStyle>\n')
    f.write('</Style>\n')


def write_kml(fname, data: FlightData, metadata: dict):
    color_maps = dict(rdgn9=["ff2600a5", "ff2e40de", "ff528ef9", "ff81d4fe", "ffbefffe", "ff82e9cb", "ff66ca84", "ff54a02a", "ff376800"])
    with open(fname, 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<kml xmlns="http://earth.google.com/kml/2.0">\n')
        f.write('<Document>\n')
        f.write("<open>1</open>\n")
        for color_map_name, color_map_values in color_maps.items():
            _write_kml_colormap(f, color_map_name, color_map_values)
        date = metadata.get('date')
        pilot = metadata.get('pilot')
        launch_site = metadata.get('launch_site', "Unknown")
        name = launch_site
        if pilot:
            name += " - " + pilot
        if date:
            name += f": {date:%d.%m.%Y}"
        f.write(f'<name>{name}</name>\n')
        f.write("<Folder>\n")
        f.write("<name>Flight track</name>\n")
        f.write("<open>1</open>\n")
        f.write("<Style><ListStyle><listItemType>radioFolder</listItemType></ListStyle></Style>\n")
        _write_kml_timeseries(f, data, data.vario, 'rdgn9', -4, 4, 9, meta_data['units'], f"Vario [{meta_data['units'].y}]", meta_data['units'].y)
        _write_kml_timeseries(f, data, data.speed, 'rdgn9', 0, 60, 9, meta_data['units'], f"Speed [{meta_data['units'].x}]", meta_data['units'].x)
        f.write("</Folder>")
        _write_kml_path(f, data)
        f.write('</Document>\n')
        f.write('</kml>\n')


def get_nearest_launch_site_name(lat, lon):
    best_name = "Unknown"
    best_distance = 10e3
    for name, (lat_site, lon_site) in LAUNCH_SITES.items():
        d = get_distance(lat, lon, lat_site, lon_site)
        if d < best_distance:
            best_distance = d
            best_name = name
    return best_name


def process_data(data, meta_data, units):
    data.x = [EARTH_RADIUS * math.cos(lat * math.pi / 180) * math.cos(lon * math.pi / 180) for lat, lon in
              zip(data.lat, data.lon)]
    data.y = [EARTH_RADIUS * math.cos(lat * math.pi / 180) * math.sin(lon * math.pi / 180) for lat, lon in
              zip(data.lat, data.lon)]
    timedelta = [(data.t[i+1] - data.t[i]).seconds for i in range(data.n_samples -1)] + [1.0]
    distance_delta = [math.sqrt((data.x[i + 1] - data.x[i]) ** 2 + (data.y[i + 1] - data.y[i]) ** 2) for i in
                      range(data.n_samples - 1)] + [0.0]
    vario_delta = [data.alt[i + 1] - data.alt[i] for i in range(data.n_samples - 1)] + [0.0]
    units.xfactor = get_conversion_factor(units.x)
    units.yfactor = get_conversion_factor(units.y)
    units.altfactor = get_conversion_factor(units.alt)
    # Some recording devices take multiple fixes per minute, but only record timestamps accurate to the minute.
    # Adding one millisecond avoids division by zero exceptions, but fubars the speed calculations.
    # A better method would be to calculate the frequency of fixes in these cases. This is an ugly hack.
    data.speed = [units.xfactor * dx / (dt+0.001) for dx, dt in zip(distance_delta, timedelta)]
    data.vario = [units.yfactor * dy / (dt+0.001) for dy, dt in zip(vario_delta, timedelta)]
    site_name = get_nearest_launch_site_name(data.lat[0], data.lon[0])
    meta_data['launch_site'] = site_name
    meta_data['units'] = units
    return data, meta_data

def get_conversion_factor(unit):
    """Gets a conversion factor from metres per second (or simple metres) to whatever your heart desires"""
    # I bet there's a conversion library that would be better for this
    if unit in ["kts", "knots"]:
        return 1.9438444924406
    elif unit in ["mph", "miles/h"]:
        return 2.2369362920544
    elif unit in ["kmh", "km/h"]:
        return 3.6
    elif unit in ["fpm", "f/m"]:
        return 196.85039370078738
    elif unit in ["feet"]:
        return 3.280839895013123
    elif unit in ["m/s", "mps", "m", "metres", "meters"]:
        return 1.0
    else:
        raise ValueError(f"Unknown unit for speed: {unit}")

if __name__ == '__main__':
    units = Units()
    parser = argparse.ArgumentParser(description="IGC to KML converter for flight logs, so they can be viewed with Google Earth.")
    parser.add_argument("input", nargs="+", help="Input file name(s)")
    parser.add_argument("--output", help="Output file name", default=None)
    parser.add_argument("--force", "-f", help="Overwrite output file if it exists", action="store_true")
    parser.add_argument("--pilot", "-p", help="Pilot's name (will appear on flight path name)", type=str)
    parser.add_argument("--xunits", "-x", help="Ground speed units (default kmh)", type=str, choices=["m/s", "kmh", "mph", "kts", "knots", "miles/h"], default="kmh")
    parser.add_argument("--yunits", "-y", help="Vertical speed units (default mps)", type=str, choices=["m/s", "kmh", "mph", "kts", "fpm", "f/m"], default="m/s")
    parser.add_argument("--altunits", "-a", help="Altitude units (default m)", type=str, choices=["m", "feet", "metres", "metres"], default="m")
    args = parser.parse_args()
    units.x = args.xunits
    units.y = args.yunits
    units.alt = args.altunits

    for input_fname in args.input:
        data, meta_data = parse_igc(input_fname)
        data, meta_data = process_data(data, meta_data, units)  # "units" becomes part of the "meta_data" dict here
        meta_data["pilot"] = args.pilot
        output_name = args.output or f"{data.t[0]:%Y_%m_%d_%H%M}_{meta_data['launch_site']}.kml"
        if os.path.isfile(output_name) and not args.force:
            print(f"Can not save kml file, because it already exists: {output_name}")
        else:
            write_kml(output_name, data, meta_data)





