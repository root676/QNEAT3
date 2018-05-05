# -*- coding: utf-8 -*-
"""
***************************************************************************
    Qneat3Framework.py
    ---------------------
    Date                 : January 2018
    Copyright            : (C) 2018 by Clemens Raffler
    Email                : clemens dot raffler at gmail dot com
***************************************************************************
"""

import time
import gdal

from math import ceil
from numpy import arange, meshgrid, linspace, nditer
from osgeo import osr
from qgis.core import QgsProject, QgsRasterLayer, QgsFeature, QgsFields, QgsField, QgsGeometry, QgsPointXY, QgsDistanceArea, QgsUnitTypes
from qgis.analysis import QgsVectorLayerDirector, QgsNetworkDistanceStrategy, QgsNetworkSpeedStrategy, QgsGraphAnalyzer, QgsGraphBuilder, QgsInterpolator, QgsTinInterpolator, QgsGridFileWriter
from qgis.PyQt.QtCore import QVariant

from QNEAT3.Qneat3Utilities import getFieldIndexFromQgsProcessingFeatureSource, getListOfPoints, getFieldDatatypeFromPythontype


class Qneat3Network():
    """
    Qneat3Network:
    Provides basic logic for more advanced network analysis algorithms
    """

    def __init__(self, 
                 input_network, #QgsProcessingParameterFeatureSource
                 input_points, #[QgsPointXY] or QgsProcessingParameterFeatureSource or QgsVectorLayer --> Implement List of QgsFeatures [QgsFeatures]
                 input_strategy, #int
                 input_directionFieldName, #str, empty if field not given
                 input_forwardValue, #str
                 input_backwardValue, #str
                 input_bothValue, #str
                 input_defaultDirection, #int
                 input_analysisCrs, #QgsCoordinateReferenceSystem
                 input_speedField, #str
                 input_defaultSpeed, #float
                 input_tolerance, #float
                 feedback #feedback object from processing (log window)
                 ): 
        
        """
        Constructor for a Qneat3Network object.
        @type input_network: QgsProcessingParameterFeatureSource
        @param input_network: input network dataset from processing algorithm 
        @type input_points: QgsProcessingParameterFeatureSource/QgsVectorLayer/[QgsPointXY]
        @param input_points: input point dataset from processing algorithm
        @type input_strategy: int
        @param input_strategy: Strategy parameter (0 for distance evaluation, 1 time evaluation)
        @type directionFieldName: string
        @param directionFieldName: Field name of field containing direction information
        @type input_forwardValue: string
        @param input_forwardValue: Value assigned to forward-directed edges
        @type input_backwardValue: string
        @param input_backwardValue: Value assigned to backward-directed edges
        @type input_bothValue: string
        @param input_bothValues: Value assigned to undirected edges (accessible from both directions)
        @type input_defaultDirection: QgsVectorLayerDirector.DirectionForward/DirectionBackward/DirectionBoth
        @param input_defaultDirection: QgsVectorLayerDirector Direction enum to determine default direction
        @type input_analysisCrs: QgsCoordinateReferenceSystem
        @param input_analysisCrs: Analysis coordinate system
        @type input_speedField: string
        @param input_speedField: Field name of field containing speed information
        @type input_tolerance: float
        @param input_tolerance: tolerance value when connecting graph edges
        @type feedback: QgsProcessingFeedback
        @param feedback: feedback object from processing algorithm
        
        """
        
        #initialize feedback
        self.feedback = feedback
        
        self.feedback.pushInfo("[QNEAT3Network][__init__] Setting up parameters")
        self.AnalysisCrs = input_analysisCrs
        
        #init direction fields
        self.feedback.pushInfo("[QNEAT3Network][__init__] Setting up network direction parameters")
        self.directedAnalysis = self.setNetworkDirection((input_directionFieldName, input_forwardValue, input_backwardValue, input_bothValue, input_defaultDirection))
        self.director = QgsVectorLayerDirector(input_network,
                                    getFieldIndexFromQgsProcessingFeatureSource(input_network, input_directionFieldName),
                                    input_forwardValue,
                                    input_backwardValue,
                                    input_bothValue,
                                    input_defaultDirection)

        #init analysis points
        self.feedback.pushInfo("[QNEAT3Network][__init__] Setting up analysis points")
        if isinstance(input_points,(list,)):
            self.list_input_points = input_points #[QgsPointXY]
        else:
            self.list_input_points = getListOfPoints(input_points) #[QgsPointXY]
            self.input_points = input_points
    
        #Setup cost-strategy pattern.
        self.feedback.pushInfo("[QNEAT3Network][__init__] Setting analysis strategy: {}".format(input_strategy))
        self.setNetworkStrategy(input_strategy, input_network, input_speedField, input_defaultSpeed)
        self.director.addStrategy(self.strategy)
        #add the strategy to the QgsGraphDirector
        self.director.addStrategy(self.strategy)
        self.builder = QgsGraphBuilder(self.AnalysisCrs)
        #tell the graph-director to make the graph using the builder object and tie the start point geometry to the graph
        
        self.feedback.pushInfo("[QNEAT3Network][__init__] Start tying analysis points to the graph and building it.")
        self.feedback.pushInfo("[QNEAT3Network][__init__] This is a compute intensive task and may take some time depending on network size")
        start_local_time = time.localtime()
        start_time = time.time()
        self.feedback.pushInfo("[QNEAT3Network][__init__] Start Time: {}".format(time.strftime(":%Y-%m-%d %H:%M:%S", start_local_time)))
        self.list_tiedPoints = self.director.makeGraph(self.builder, self.list_input_points)
        self.network = self.builder.graph()
        end_local_time = time.localtime()
        end_time = time.time()
        self.feedback.pushInfo("[QNEAT3Network][__init__] End Time: {}".format(time.strftime(":%Y-%m-%d %H:%M:%S", end_local_time)))
        self.feedback.pushInfo("[QNEAT3Network][__init__] Total Build Time: {}".format(end_time-start_time))
        self.feedback.pushInfo("[QNEAT3Network][__init__] Analysis setup complete")
        
            
    def setNetworkDirection(self, directionArgs):    
        if directionArgs.count("") == 0:
            self.directedAnalysis = True
            self.directionFieldId, self.input_forwardValue, self.input_backwardValue, self.input_bothValue, self.input_defaultDirection = directionArgs
        else:
            self.directedAnalysis = False
            
    def setNetworkStrategy(self, input_strategy, input_network, input_speedField, input_defaultSpeed):
        distUnit = self.AnalysisCrs.mapUnits()
        multiplier = QgsUnitTypes.fromUnitToUnitFactor(distUnit, QgsUnitTypes.DistanceMeters)
        
        speedFieldId = getFieldIndexFromQgsProcessingFeatureSource(input_network, input_speedField)
        if input_strategy == 0:
            self.strategy = QgsNetworkDistanceStrategy()
            self.strategy_int = 0
        else:
            self.strategy = QgsNetworkSpeedStrategy(speedFieldId, float(input_defaultSpeed), multiplier * 1000.0 / 3600.0)
            self.strategy_int = 1
        self.multiplier = 3600

    def calcDijkstra(self, startpoint_id, criterion):
        """Calculates Dijkstra on whole network beginning from one startPoint. Returns a list containing a TreeId-Array and Cost-Array that match up with their indices [[tree],[cost]] """
        tree, cost = QgsGraphAnalyzer.dijkstra(self.network, startpoint_id, criterion)
        dijkstra_query = list()
        dijkstra_query.insert(0, tree)
        dijkstra_query.insert(1, cost)
        return dijkstra_query
    
    def calcShortestTree(self, startpoint_id, criterion):
        tree = QgsGraphAnalyzer.shortestTree(self.network, startpoint_id, criterion)
        return tree
        
    def calcIsoPoints(self, analysis_point_list, max_dist, context):
        iso_pointcloud = dict()
        
        for counter, point in enumerate(analysis_point_list):
            self.feedback.pushInfo("[QNEAT3Network][calcIsoPoints] Processing Point {}".format(counter))
            dijkstra_query = self.calcDijkstra(point.network_vertex_id, 0)
            tree = dijkstra_query[0]
            cost = dijkstra_query[1]
            
            current_start_point_id = point.point_id #id of the input point
            current_vertex_id = point.network_vertex_id
            entry_cost = point.entry_cost
            
            field_type = getFieldDatatypeFromPythontype(current_start_point_id)
            
            #startpoints are not part of the Query so they have to be added manually before
            #dikstra is called.
            start_vertex_feat = QgsFeature()
            start_vertex_fields = QgsFields()
            start_vertex_fields.append(QgsField('vertex_id', QVariant.Int, '', 254, 0))
            start_vertex_fields.append(QgsField('cost', QVariant.Double, '', 254, 7))
            start_vertex_fields.append(QgsField('origin_point_id',field_type, '', 254, 7))
            start_vertex_feat.setFields(start_vertex_fields)
            start_vertex_feat['vertex_id'] = current_vertex_id
            start_vertex_feat['cost'] = entry_cost
            start_vertex_feat['origin_point_id'] = current_start_point_id
            geom = QgsGeometry().fromPointXY(self.network.vertex(current_vertex_id).point())
            start_vertex_feat.setGeometry(geom)
            
            iso_pointcloud.update({current_vertex_id: start_vertex_feat})
            
            i = 0
            while i < len(cost):
                #as long as costs at vertex i is greater than iso_distance and there exists an incoming edge (tree[i]!=-1) 
                #consider it as a possible catchment polygon element
                if tree[i] != -1:
                    toVertexId = self.network.edge(tree[i]).toVertex()
                    #if the costs of the current vertex are lower than the radius, append the vertex id to results.
                    if cost[toVertexId] <= max_dist:
                        current_cost = cost[toVertexId]
                        #build feature
                                    
                        feat = QgsFeature()
                        fields = QgsFields()
                        fields.append(QgsField('vertex_id', QVariant.Int, '', 254, 0))
                        fields.append(QgsField('cost', QVariant.Double, '', 254, 7))
                        fields.append(QgsField('origin_point_id',field_type, '', 254, 7))
                        feat.setFields(fields)
                        feat['vertex_id'] = toVertexId
                        feat['cost'] = current_cost
                        feat['origin_point_id'] = current_start_point_id
                        geom = QgsGeometry().fromPointXY(self.network.vertex(toVertexId).point())
                        feat.setGeometry(geom)
                        
                        if toVertexId not in iso_pointcloud:
                            #ERROR: FIRST POINT IN POINTCLOUD WILL NEVER BE ADDED
                            iso_pointcloud.update({toVertexId: feat})
                        if toVertexId in iso_pointcloud.keys() and iso_pointcloud.get(toVertexId)['cost'] > current_cost:
                            #if the vertex already exists in the iso_pointcloud and the cost is greater than the existing cost
                            del iso_pointcloud[toVertexId]
                            #iso_pointcloud.pop(toVertexId)
                            iso_pointcloud.update({toVertexId: feat})
                        #count up to next vertex
                i = i + 1 
                if i%1000 == 0:
                    self.feedback.pushInfo("[QNEAT3Network][calcIsoPoints] Added {} Nodes to iso pointcloud...".format(i))
                    
        return iso_pointcloud.values() #list of QgsFeature (=QgsFeatureList)
                
                
    def calcIsoInterpolation(self, iso_point_layer, resolution, interpolation_raster_path):
        layer_data = QgsInterpolator.LayerData()
        QgsInterpolator.LayerData
        
        layer_data.source = iso_point_layer #in QGIS2: vectorLayer
        layer_data.valueSource = QgsInterpolator.ValueAttribute
        layer_data.interpolationAttribute =  1 #take second field to get costs
        layer_data.sourceType = QgsInterpolator.SourcePoints

        tin_interpolator = QgsTinInterpolator([layer_data], QgsTinInterpolator.Linear)
        
        rect = iso_point_layer.extent()
        ncol = int((rect.xMaximum() - rect.xMinimum()) / resolution)
        nrows = int((rect.yMaximum() - rect.yMinimum()) / resolution)
        
        writer = QgsGridFileWriter(tin_interpolator, interpolation_raster_path, rect, ncol, nrows)
        writer.writeFile(self.feedback)  # Creating .asc raste
        return QgsRasterLayer(interpolation_raster_path, "temp_qneat3_interpolation_raster")
    
    def calcIsoLimewiseInterpolation(self, iso_point_layer, resolution, interpolation_raster_path):
        return 0

    def calcIsoContours(self, max_dist, interval, interpolation_raster_path):
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
            self.feedback.pushInfo("[QNEAT3Network][calcIsoContours] Calculating {}-level contours".format(current_level))
            contours = plt.contourf(x_grid, y_grid, raster_values, [0, current_level], antialiased=True)
            
            for collection in contours.collections:
                for contour_paths in collection.get_paths():                    
                    for polygon in contour_paths.to_polygons():
                        x = polygon[:,0]
                        y = polygon[:,1]

                        polylinexy_list = [QgsPointXY(i[0], i[1]) for i in zip(x,y)]
                    
                        feat = QgsFeature()
                        fields = QgsFields()
                        fields.append(QgsField('id', QVariant.Int, '', 254, 0))
                        fields.append(QgsField('cost_level', QVariant.Double, '', 20, 7))
                        feat.setFields(fields)
                        geom = QgsGeometry().fromPolylineXY(polylinexy_list)
                        feat.setGeometry(geom)
                        feat['id'] = fid
                        feat['cost_level'] = float(current_level)
                        featurelist.insert(0, feat)
                        
            fid=fid+1    
        return featurelist

    
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
        

            
            for collection in contours.collections:
                for contour_path in collection.get_paths(): 
        
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
        
