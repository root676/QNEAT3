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
from qgis.core import QgsGeometry, QgsUnitTypes
from qgis.analysis import QgsVectorLayerDirector, QgsNetworkDistanceStrategy, QgsNetworkSpeedStrategy, QgsGraphAnalyzer, QgsGraphBuilder

from QNEAT3.Qneat3Utilities import getFieldIndexFromQgsProcessingFeatureSource, getListOfPoints
    
class Qneat3Network():
    
    """
    QNEAT3 base-class:
    Provides basic logic for more advanced network analysis algorithms
    """

    def __init__(self, 
                 input_network, #QgsProcessingParameterFeatureSource
                 input_points, #[QgsPointXY] or QgsProcessingParameterFeatureSource
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
        

        feedback.pushInfo("[QNEAT3Network]: setting up parameters")
        self.AnalysisCrs = input_analysisCrs
        
        #init direction fields
        feedback.pushInfo("[QNEAT3Network]: setting up network direction parameters")
        self.directedAnalysis = self.setNetworkDirection((input_directionFieldName, input_forwardValue, input_backwardValue, input_bothValue, input_defaultDirection))
        self.director = QgsVectorLayerDirector(input_network,
                                    getFieldIndexFromQgsProcessingFeatureSource(input_network, input_directionFieldName),
                                    input_forwardValue,
                                    input_backwardValue,
                                    input_bothValue,
                                    input_defaultDirection)

        #init analysis points
        feedback.pushInfo("[QNEAT3Network]: setting up analysis points")
        if isinstance(input_points,(list,)):
            self.list_input_points = input_points
        else:
            self.list_input_points = getListOfPoints(input_points)
            self.input_points = input_points
    
        #Setup cost-strategy pattern.
        feedback.pushInfo("[QNEAT3Network]: Setting analysis strategy: {}".format(input_strategy))
        self.setNetworkStrategy(input_strategy, input_network, input_speedField, input_defaultSpeed)
        self.director.addStrategy(self.strategy)
        #add the strategy to the QgsGraphDirector
        self.director.addStrategy(self.strategy)
        self.builder = QgsGraphBuilder(self.AnalysisCrs)
        #tell the graph-director to make the graph using the builder object and tie the start point geometry to the graph
        
        feedback.pushInfo("[QNEAT3Network]: Start tying analysis points to the graph and building it.")
        feedback.pushInfo("...This is a compute intensive task and may take some time depending on network size")
        start_local_time = time.localtime()
        start_time = time.time()
        feedback.pushInfo("...Start Time: {}".format(time.strftime(":%Y-%m-%d %H:%M:%S", start_local_time)))
        self.list_tiedPoints = self.director.makeGraph(self.builder, self.list_input_points)
        self.network = self.builder.graph()
        end_local_time = time.localtime()
        end_time = time.time()
        feedback.pushInfo("...End Time: {}".format(time.strftime(":%Y-%m-%d %H:%M:%S", end_local_time)))
        feedback.pushInfo("...Total Build Time: {}".format(end_time-start_time))
        feedback.pushInfo("[QNEAT3Network]: Analysis setup complete")
                
            
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
            
        
class Qneat3AnalysisPoint():
    
    def __init__(self, layer_name, feature, point_id_field_name, network, vertex_geom):
        self.layer_name = layer_name
        self.point_id = feature[point_id_field_name]
        self.point_geom = feature.geometry().asPoint()
        self.network_vertex_id = self.getNearestVertexId(network, vertex_geom)
        self.network_vertex = self.getNearestVertex(network, vertex_geom)
        
    def calcEntryCost(self, strategy):
        entry_linestring_geom = self.calcEntryLinestring()
        if strategy == "Shortest":
            return entry_linestring_geom.length()
        else:
            return entry_linestring_geom.length()/1.3888 #length/(m/s) todo: Make dynamic

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

class Qneat3GeometryException(Exception):
    def __init__(self, given_geom_type, expected_geom_type):
        
        self.message = "Dataset has wrong geometry type. Got {} dataset but expected {} dataset instead. ".format( given_geom_type, expected_geom_type)

        super(Qneat3GeometryException, self).__init__(self.message)
        
class Qneat3CrsException(Exception):
    def __init__(self, *crs):
    
        self.message = "Coordinate Reference Systems don't match up: {} Reproject all datasets so that their CRSs match up.".format(list(crs))

        super(Qneat3CrsException, self).__init__(self.message)
                                                                                                                                                                                                                        