"""
***************************************************************************
    Qneat3Framework.py
    ---------------------
    Date                 : January 2018
    Copyright            : (C) 2018 by Clemens Raffler
    Email                : clemens dot raffler at gmail dot com
***************************************************************************
"""



from qgis.core import *
from qgis.analysis import *

from PyQt5.QtCore import QVariant

from QNEAT3.Qneat3Utilities import *

from processing.tools.vector import resolveFieldIndex

    
class Qneat3Network():
    
    """
    QNEAT base-class:
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
        

        feedback.pushInfo("__init__[QneatBaseCalculator]: setting up parameters")
        feedback.pushInfo("__init__[QneatBaseCalculator]: setting up datasets")
        feedback.pushInfo("__init__[QneatBaseCalculator]: setting up network analysis parameters")
        self.AnalysisCrs = input_analysisCrs
        
        #init direction fields
        feedback.pushInfo("__init__[QneatBaseCalculator]: setting up network direction parameters")
        self.directedAnalysis = self.setNetworkDirection((input_forwardValue, input_backwardValue, input_bothValue, input_defaultDirection))
        feedback.pushInfo("...Analysis is directed")
        feedback.pushInfo("...setting up Director")
        self.director = QgsVectorLayerDirector(input_network,
                                    getFieldIndexFromQgsProcessingFeatureSource(input_network, input_directionFieldName),
                                    input_forwardValue,
                                    input_backwardValue,
                                    input_bothValue,
                                    input_defaultDirection)

        #init graph analysis
        feedback.pushInfo("__init__[QneatBaseCalculator]: setting up network analysis")
        feedback.pushInfo("...getting all analysis points")
        
        if isinstance(input_points,(list,)):
            self.list_input_points = input_points
        else:
            self.list_input_points = getListOfPoints(input_points)
            self.input_points = input_points
    
        #Use distance as cost-strategy pattern.
        feedback.pushInfo("...Setting analysis strategy")
        
        self.setNetworkStrategy(input_strategy, input_speedField, input_defaultSpeed)
        self.director.addStrategy(self.strategy)

        #add the strategy to the QgsGraphDirector
        self.director.addStrategy(self.strategy)
        feedback.pushInfo("...Setting the graph builders spatial reference")
        self.builder = QgsGraphBuilder(self.AnalysisCrs)
        #tell the graph-director to make the graph using the builder object and tie the start point geometry to the graph
        feedback.pushInfo("...Tying input_points to the graph")
        self.list_tiedPoints = self.director.makeGraph(self.builder, self.list_input_points)
        #get the graph
        feedback.pushInfo("...Build the graph")
        self.network = self.builder.graph()
        feedback.pushInfo("__init__[QneatBaseCalculator]: init complete")
                
            
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
            
    def setNetworkStrategy(self, input_strategy, input_speedField, input_defaultSpeed):
        distUnit = self.AnalysisCrs.mapUnits()
        multiplier = QgsUnitTypes.fromUnitToUnitFactor(distUnit, QgsUnitTypes.DistanceMeters)
        
        if input_strategy == 0:
            self.strategy = QgsNetworkDistanceStrategy()
        else:
            self.strategy = QgsNetworkSpeedStrategy(input_speedField, input_defaultSpeed, multiplier * 1000.0 / 3600.0)
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
        if strategy == "distance":
            return entry_linestring_geom.length()
        else:
            return None

    def calcEntryLinestring(self):
        return QgsGeometry.fromPolyline([self.point_geom, self.network_vertex.point()])
    
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
                                                                                                                                                                                                                        