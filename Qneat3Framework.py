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

import time, datetime
import gdal

from math import floor, ceil
from numpy import arange, meshgrid, insert
from osgeo import osr
from qgis.core import QgsRasterLayer, QgsFeatureSink, QgsFeature, QgsFields, QgsField, QgsGeometry, QgsDistanceArea, QgsUnitTypes
from qgis.analysis import QgsVectorLayerDirector, QgsNetworkDistanceStrategy, QgsNetworkSpeedStrategy, QgsGraphAnalyzer, QgsGraphBuilder, QgsInterpolator, QgsTinInterpolator, QgsIDWInterpolator, QgsGridFileWriter
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
        
        self.feedback.pushInfo("[QNEAT3Network]: setting up parameters")
        self.AnalysisCrs = input_analysisCrs
        
        #init direction fields
        self.feedback.pushInfo("[QNEAT3Network]: setting up network direction parameters")
        self.directedAnalysis = self.setNetworkDirection((input_directionFieldName, input_forwardValue, input_backwardValue, input_bothValue, input_defaultDirection))
        self.director = QgsVectorLayerDirector(input_network,
                                    getFieldIndexFromQgsProcessingFeatureSource(input_network, input_directionFieldName),
                                    input_forwardValue,
                                    input_backwardValue,
                                    input_bothValue,
                                    input_defaultDirection)

        #init analysis points
        self.feedback.pushInfo("[QNEAT3Network]: setting up analysis points")
        if isinstance(input_points,(list,)):
            self.list_input_points = input_points #[QgsPointXY]
        else:
            self.list_input_points = getListOfPoints(input_points) #[QgsPointXY]
            self.input_points = input_points
    
        #Setup cost-strategy pattern.
        self.feedback.pushInfo("[QNEAT3Network]: Setting analysis strategy: {}".format(input_strategy))
        self.setNetworkStrategy(input_strategy, input_network, input_speedField, input_defaultSpeed)
        self.director.addStrategy(self.strategy)
        #add the strategy to the QgsGraphDirector
        self.director.addStrategy(self.strategy)
        self.builder = QgsGraphBuilder(self.AnalysisCrs)
        #tell the graph-director to make the graph using the builder object and tie the start point geometry to the graph
        
        self.feedback.pushInfo("[QNEAT3Network]: Start tying analysis points to the graph and building it.")
        self.feedback.pushInfo("...This is a compute intensive task and may take some time depending on network size")
        start_local_time = time.localtime()
        start_time = time.time()
        self.feedback.pushInfo("...Start Time: {}".format(time.strftime(":%Y-%m-%d %H:%M:%S", start_local_time)))
        self.list_tiedPoints = self.director.makeGraph(self.builder, self.list_input_points)
        self.network = self.builder.graph()
        end_local_time = time.localtime()
        end_time = time.time()
        self.feedback.pushInfo("...End Time: {}".format(time.strftime(":%Y-%m-%d %H:%M:%S", end_local_time)))
        self.feedback.pushInfo("...Total Build Time: {}".format(end_time-start_time))
        self.feedback.pushInfo("[QNEAT3Network]: Analysis setup complete")
        
            
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
        else:
            self.strategy = QgsNetworkSpeedStrategy(speedFieldId, float(input_defaultSpeed), multiplier * 1000.0 / 3600.0)
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
        
    def calcIsoPoints(self, analysis_point_list, max_dist):
        iso_pointcloud = dict()
        
        for point in analysis_point_list:
            dijkstra_query = self.calcDijkstra(point.network_vertex_id, 0)
            tree = dijkstra_query[0]
            cost = dijkstra_query[1]
            
            current_start_point_id = point.point_id
            field_type = getFieldDatatypeFromPythontype(current_start_point_id)
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
                            self.feedback.pushInfo("insert idx {} with {} cost".format(toVertexId, current_cost))
                            iso_pointcloud.update({toVertexId: feat})
                        if toVertexId in iso_pointcloud.keys() and iso_pointcloud.get(toVertexId)['cost'] > current_cost:
                            #if the vertex already exists in the iso_pointcloud and the c
                            self.feedback.pushInfo("replace idx {} with {} cost".format(toVertexId, current_cost))
                            iso_pointcloud.pop(toVertexId)
                            iso_pointcloud.update({toVertexId: feat})
                        #count up to next vertex
                i = i + 1 
                
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
        
        writer = QgsGridFileWriter(tin_interpolator, interpolation_raster_path, rect, ncol, nrows, resolution, resolution)
        writer.writeFile(self.feedback)  # Creating .asc raste
        return QgsRasterLayer(interpolation_raster_path, "temp_qneat3_interpolation_raster", True)        
    
    def calcIsoContours(self, interval, sink, interpolation_raster_path):
        try:
            import matplotlib.pyplot as plt
            ds_in = gdal.Open(interpolation_raster_path)
            band_in = ds_in.GetRasterBand(1)
            xsize_in = band_in.XSize
            ysize_in = band_in.YSize
        
            geotransform_in = ds_in.GetGeoTransform()
        
            srs = osr.SpatialReference()
            srs.ImportFromWkt( ds_in.GetProjectionRef() )  
       
            x_pos = arange(geotransform_in[0], geotransform_in[0] + xsize_in*geotransform_in[1], geotransform_in[1])
            y_pos = arange(geotransform_in[3], geotransform_in[3] + ysize_in*geotransform_in[5], geotransform_in[5])
            x_grid, y_grid = meshgrid(x_pos, y_pos)
        
            raster_values = band_in.ReadAsArray(0, 0, xsize_in, ysize_in)
        
            stats = band_in.GetStatistics(False, True)
            
            min_value = stats[0]
            min_level = interval * floor(min_value/interval)
           
            max_value = stats[1]
            #Due to range issues, a level is added
            max_level = interval * (1 + ceil(max_value/interval)) 
        
            levels = arange(min_level, max_level, interval)
        
            contours = plt.contourf(x_grid, y_grid, raster_values, levels)
        
            fields = QgsFields()
            fields.append(QgsField('id', QVariant.Int, '', 254, 0))
            fields.append(QgsField('cost_level', QVariant.Double, '', 254, 7))
            """Maybe move to algorithm"""
            for i, level in enumerate(range(len(contours.collections))):
                paths = contours.collections[level].get_paths()
                for path in paths:
                    
                    feat = QgsFeature()
                    feat.setFields(fields)
                    geom = QgsGeometry().fromPolygonXY(path)
                    feat.setGeometry(geom)
                    feat['id'] = i
                    feat['cost_level'] = level
                    
                    sink.addFeature(feat, QgsFeatureSink.FastInsert) 
            """Maybe move to algorithm"""
            return sink
        except:
            return sink
    
    def calcIsoPolygon(self):
        """
        feat_out = ogr.Feature( dst_layer.GetLayerDefn())
        feat_out.SetField( attr_name, contours.levels[level] )
        pol = ogr.Geometry(ogr.wkbPolygon)
        
                        ring = None            
                
                for i in range(len(path.vertices)):
                    point = path.vertices[i]
                    if path.codes[i] == 1:
                        if ring != None:
                            pol.AddGeometry(ring)
                        ring = ogr.Geometry(ogr.wkbLinearRing)
                        
                    ring.AddPoint_2D(point[0], point[1])
                
    
                pol.AddGeometry(ring)
                
                feat_out.SetGeometry(pol)
                if dst_layer.CreateFeature(feat_out) != 0:
                    print "Failed to create feature in shapefile.\n"
                    exit( 1 )
    
                
                feat_out.Destroy()  
        """
        self.iso_polygon
        pass
    
    
        #static interpolation_storage
        
