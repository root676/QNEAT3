# -*- coding: utf-8 -*-
"""
***************************************************************************
    QneatFramework.py
    ---------------------
    
    Date                 : December 2025
    Copyright            : (C) 2025 by Clemens Raffler
    Email                : clemens dot raffler at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

import numpy
from scipy.ndimage import distance_transform_edt
from osgeo import gdal, ogr, osr

import math
from enum import IntEnum

from qgis.analysis import (
    QgsGraphAnalyzer,
    QgsGraphBuilder, 
    QgsGridFileWriter,
    QgsInterpolator, 
    QgsNetworkDistanceStrategy, 
    QgsNetworkSpeedStrategy, 
    QgsTinInterpolator, 
    QgsVectorLayerDirector
    )

from qgis.core import (
    Qgis,
    QgsDistanceArea, 
    QgsFeature, 
    QgsField, 
    QgsFields,
    QgsGeometry,  
    QgsPoint, 
    QgsPointXY, 
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,   
    QgsWkbTypes
    )

from qgis.PyQt.QtCore import QVariant

from .QneatUtilities import buildQgsVectorLayer, getCellIndexFromPoint

from typing import (
    Optional,
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsProcessingFeedback,
        QgsProcessingFeatureSource
        )
    
    from qgis.analysis import (
        QgsGraph
    )
class OptimizationStrategy(IntEnum):
    DISTANCE = 0
    TIME = 1

class EntryCostCalculationMethod(IntEnum):
    PLANAR = 0
    ELLIPSOID = 1

class IsoAreaMethod(IntEnum):
    EUCLIDEAN_DISTANCE = 0
    TIN_INTERPOLATION = 1

class IsoAreaType(IntEnum):
    POLYGONS = 0
    CONTOURS = 1

class MatrixType(IntEnum):
    TABLE = 0
    LINE = 1
    ROUTE = 2

class ProgressProxyFeedback (QgsProcessingFeedback):

    def __init__(self, parent_feedback: QgsProcessingFeedback, start: float, span: float):
        super().__init__()
        self._parent_feedback = parent_feedback
        self._start = start
        self._span = span
    
    def setProgress(self, progress: float):
        # progress comes in as 0 to 1
        global_progress = self._start + progress * self._span
        self._parent_feedback.setProgress(global_progress)
        
    def isCanceled(self) -> bool:
        return self._parent_feedback.isCanceled()


class ProgressRange:
    def __init__(self, feedback: ProgressProxyFeedback, start, span):
        self.fb = ProgressProxyFeedback(feedback, start, span)

    def feedback(self) -> ProgressProxyFeedback:
        return self.fb
    

class QneatAnalysisPoint():
    
    def __init__(self, feature: QgsFeature, graph_vertex_id: int, graph_vertex_geom: QgsPointXY, graph_entry_cost: float):
        self.feature: QgsFeature = feature
        self.graph_vertex_id: int = graph_vertex_id
        self.graph_vertex_geom: QgsPointXY = graph_vertex_geom
        self.graph_entry_cost: float = graph_entry_cost
        self.graph_entry_geom: QgsGeometry = QgsGeometry().fromPolylineXY([self.feature.geometry().asPoint(), self.graph_vertex_geom])
    
    def __str__(self):
        return "QneatAnalysisPoint: feature_id: {:30} referencing graph_vertex_id: {:d}".format(self.feature.id(), self.graph_vertex_id) 
       
    
class QneatCore():
    """
    QneatCore:
    Provides basic logic for more advanced network analysis algorithms
    """

    def __init__(self, 
                 graph_source: QgsProcessingFeatureSource,
                 point_featurelist: list[QgsFeature],
                 optimization_strategy: OptimizationStrategy,
                 speed_field: str,
                 default_speed: float,
                 tolerance: float,
                 entry_cost_calculation_method: EntryCostCalculationMethod,
                 buildProgressRange: ProgressRange,
                 directionFieldName: Optional[str] = None, 
                 forwardValue: Optional[str] = None,
                 backwardValue: Optional[str] = None, 
                 bothValue: Optional[str] = None,
                 defaultDirection: Optional[int] = None
                 ): 

        self.feedback = buildProgressRange.feedback()
        self.analysis_crs = graph_source.sourceCrs()

        #read points as QgsPointXY
        xy_points = list()
        for f in point_featurelist:
            if f.geometry() and f.geometry().isEmpty() is False:
                xy_points.append(f.geometry().asPoint())
            else:
                raise QgsProcessingException(f"Dataset has wrong geometry type. Got {QgsWkbTypes.displayString(f.geometry.wkbType())} dataset but expected Point dataset instead.")

        defaultDirectionEnum = QgsVectorLayerDirector.Direction(defaultDirection)

        #init direction fields
        director = QgsVectorLayerDirector(graph_source,
                                    graph_source.fields().lookupField(directionFieldName),
                                    forwardValue,
                                    backwardValue,
                                    bothValue,
                                    defaultDirectionEnum
                                    )
    
        #Setup cost-strategy pattern.
        self.default_speed = default_speed
        speed_field_id = graph_source.fields().lookupField(speed_field)
        self.setNetworkStrategy(optimization_strategy, speed_field_id, self.default_speed)

        #add the strategy to the QgsGraphDirector
        director.addStrategy(self.strategy)
        builder = QgsGraphBuilder(self.analysis_crs, True, tolerance)
        
        #tell the graph-director to make the graph using the builder object and tie the start point geometries to the graph
        self.feedback.pushInfo("building graph...")
        tiedPoints: list[QgsPointXY] = director.makeGraph(builder, xy_points, buildProgressRange.feedback())
        self.qgsgraph: QgsGraph = builder.graph()

        self.analysis_points: list[QneatAnalysisPoint] = list()

        if entry_cost_calculation_method == EntryCostCalculationMethod.ELLIPSOID: 
            dist_calculator = QgsDistanceArea()
            dist_calculator.setSourceCrs(self.analysis_crs, QgsProject().instance().transformContext())
            dist_calculator.setEllipsoid(self.analysis_crs.ellipsoidAcronym())

        #build snapping info for analysis_points
        for i, tied_point in enumerate(tiedPoints):
            graph_vertex_id: int = self.qgsgraph.findVertex(tied_point)
            input_point: QgsPointXY = xy_points[i]
            if entry_cost_calculation_method == EntryCostCalculationMethod.ELLIPSOID: 
                dist = dist_calculator.measureLine(input_point, tied_point)
            else: 
                dist = input_point.distance(tied_point)
            
            if optimization_strategy == OptimizationStrategy.DISTANCE: 
                entry_cost = dist
            else:
                entry_cost = dist/(self.default_speed*(1000.0 / 3600.0))

            self.analysis_points.append(QneatAnalysisPoint(point_featurelist[i], graph_vertex_id, tied_point, entry_cost))
            
          
    def setNetworkStrategy(self, optimization_strategy: OptimizationStrategy, speed_field_index: int, default_speed: float):
        if optimization_strategy == OptimizationStrategy.DISTANCE:
            self.strategy = QgsNetworkDistanceStrategy()
        else:
            self.strategy = QgsNetworkSpeedStrategy(speed_field_index, float(default_speed), 1000.0 / 3600.0)


    def calcDijkstra(self, source_vertex_id: int) -> tuple[list[int], list[float]]:
        tree, cost = QgsGraphAnalyzer.dijkstra(self.qgsgraph, source_vertex_id, 0)
        return tree, cost
        
    
    def queryOdPair(self, tree: list[int], cost: list[float], origin_point: QneatAnalysisPoint, origin_point_id_field: str, destination_point: QneatAnalysisPoint, destination_point_id_field: str, matrix_type: MatrixType) -> QgsFeature:
        origin_id = origin_point.feature[origin_point_id_field]
        origin_id_field_type = origin_point.feature.fields().field(origin_point_id_field).type()

        destination_id = destination_point.feature[destination_point_id_field]
        destination_id_field_type = destination_point.feature.fields().field(destination_point_id_field).type()

        feat: QgsFeature = QgsFeature()
        fields: QgsFields  = QgsFields()
        fields.append(QgsField('origin_id', origin_id_field_type, '', 254, 0))
        fields.append(QgsField('destination_id', destination_id_field_type, '', 254, 0))
        fields.append(QgsField('entry_cost', QVariant.Double, '', 20,7))
        fields.append(QgsField('network_cost', QVariant.Double, '', 20, 7))
        fields.append(QgsField('exit_cost', QVariant.Double, '', 20,7))
        fields.append(QgsField('total_cost', QVariant.Double, '', 20,7))
        feat.setFields(fields)

        if origin_id == destination_id:
            feat['origin_id'] = origin_id
            feat['destination_id'] = destination_id
            feat['entry_cost '] = 0.0
            feat['entry_cost'] = 0.0
            feat['network_cost'] = 0.0
            feat['exit_cost'] = 0.0
            feat['total_cost'] = 0.0
        elif tree[destination_point.graph_vertex_id] == -1:
            feat['origin_id'] = origin_id
            feat['destination_id'] = destination_id
            feat['entry_cost'] = None
            feat['network_cost'] = None
            feat['exit_cost'] = None
            feat['total_cost'] = None
        else:
            network_cost = cost[destination_point.graph_vertex_id]
            feat['origin_id'] = origin_id
            feat['destination_id'] = destination_id
            feat['entry_cost'] = origin_point.graph_entry_cost
            feat['network_cost'] = network_cost
            feat['exit_cost'] = destination_point.graph_entry_cost
            feat['total_cost'] = origin_point.graph_entry_cost + network_cost + destination_point.graph_entry_cost

        #set geometry
        if matrix_type == MatrixType.TABLE:
            feat.setGeometry(QgsGeometry())
        elif matrix_type == MatrixType.LINE:
            feat.setGeometry(QgsGeometry().fromPolylineXY([origin_point.feature.geometry().asPoint(), destination_point.feature.geometry().asPoint()]))
        elif matrix_type == MatrixType.ROUTE:
            route_points: list[QgsPointXY] = list()
            route_points.append(origin_point.feature.geometry().asPoint())
            route_points.append(origin_point.graph_vertex_geom)

            current_vertex_id = destination_point.graph_vertex_id
            while current_vertex_id != origin_point.graph_vertex_id:
                current_vertex_idx = self.qgsgraph.edge(tree[current_vertex_idx]).fromVertex()
                route_points.append(self.qgsgraph.vertex(current_vertex_idx).point())
            
            route_points.append(destination_point.graph_vertex_geom)
            route_points.append(destination_point.feature.geometry().asPoint())
            
            route_geom: QgsGeometry = QgsGeometry().fromPolylineXY(route_points)
            feat.setGeometry(route_geom)

        return feat
    
        
    def calcIsoPoints(self, max_cost: float, progress_range: ProgressRange, id_field_datatype: QVariant = QVariant.LongLong) -> list[QgsFeature]:
        iso_points = dict()

        output_fields = QgsFields()
        output_fields.append(QgsField('vertex_id', QVariant.LongLong))
        output_fields.append(QgsField('cost', QVariant.Double))
        output_fields.append(QgsField('origin_point_id', id_field_datatype))

        total_workload: int = len(self.analysis_points)

        for i, origin_point in enumerate(self.analysis_points):
            entry_cost = origin_point.graph_entry_cost

            if entry_cost <= max_cost:
                self.feedback.pushInfo(f"Processing origin point {i}")
                tree, cost = self.calcDijkstra(origin_point.graph_vertex_id)

                feat = QgsFeature(output_fields)
                feat['vertex_id'] = origin_point.graph_vertex_id
                feat['cost'] = entry_cost
                feat['origin_point_id'] = origin_point.feature["user_id"]
                pt_m = QgsPoint(self.qgsgraph.vertex(origin_point.graph_vertex_id).point())
                pt_m.addMValue(entry_cost)
                geom = QgsGeometry(pt_m)
                feat.setGeometry(geom)
                
                iso_points[origin_point.graph_vertex_id] = feat

                for v in range(len(cost)):
                    if tree[v] == -1:
                        continue

                    real_cost = cost[v] + entry_cost
                    if real_cost > max_cost:
                        continue

                    existing = iso_points.get(v)
                    if existing is not None and existing['cost'] <= real_cost:
                        continue

                    feat = QgsFeature(output_fields)
                    feat['vertex_id'] = v
                    feat['cost'] = real_cost
                    feat['origin_point_id'] = origin_point.feature['user_id']
                    pt_m = QgsPoint(self.qgsgraph.vertex(v).point()) 
                    pt_m.addMValue(real_cost)
                    feat.setGeometry(QgsGeometry(pt_m))

                    iso_points[v] = feat
            else:
                self.feedback.pushInfo(f"WARNING: Skipping origin point with ID {origin_point.feature['user_id']} as it is outside of maximum iso-area bounds of {max_cost}.")

            progress_range.feedback().setProgress((i+1)/total_workload)

        return list(iso_points.values())
        
        
    def calcIsoTinInterpolation(self, iso_points: list[QgsFeature], cellsize: float, output_interpolation_path : str, progress_range: ProgressRange, cost_field_name : str = 'cost' ) -> QgsRasterLayer:

        if cellsize <= 0:
            raise QgsProcessingException("Cell size for iso area interpolation must be > 0")
        
        #pack iso_point_features in a QgsFeatureSource in order to be usable for QgsInterpolator
        iso_point_layer: QgsVectorLayer = buildQgsVectorLayer(f'point?crs={self.analysis_crs.authid()}&field=vertex_id:integer&field={cost_field_name}:integer', "iso_points", self.analysis_crs, iso_points)
        iso_point_layer.updateExtents()

        if self.analysis_crs.isGeographic():
            raise QgsProcessingException('The QGIS TIN-Interpolation algorithm is designed to work with projected coordinate systems.Please use a projected coordinate system (eg. UTM zones) instead of geographic coordinate systems (eg. WGS84)!')
        
        cost_field_index = iso_point_layer.fields().indexFromName(cost_field_name)
        if cost_field_index < 0:
            raise QgsProcessingException(f"Field {cost_field_name} not found for interpolation.")

        layer_data = QgsInterpolator.LayerData()
        
        layer_data.source = iso_point_layer 
        layer_data.valueSource = QgsInterpolator.ValueSource.Attribute
        layer_data.interpolationAttribute =  1 #take second field to get costs
        layer_data.sourceType = QgsInterpolator.SourceType.Points

        tin_interpolator = QgsTinInterpolator([layer_data], QgsTinInterpolator.TinInterpolation.Linear, progress_range.feedback())
        
        extent : QgsRectangle = iso_point_layer.extent()
        ncol = max(1, math.ceil(extent.width() / cellsize))
        nrows = max(1, math.ceil(extent.width() / cellsize))
        
        writer = QgsGridFileWriter(tin_interpolator, output_interpolation_path, extent, ncol, nrows)
        result = writer.writeFile() 
        if result != 0:
            raise QgsProcessingException(f"Failed to write interpolation result file.")

        output_raster = QgsRasterLayer(output_interpolation_path, "temp_qneat_interpolation_raster")
        output_raster.setCrs(self.analysis_crs)

        return output_raster
    
    def calcEuclideanDistanceRaster(self, iso_points: list[QgsFeature], cellsize: float, output_path: str, progress_range: ProgressRange, cost_field_name : str = 'cost') -> QgsRasterLayer:
        
        iso_point_layer: QgsVectorLayer = buildQgsVectorLayer(
            f'point?crs={self.analysis_crs.authid()}'
            f'&field=vertex_id:integer'
            f'&field={cost_field_name}:integer',
            "iso_points",
            self.analysis_crs,
            iso_points
        )

        progress_range.feedback().setProgress(0.2)
        rasterExtent: QgsRectangle = iso_point_layer.sourceExtent().scaled(1.1)

        xmin = rasterExtent.xMinimum()
        ymin = rasterExtent.yMinimum()
        xmax = rasterExtent.xMaximum()
        ymax = rasterExtent.yMaximum()   # FIXED

        cols = int(math.ceil((xmax - xmin) / cellsize))
        rows = int(math.ceil((ymax - ymin) / cellsize))

        driver = gdal.GetDriverByName('GTiff')
        outputRaster = driver.Create(output_path, cols, rows, 1, gdal.GDT_Float32)

        geotransform = (xmin, cellsize, 0, ymax, 0, -cellsize)
        outputRaster.SetGeoTransform(geotransform)

        band = outputRaster.GetRasterBand(1)
        band.SetNoDataValue(-9999)

        seedMask = numpy.ones((rows, cols), dtype=bool)
        node_cost_raster = numpy.full((rows, cols), numpy.nan, dtype=numpy.float32)
        progress_range.feedback().setProgress(0.5)

        for node in iso_points:

            pt = node.geometry().asPoint()
            x, y = pt.x(), pt.y()

            row, col = getCellIndexFromPoint(x, y, rasterExtent, cellsize, rows, cols)

            if 0 <= row < rows and 0 <= col < cols:
                seedMask[row, col] = False
                node_cost_raster[row, col] = float(node[cost_field_name])

        eucDist, (inds_r, inds_c) = distance_transform_edt(
            seedMask,
            return_indices=True
        )
        progress_range.feedback().setProgress(0.8)

        cost_raster = node_cost_raster[inds_r, inds_c] + eucDist * cellsize

        cost_raster = numpy.where(
            numpy.isnan(cost_raster),
            -9999,
            cost_raster
        )

        band.WriteArray(cost_raster)

        outRasterSRS = osr.SpatialReference()
        outRasterSRS.ImportFromWkt(self.analysis_crs.toWkt())
        outputRaster.SetProjection(outRasterSRS.ExportToWkt())

        band.FlushCache()
        band = None
        outputRaster = None

        output_raster = QgsRasterLayer(output_path, "temp_qneat_euclidean_distance_raster")
        output_raster.setCrs(self.analysis_crs)
        progress_range.feedback().setProgress(0.8)

        return output_raster

    

    def calcIsoAreas(self, input_cost_raster_path: str, max_cost: float, interval: float, iso_area_type : IsoAreaType, progress_range: ProgressRange) -> QgsVectorLayer:

        interpolation_raster = gdal.Open(input_cost_raster_path)
        if interpolation_raster is None:
            raise QgsProcessingException("Could not open Interpolation result, please use another cellsize, iso area extent or obtain a valid interpolation raster with the QNEAT Iso-Area as Interpolation algorithm.")

        band = interpolation_raster.GetRasterBand(1)
        #band.CreateMaskBand(gdal.GMF_PER_DATASET)
        #band.DeleteNoDataValue()

        ogr_geom_type = ogr.wkbMultiLineString
        qgis_geom_type = Qgis.WkbType.MultiLineString
        contour_polygonize = False
        if iso_area_type == IsoAreaType.POLYGONS:
            ogr_geom_type = ogr.wkbMultiPolygon
            qgis_geom_type = Qgis.WkbType.MultiPolygon
            contour_polygonize = True
            

        ogr_driver = ogr.GetDriverByName("MEMORY")
        ogr_ds = ogr_driver.CreateDataSource("iso_areas")
        ogr_layer = ogr_ds.CreateLayer("iso_areas", geom_type=ogr_geom_type)

        #Fields
        field_list = list()
        id_field: ogr.FieldDefn = ogr.FieldDefn('id', ogr.OFTInteger)
        cost_level_field: ogr.FieldDefn = ogr.FieldDefn('cost_level', ogr.OFTReal)
        field_list.extend([id_field, cost_level_field])

        ogr_layer.CreateFields(field_list)
        
        srs: osr.SpatialReference = osr.SpatialReference()
        srs.ImportFromWkt( interpolation_raster.GetProjectionRef() )

        levels = [i * interval for i in range(int(max_cost / interval) + 1)]
        
        gdal.ContourGenerateEx(
            band,
            ogr_layer,
            options=[
                f"FIXED_LEVELS= {','.join(map(str, levels))}",
                f"NODATA={band.GetNoDataValue()}",
                "ID_FIELD=0",
                "ELEV_FIELD_MAX=1" if contour_polygonize else "ELEV_FIELD=1",
                "POLYGONIZE=" + 'yes' if contour_polygonize else 'no'
            ]
        )

        geom_string = "MultiLineString" if iso_area_type == IsoAreaType.CONTOURS else "MultiPolygon"
        iso_areas = QgsVectorLayer(f"{geom_string}?crs={self.analysis_crs.authid()}&field=id:integer&field=cost_level:double", "iso_areas", "memory")

        iso_area_fields = QgsFields()
        iso_area_fields.append(QgsField('id', QVariant.LongLong))
        iso_area_fields.append(QgsField('cost_level', QVariant.Double))
        provider = iso_areas.dataProvider()

        total_workload = ogr_layer.GetFeatureCount()

        iso_area_features = list()
        ogr_layer.ResetReading()
        for i, ogr_feat in enumerate(ogr_layer):
            qgs_feat = QgsFeature(iso_area_fields)

            ogr_geom = ogr_feat.GetGeometryRef()
            if ogr_geom:
                qgs_feat.setGeometry(QgsGeometry.fromWkt(ogr_geom.ExportToWkt()))

                qgs_feat.setAttribute("id", ogr_feat.GetField("id"))
                qgs_feat.setAttribute("cost_level", ogr_feat.GetField("cost_level"))

                iso_area_features.append(qgs_feat)
            else:
                continue



            progress = (i + 1) / total_workload
            progress_range.feedback().setProgress(progress)
            

        provider.addFeatures(iso_area_features)
        iso_areas.updateExtents()

        #handle gdal refcounting
        band = None
        interpolation_raster = None
        contours = None

        return iso_areas
        

                                                                                                                                                                                                                        
