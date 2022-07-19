IGC -> KML converter
==========

Simple command line tool to convert .IGC files from a flight logger (e.g. a paragliding vario) to .KML files, so your track can be viewed on Google Earth.

Usage
----

```igc2kml file1.igc```

Use ```igc2kml --help``` to see all available options. 

Launch site detection
-----

The parser will automatically detect the nearest known paragliding launch-site and use it for the filename and the KML description.
To extend this list, simply open the file with a text editor and add your site to the list at the top. 