class Qneat3AnalysisPoint():
    
    def __init__(self, layer_name, feature, point_id_field_name, net, vertex_geom):
        self.layer_name = layer_name
        self.point_feature = feature
        self.point_id = feature[point_id_field_name]
        self.point_geom = feature.geometry().asPoint()
        self.network_vertex_id = self.getNearestVertexId(net.network, vertex_geom)
        self.network_vertex = self.getNearestVertex(net.network, vertex_geom)
        self.crs = net.AnalysisCrs
        
    def calcEntryCost(self, strategy, context):
        dist_calculator = QgsDistanceArea()
        dist_calculator.setSourceCrs(self.crs, context.transformContext())
        dist_calculator.setEllipsoid(context.project().ellipsoid())
        dist = dist_calculator.measureLine(self.point_geom, self.network_vertex.point())
        #entry_linestring_geom = self.calcEntryLinestring()
        if strategy == "Shortest":
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
        try:
            pid = str(self.point_id).decode('utf8')
        except UnicodeEncodeError:
            pid = self.point_id
        return u"QneatAnalysisPoint: {} analysis_id: {:30} FROM {:30} TO {:30} network_id: {:d}".format(self.layer_name, pid, self.point_geom.__str__(), self.network_vertex.point().__str__(), self.network_vertex_id)    
                                                                                                                                                                                                                        