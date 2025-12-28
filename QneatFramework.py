# -*- coding: utf-8 -*-
"""
***************************************************************************
    Qneat3Framework.py
    ---------------------
    
    Date                 : January 2018
    Copyright            : (C) 2018 by Clemens Raffler
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

import time
from osgeo import gdal, ogr, osr

from math import ceil
from enum import Enum

import numpy

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
    QgsFeatureRequest,
    QgsFeatureSink, 
    QgsField, 
    QgsFields,
    QgsGeometry,  
    QgsPoint, 
    QgsPointXY, 
    QgsProcessingException,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,   
    QgsSpatialIndex,
    QgsWkbTypes
    )

from qgis.PyQt.QtCore import QVariant, QMetaType

import QneatUtilities

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
        

class QneatCore():
    """
    QneatCore:
    Provides basic logic for more advanced network analysis algorithms
    """

    def __init__(self, 
                 graph_source: QgsProcessingFeatureSource,
                 point_featurelist: list[QgsFeature],
                 optimization_strategy: int,
                 speed_field: str,
                 default_speed: float,
                 tolerance: float,
                 entry_cost_calculation_method: int,
                 feedback: QgsProcessingFeedback,
                 directionFieldName: Optional[str] = None, 
                 forwardValue: Optional[str] = None,
                 backwardValue: Optional[str] = None, 
                 bothValue: Optional[str] = None,
                 defaultDirection: Optional[int] = None
                 ): 

        self.feedback = feedback
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
        
        self.setNetworkStrategy(optimization_strategy, graph_source, speed_field, self.default_speed)

        #add the strategy to the QgsGraphDirector
        director.addStrategy(self.strategy)
        builder = QgsGraphBuilder(self.analysis_crs, True, tolerance)
        
        #tell the graph-director to make the graph using the builder object and tie the start point geometries to the graph
        self.feedback.pushInfo("building graph...")
        tiedPoints: list[QgsPointXY] = self.director.makeGraph(builder, xy_points)
        self.qgsgraph: QgsGraph = builder.graph()

        self.analysis_points: list[QneatAnalysisPoint] = list()

        if entry_cost_calculation_method == 0: 
            dist_calculator = QgsDistanceArea()
            dist_calculator.setSourceCrs(self.analysis_crs, QgsProject().instance().transformContext())
            dist_calculator.setEllipsoid(self.analysis_crs.ellipsoidAcronym())

        #build snapping info for analysis_points
        for i, tied_point in enumerate(tiedPoints):
            graph_vertex_id: int = self.qgsgraph.findVertex(tied_point)
            input_point: QgsPointXY = xy_points[i]
            if entry_cost_calculation_method == 0: 
                dist = dist_calculator.measureLine(input_point, tied_point)
            else: 
                dist = input_point.distance(tied_point)
            
            if self.strategy == 0: 
                entry_cost = dist
            else:
                entry_cost = dist/(self.default_speed*(1000.0 / 3600.0))

            self.analysis_points.append(QneatAnalysisPoint(point_featurelist[i], graph_vertex_id, tied_point, entry_cost))
            
          
    def setNetworkStrategy(self, optimization_strategy, graph, speedField, default_speed):
        speedFieldId = graph.fields().lookupField(speedField)
        if optimization_strategy == 0:
            self.strategy = QgsNetworkDistanceStrategy()
        else:
            self.strategy = QgsNetworkSpeedStrategy(speedFieldId, float(default_speed), 1000.0 / 3600.0)

    def calcDijkstra(self, source_vertex_id: int) -> tuple[list[int], list[float]]:
        tree, cost = QgsGraphAnalyzer.dijkstra(self.network, source_vertex_id, 0)
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
        
    def calcIsoPoints(self, id_field_name: str, max_cost: float) -> list[QgsFeature]:
        iso_points = dict()

        output_fields = QgsFields()
        output_fields.append(QgsField('vertex_id', QVariant.Int))
        output_fields.append(QgsField('cost', QVariant.Double))
        output_fields.append(QgsField('origin_point_id',QneatUtilities.getFieldDatatype(id_field_name)))

        for i, origin_point in enumerate(self.analysis_points):
            entry_cost = origin_point.graph_entry_cost

            if entry_cost <= max_cost:
                self.feedback.pushInfo(f"Processing origin point {i}")
                tree, cost = self.calcDijkstra(origin_point.graph_vertex_id)

                feat = QgsFeature(output_fields)
                feat['vertex_id'] = origin_point.graph_vertex_id
                feat['cost'] = entry_cost
                feat['origin_point_id'] = origin_point.feature[id_field_name]
                pt_m = QgsPoint(self.network.vertex(origin_point.graph_vertex_id).point())
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
                    feat['origin_point_id'] = origin_point.feature[id_field_name]
                    pt_m = QgsPoint(self.qgsgraph.vertex(v).point()) 
                    pt_m.addMValue(real_cost)
                    feat.setGeometry(QgsGeometry(pt_m))

                    iso_points[v] = feat
            else:
                self.feedback.pushInfo(f"WARNING: Skipping origin point with ID {origin_point.feature[id_field_name]} as it is outside of maximum iso-area bounds of {max_cost}.")

        return list(iso_points.values())
    
    def calcQneatInterpolation(self,iso_pointcloud_featurelist, resolution, interpolation_raster_path):  
        #prepare spatial index
        uri = 'PointM?crs={}&field=vertex_id:int(254)&field=cost:double(254,7)&key=vertex_id&index=yes'.format(self.AnalysisCrs.authid())
        
        mIsoPointcloud = QgsVectorLayer(uri, "mIsoPointcloud_layer", "memory")
        mIsoPointcloud_provider = mIsoPointcloud.dataProvider()
        mIsoPointcloud_provider.addFeatures(iso_pointcloud_featurelist, QgsFeatureSink.FastInsert)
        
        #implement spatial index for lines (closest line, etc...)
        spt_idx = QgsSpatialIndex(mIsoPointcloud.getFeatures(QgsFeatureRequest()), self.feedback)
        
        #prepare numpy coordinate grids
        NoData_value = -9999
        raster_rectangle = mIsoPointcloud.extent()
        
        #top left point
        xmin = raster_rectangle.xMinimum()
        ymin = raster_rectangle.yMinimum()
        xmax = raster_rectangle.xMaximum()
        ymax = raster_rectangle.yMaximum()
        
        cols = int((xmax - xmin) / resolution)
        rows = int((ymax - ymin) / resolution)
        
        output_interpolation_raster = gdal.GetDriverByName('GTiff').Create(interpolation_raster_path, cols, rows, 1, gdal.GDT_Float64 )
        output_interpolation_raster.SetGeoTransform((xmin, resolution, 0, ymax, 0, -resolution))
        
        band = output_interpolation_raster.GetRasterBand(1)
        band.SetNoDataValue(NoData_value)
        
        #initialize zero array with 2 dimensions (according to rows and cols)
        raster_data = numpy.zeros(shape=(rows, cols))
        
        #compute raster cell MIDpoints
        x_pos = numpy.linspace(xmin+(resolution/2), xmax -(resolution/2), raster_data.shape[1])
        y_pos = numpy.linspace(ymax-(resolution/2), ymin + (resolution/2), raster_data.shape[0])
        x_grid, y_grid = numpy.meshgrid(x_pos, y_pos) 
        
        self.feedback.pushInfo('[QNEAT3Network][calcQneatInterpolation] Beginning with interpolation')
        total_work = rows * cols
        counter = 0
        
        self.feedback.pushInfo('[QNEAT3Network][calcQneatInterpolation] Total workload: {} cells'.format(total_work))
        self.feedback.setProgress(0)
        for i in range(rows):
            for j in range(cols):
                current_pixel_midpoint = QgsPointXY(x_grid[i,j],y_grid[i,j])
                
                nearest_vertex_fid = spt_idx.nearestNeighbor(current_pixel_midpoint, 1)[0]
                
                nearest_feature = mIsoPointcloud.getFeature(nearest_vertex_fid)
                
                nearest_vertex = self.network.vertex(nearest_feature['vertex_id'])
                
                edges = nearest_vertex.incomingEdges() + nearest_vertex.outgoingEdges()
                
                vertex_found = False
                nearest_counter = 2
                while vertex_found == False:
                    n_nearest_feature_fid = spt_idx.nearestNeighbor(current_pixel_midpoint, nearest_counter)[nearest_counter-1]
                    n_nearest_feature = mIsoPointcloud.getFeature(n_nearest_feature_fid)
                    n_nearest_vertex_id = n_nearest_feature['vertex_id']
                    
                    for edge_id in edges:
                        from_vertex_id = self.network.edge(edge_id).fromVertex()
                        to_vertex_id = self.network.edge(edge_id).toVertex()
                        
                        if n_nearest_vertex_id == from_vertex_id: 
                            vertex_found = True
                            vertex_type = "from_vertex"
                            from_point = n_nearest_feature.geometry().asPoint()
                            from_vertex_cost = n_nearest_feature['cost']
                        if n_nearest_vertex_id == to_vertex_id:
                            vertex_found = True
                            vertex_type = "to_vertex"
                            to_point = n_nearest_feature.geometry().asPoint()
                            to_vertex_cost = n_nearest_feature['cost']
                    
                    nearest_counter = nearest_counter + 1
                    """
                    if nearest_counter == 5:
                        vertex_found = True
                        vertex_type = "end_vertex"
                    """
                
                if vertex_type == "from_vertex":
                    nearest_edge_geometry = QgsGeometry().fromPolylineXY([from_point, nearest_vertex.point()])
                    res = nearest_edge_geometry.closestSegmentWithContext(current_pixel_midpoint)
                    segment_point = res[1] #[0: distance, 1: point, 2: left_of, 3: epsilon for snapping]
                    dist_to_segment = segment_point.distance(current_pixel_midpoint)
                    dist_edge = from_point.distance(segment_point)
                    #self.feedback.pushInfo("dist_to_segment = {}".format(dist_to_segment))
                    #self.feedback.pushInfo("dist_on_edge = {}".format(dist_edge))
                    #self.feedback.pushInfo("cost = {}".format(from_vertex_cost))
                    pixel_cost = from_vertex_cost + dist_edge + dist_to_segment
                    raster_data[i,j] = pixel_cost
                elif vertex_type == "to_vertex":
                    nearest_edge_geometry = QgsGeometry().fromPolylineXY([nearest_vertex.point(), to_point])
                    res = nearest_edge_geometry.closestSegmentWithContext(current_pixel_midpoint)
                    segment_point = res[1] #[0: distance, 1: point, 2: left_of, 3: epsilon for snapping]
                    dist_to_segment = segment_point.distance(current_pixel_midpoint)
                    dist_edge = to_point.distance(segment_point)
                    #self.feedback.pushInfo("dist_to_segment = {}".format(dist_to_segment))
                    #self.feedback.pushInfo("dist_on_edge = {}".format(dist_edge))
                    #self.feedback.pushInfo("cost = {}".format(from_vertex_cost))
                    pixel_cost = to_vertex_cost + dist_edge + dist_to_segment
                    raster_data[i,j] = pixel_cost
                else:
                    pixel_cost = -99999#nearest_feature['cost'] + (nearest_vertex.point().distance(current_pixel_midpoint))
                            
                    
                """
                nearest_feature_pointxy = nearest_feature.geometry().asPoint()
                nearest_feature_cost = nearest_feature['cost']
                
                dist_to_vertex = current_pixel_midpoint.distance(nearest_feature_pointxy)
                #implement time cost
                pixel_cost = dist_to_vertex + nearest_feature_cost
                
                raster_data[i,j] = pixel_cost
                """
                counter = counter+1
                if counter%1000 == 0:
                    self.feedback.pushInfo("[QNEAT3Network][calcQneatInterpolation] Interpolated {} cells...".format(counter))
                self.feedback.setProgress((counter/total_work)*100)
                
                
        band.WriteArray(raster_data)
        outRasterSRS = osr.SpatialReference()
        outRasterSRS.ImportFromWkt(self.AnalysisCrs.toWkt())
        output_interpolation_raster.SetProjection(outRasterSRS.ExportToWkt())
        band.FlushCache()

        
        
    def calcIsoTinInterpolation(self, iso_points: list[QgsFeature], cost_field_name : str, cellsize: float, output_interpolation_path : str) -> QgsRasterLayer:

        if cellsize <= 0:
            raise QgsProcessingException("Cell size for iso area interpolation must be > 0")
        
        #pack iso_point_features in a QgsFeatureSource in order to be usable for QgsInterpolator
        iso_point_layer: QgsVectorLayer = QneatUtilities.buildQgsVectorLayer(iso_points, "iso_points", self.analysis_crs, iso_points)
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

        tin_interpolator = QgsTinInterpolator([layer_data], QgsTinInterpolator.TinInterpolation.Linear)
        
        extent : QgsRectangle = iso_point_layer.extent()
        ncol = max(1, ceil(extent.width() / cellsize))
        nrows = max(1, ceil(extent.width() / cellsize))
        
        writer = QgsGridFileWriter(tin_interpolator, output_interpolation_path, extent, ncol, nrows)
        result = writer.writeFile() 
        if result != 0:
            raise QgsProcessingException(f"Failed to write interpolation result file.")

        output_raster = QgsRasterLayer(output_interpolation_path, "temp_qneat3_interpolation_raster")
        output_raster.setCrs(self.analysis_crs)

        return output_raster

    def calcIsoAreas(self, input_interpolation_raster: str, max_cost: float, interval: float, iso_area_type : IsoAreaType) -> QgsVectorLayer:
        
        interpolation_raster = gdal.Open(input_interpolation_raster)
        if interpolation_raster is None:
            raise QgsProcessingException("Could not open Interpolation result, please use another cellsize, iso area extent or obtain a valid interpolation raster with the QNEAT Iso-Area as Interpolation algorithm.")
        
        band = interpolation_raster.GetRasterBand(1)
        xsize_in = band.XSize
        ysize_in = band.YSize

        ogr_driver = ogr.GetDriverByName("MEMORY")
        contours = ogr_driver.CreateDataSource("iso_areas")
        

        srs: osr.SpatialReference = osr.SpatialReference()
        srs.ImportFromWkt( interpolation_raster.GetProjectionRef() )

        ogr_layer: ogr.Layer = contours.CreateLayer(
            "contours",
            srs = srs,
            geom_type=ogr.wkbLineString
        )

        #Fields
        field_list = list()
        id_field: ogr.FieldDefn = ogr.FieldDefn('id', ogr.OFTInteger)
        cost_level_field: ogr.FieldDefn = ogr.FieldDefn('cost_level', ogr.OFTReal)
        field_list.append(id_field, cost_level_field)

        ogr_layer.CreateFields(field_list)

        max_level = interval * ceil(max_cost/interval) + interval
        levels: list[float] = list(range(start=interval, end=max_level, step=interval))

        gdal.ContourGenerate(
            band,
            interval,
            0.0,
            levels, #fixed levels
            0,
            -9999,
            ogr_layer,
            0,
            1
        )

        iso_areas = QgsVectorLayer("LineString", "iso_areas", "memory")
        iso_areas.setCrs(self.analysis_crs)

        iso_area_fields = QgsFields()
        iso_area_fields.append(QgsField('id', QMetaType.Type.LongLong))
        iso_area_fields.append(QgsField('cost_level'), QMetaType.Type.Double)
        provider = iso_areas.dataProvider()
        provider.addAttributes(iso_area_fields)
        iso_areas.updatedFields()

        iso_area_features = list()
        ogr_layer.ResetReading()
        for ogr_feat in ogr_layer:
            qgs_feat = QgsFeature(iso_area_fields)

            ogr_geom = ogr_feat.GetGeometryRef()
            if ogr_geom and IsoAreaType.CONTOURS:
                qgs_feat.setGeometry(QgsGeometry.fromWkt(ogr_geom.ExportToWkt()))
            elif ogr_geom and IsoAreaType.POLYGONS:
                geom: QgsGeometry = QgsGeometry.fromWkt(ogr_feat.ExportToWkt())

                if not geom or geom.isEmpty():
                    continue #TODO!!!

                #single polygons
                if geom.wkbType() == Qgis.WkbType.LineString and not geom.isMultipart():
                    line = geom.asPolyline()
                    if len(line) >= 4 and line[0] == line[-1]:
                        qgs_feat.setGeometry(QgsGeometry.fromPolygonXY([line]))
                    else:
                        continue #TODO!!!
                elif geom.wkbType() == Qgis.WkbType.LineString and geom.isMultipart():
                    polygons = list()
                    for line in geom.asMultiPolyline():
                        if len(line) >= 4 and line [0] == line[-1]:
                            polygons.append(QgsGeometry.fromPolygonXY([line]))
                        else:
                            continue #TODO!!!
                    
                    multipolygon = QgsGeometry.unaryUnion(polygons)
                    qgs_feat.setGeometry(QgsGeometry.fromMultiPolygonxy(multipolygon))

            qgs_feat.setAttribute("id", ogr_feat.GetField("id"))
            qgs_feat.setAttribute("cost_level", ogr_feat.GetField("cost_level"))

            iso_area_features.append(qgs_feat)
        
        provider.addFeatures(iso_area_features)
        iso_areas.updateExtents()

        return iso_areas
    
    
    def calcIsoPolygons(self, max_dist, interval, interpolation_raster_path):
        featurelist = []
        
        try:
            import matplotlib.pyplot as plt
        except:
            return featurelist
    
        ds_in = gdal.Open(interpolation_raster_path)
        band_in = ds_in.GetRasterBand(1)
        xsize_in = band_in.XSize
        ysize_in = band_in.YSize
    
        geotransform_in = ds_in.GetGeoTransform()
    
        srs = osr.SpatialReference()
        srs.ImportFromWkt( ds_in.GetProjectionRef() )

        raster_values = band_in.ReadAsArray(0, 0, xsize_in, ysize_in)
        raster_values[raster_values < 0] = max_dist + 1000 #necessary to produce rectangular array from raster
        #nodata values get replaced by the maximum value + 1
        
        x_pos = linspace(geotransform_in[0], geotransform_in[0] + geotransform_in[1] * raster_values.shape[1], raster_values.shape[1])
        y_pos = linspace(geotransform_in[3], geotransform_in[3] + geotransform_in[5] * raster_values.shape[0], raster_values.shape[0])
        x_grid, y_grid = meshgrid(x_pos, y_pos)        
        
        start = interval
        end = interval * ceil(max_dist/interval) +interval
    
        levels = arange(start, end, interval)

        fid = 0
        for current_level in nditer(levels):
            self.feedback.pushInfo("[QNEAT3Network][calcIsoPolygons] calculating {}-level contours".format(current_level))
            contours = plt.contourf(x_grid, y_grid, raster_values, [0, current_level], antialiased=True)
        
            for contour_path in contours.get_paths(): 
    
                polygon_list = []
                
                for vertex in contour_path.to_polygons():
                    x = vertex[:,0]
                    y = vertex[:,1]

                    polylinexy_list = [QgsPointXY(i[0], i[1]) for i in zip(x,y)]
                    polygon_list.append(polylinexy_list)
                
                feat = QgsFeature()
                fields = QgsFields()
                fields.append(QgsField('id', QVariant.Int, '', 254, 0))
                fields.append(QgsField('cost_level', QVariant.Double, '', 20, 7))
                feat.setFields(fields)
                geom = QgsGeometry().fromPolygonXY(polygon_list)
                feat.setGeometry(geom)
                feat['id'] = fid
                feat['cost_level'] = float(current_level)
                

                featurelist.insert(0, feat)
            fid=fid+1    
        """Maybe move to algorithm"""
        #featurelist = featurelist[::-1] #reverse
        self.feedback.pushInfo("[QNEAT3Network][calcIsoPolygons] number of elements in contour_featurelist: {}".format(len(featurelist)))
        return featurelist
        
class QneatAnalysisPoint():
    
    def __init__(self, feature: QgsFeature, graph_vertex_id: int, graph_vertex_geom: QgsPointXY, graph_entry_cost: float):
        self.feature: QgsFeature = feature
        self.graph_vertex_id: int = graph_vertex_id
        self.graph_vertex_geom: QgsPointXY = graph_vertex_geom
        self.graph_entry_cost: float = graph_entry_cost
        self.graph_entry_geom: QgsGeometry = QgsGeometry().fromPolylineXY([self.feature.geometry.asPoint(), self.graph_entry_geom])
    
    def __str__(self):
        return "QneatAnalysisPoint: feature_id: {:30} referencing graph_vertex_id: {:d}".format(self.feature.id(), self.graph_vertex_id)    
                                                                                                                                                                                                                        
class MatrixType(Enum):
    TABLE = 0
    LINE = 1
    ROUTE = 2

class IsoAreaType(Enum):
    CONTOURS = 0
    POLYGONS = 1