class Qneat3AnalysisPoint():
    
    def __init__(self, layer_name, feature, point_id_field_name, net, vertex_geom, feedback):
        self.layer_name = layer_name
        self.point_feature = feature
        self.point_id = feature[point_id_field_name]
        self.point_geom = feature.geometry().asPoint()
        self.network_vertex_id = self.getNearestVertexId(net.network, vertex_geom)
        self.network_vertex = self.getNearestVertex(net.network, vertex_geom)
        self.crs = net.AnalysisCrs
        self.strategy = net.strategy_int
        self.entry_cost = self.calcEntryCost(feedback)
        
    def calcEntryCost(self, feedback):
        dist_calculator = QgsDistanceArea()
        dist_calculator.setSourceCrs(QgsProject().instance().crs(), QgsProject().instance().transformContext())
        dist_calculator.setEllipsoid(QgsProject().instance().crs().ellipsoidAcronym())
        dist = dist_calculator.measureLine([self.point_geom, self.network_vertex.point()])
        feedback.pushInfo("[QNEAT3Network][calcEntryCost] Ellipsoidal entry cost to vertex {} = {}".format(self.network_vertex_id, dist))
        if self.strategy == 0:
            return dist
        else:
            return dist/1.3888 #length/(m/s) todo: Make dynamic


    def calcEntryLinestring(self):
        return QgsGeometry.fromPolylineXY([self.point_geom, self.network_vertex.point()])
    
    def getNearestVertexId(self, network, vertex_geom):
        return network.findVertex(vertex_geom)
        
    def getNearestVertex(self, network, vertex_geom):
        return network.vertex(self.getNearestVertexId(network, vertex_geom))
    
    def __str__(self):
        return u"QneatAnalysisPoint: {} analysis_id: {:30} FROM {:30} TO {:30} network_id: {:d}".format(self.layer_name, self.point_id, self.point_geom.__str__(), self.network_vertex.point().__str__(), self.network_vertex_id)    
                                                                                                                                                                                                                        