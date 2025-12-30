# QNEAT

The QNEAT Processing plugin (short for Qgis Network Analysis Toolbox 3) aims to provide sophisticated QGIS Processing algorithms in the field of network, graph and accessibility analysis. In order to provide usability and consitency in the QGIS software design, the QNEAT-Plugin is not designed as a simple GUI extension but as an QGIS Processing provider for the Processing toolbox. Therefore all QNEAT algorithms can be integrated into complex analytical workflows via the Processing Modeler as well as processing python scripts. Further information will be provided at the corresponding [ResearchGate](https://doi.org/10.13140/RG.2.2.13042.02248) project-website.

## Currently implemented algorithms

- **Shortest Path** (Dijkstra) between two points (pairs of coordinates obtained by using QGIS-GUI)
- **Origin-Destination Matrices** Matrix between all points of a layer.
- **ISO-Area Algorithms** Algorithms for isochrone area calculation (pointcloud, interpolation-based raster, contours and polygon)
