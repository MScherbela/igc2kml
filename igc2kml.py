#!/usr/bin/python3
#%%
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

    @property
    def t_seconds(self):
        return [(t - self.t[0]).seconds for t in self.t]
    
    @property
    def duration_sec(self):
        return (self.t[-1] - self.t[0]).seconds

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

def _write_kml_timeseries(f, data, color_data, color_map_name, cmin, cmax, n_colors, name="", postfix=""):
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
        f.write(f'\t<name>{data.t[i].hour}:{data.t[i].minute}:{data.t[i].second}, {data.alt[i]:.0f}m, {data.speed[i]:.0f}{postfix}</name>\n')
        f.write('\t<TimeStamp>\n')
        f.write(f'\t\t<when>{data.t[i].astimezone(datetime.timezone.utc).isoformat()}</when>\n')
        f.write('\t</TimeStamp>\n')
        f.write('\t<LineString>\n')
        f.write('\t<altitudeMode>absolute</altitudeMode>\n')
        f.write('\t<coordinates>\n')
        f.write(f'\t\t{data.lon[i]:.6f},{data.lat[i]:.6f},{data.alt[i]:.0f}\n')
        f.write(f'\t\t{data.lon[i + 1]:.6f},{data.lat[i + 1]:.6f},{data.alt[i + 1]:.0f}\n')
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
    color_maps = dict(rdgn9=["ff2600a5", "ff2e40de", "ff528ef9", "ff81d4fe", "ffbefffe", "ff82e9cb", "ff66ca84", "ff54a02a", "ff376800"],
                      jet50=["#FF7F0000", "#FF960000", "#FFAC0000", "#FFC30000", "#FFDA0000", "#FFF50000", "#FFFF0000", "#FFFF1000", "#FFFF2400", "#FFFF3C00", "#FFFF5000", "#FFFF6400", "#FFFF7800", "#FFFF8C00", "#FFFFA400", "#FFFFB800", "#FFFFCC00", "#FFFAE000", "#FFE7F80F", "#FFD7FF1F", "#FFC7FF2F", "#FFB7FF3F", "#FFA6FF4F", "#FF93FF63", "#FF83FF73", "#FF73FF83", "#FF63FF93", "#FF4FFFA6", "#FF3FFFB7", "#FF2FFFC7", "#FF1FFFD7", "#FF0FFFE7", "#FF00F0FA", "#FF00DEFF", "#FF00CBFF", "#FF00B9FF", "#FF00A3FF", "#FF0090FF", "#FF007EFF", "#FF006BFF", "#FF0059FF", "#FF0042FF", "#FF0030FF", "#FF001DFF", "#FF000BF5", "#FF0000DA", "#FF0000C3", "#FF0000AC", "#FF000096", "#FF00007F"]
)
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
        _write_kml_timeseries(f, data, data.vario, 'rdgn9', -4, 4, 9, "Vario [m/s]", "m/s")
        _write_kml_timeseries(f, data, data.speed, 'rdgn9', 0, 60, 9, f"Speed [{meta_data['speed_unit']}]", meta_data['speed_unit'])
        _write_kml_timeseries(f, data, data.t_seconds, 'jet50', 0, data.duration_sec, 50, "Time [s]", "s")
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


def process_data(data, meta_data, speed_unit):
    data.x = [EARTH_RADIUS * math.cos(lat * math.pi / 180) * math.cos(lon * math.pi / 180) for lat, lon in
              zip(data.lat, data.lon)]
    data.y = [EARTH_RADIUS * math.cos(lat * math.pi / 180) * math.sin(lon * math.pi / 180) for lat, lon in
              zip(data.lat, data.lon)]
    data.vario = [data.alt[i + 1] - data.alt[i] for i in range(data.n_samples - 1)] + [0]
    timedelta = [(data.t[i+1] - data.t[i]).seconds for i in range(data.n_samples -1)] + [1.0]
    distance_delta = [math.sqrt((data.x[i + 1] - data.x[i]) ** 2 + (data.y[i + 1] - data.y[i]) ** 2) for i in
                      range(data.n_samples - 1)] + [0.0]
    speed_conversion_factor = get_speed_conversion_factor(speed_unit)
    data.speed = [speed_conversion_factor * dx / dt for dx, dt in zip(distance_delta, timedelta)]
    site_name = get_nearest_launch_site_name(data.lat[0], data.lon[0])
    meta_data['launch_site'] = site_name
    meta_data['speed_unit'] = speed_unit
    return data, meta_data

def get_speed_conversion_factor(unit):
    if unit in ["kts", "knots"]:
        return 1.9438444924406
    elif unit in ["mph", "miles/h"]:
        return 2.2369362920544
    elif unit in ["kmh", "km/h"]:
        return 3.6
    elif unit in ["m/s", "mps"]:
        return 1.0
    else:
        raise ValueError(f"Unknown unit for speed: {unit}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="IGC to KML converter for flight logs, so they can be viewed with Google Earth.")
    parser.add_argument("input", nargs="+", help="Input file name(s)")
    parser.add_argument("--output", help="Output file name", default=None)
    parser.add_argument("--force", "-f", help="Overwrite output file if it exists", action="store_true")
    parser.add_argument("--pilot", "-p", help="Pilot's name (will appear on flight path name)", type=str)
    parser.add_argument("--units", "-u", help="Ground speed units, kts or kmh (default kmh)", type=str, choices=["m/s", "kmh", "mph", "kts"], default="kmh")
    args = parser.parse_args()

    for input_fname in args.input:
        data, meta_data = parse_igc(input_fname)
        data, meta_data = process_data(data, meta_data, speed_unit=args.units)
        meta_data["pilot"] = args.pilot
        output_name = args.output or f"{data.t[0]:%Y_%m_%d_%H%M}_{meta_data['launch_site']}.kml"
        if os.path.isfile(output_name) and not args.force:
            print(f"Can not save kml file, because it already exists: {output_name}")
        else:
            write_kml(output_name, data, meta_data)





