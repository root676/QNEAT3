# -*- coding: utf-8 -*-
"""
***************************************************************************
    OdMatrixFromLayersAsLines.py
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

__author__ = 'Clemens Raffler'
__date__ = 'February 2018'
__copyright__ = '(C) 2018, Clemens Raffler'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
from collections import OrderedDict

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (Qgis,
                       QgsWkbTypes,
                       QgsFields,
                       QgsField,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterDefinition
                       )

from qgis.analysis import (QgsVectorLayerDirector)

from ..QneatFramework import QneatCore, OptimizationStrategy, MatrixType, ProgressRange
from ..QneatUtilities import getFieldDatatype, getOdMatrixFields

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]

from typing import (
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsFields,
        QgsProcessingFeatureSource
        )

class OdMatrixFromLayersAsLines(QgsProcessingAlgorithm):

    GRAPH_LAYER = 'GRAPH_LAYER'
    ORIGIN_POINT_LAYER = 'ORIGIN_POINT_LAYER'
    ORIGIN_ID_FIELD = 'ORIGIN_ID_FIELD'
    DESTINATION_POINT_LAYER = 'DESTINATION_POINT_LAYER'
    DESTINATION_ID_FIELD = 'DESTINATION_ID_FIELD'    
    STRATEGY = 'STRATEGY'
    ENTRY_COST_CALCULATION_METHOD = 'ENTRY_COST_CALCULATION_METHOD'
    DIRECTION_FIELD = 'DIRECTION_FIELD'
    VALUE_FORWARD = 'VALUE_FORWARD'
    VALUE_BACKWARD = 'VALUE_BACKWARD'
    VALUE_BOTH = 'VALUE_BOTH'
    DEFAULT_DIRECTION = 'DEFAULT_DIRECTION'
    SPEED_FIELD = 'SPEED_FIELD'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    TOLERANCE = 'TOLERANCE'
    OUTPUT = 'OUTPUT'
    MATRIX_GEOMETRY_TYPE = 'MATRIX_GEOMETRY_TYPE'

    def __init__(self):
        super().__init__()

    def createInstance(self):
        return OdMatrixFromLayersAsLines()

    def tr(self, string):
        return QCoreApplication.translate('QNEAT', string)

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_matrix.svg'))

    def group(self):
        return self.tr('Distance Matrices')

    def groupId(self):
        return 'networkbaseddistancematrices'
    
    def name(self):
        return 'OdMatrixFromLayersAsLines'

    def displayName(self):
        return self.tr('OD Matrix from Layers as Lines (m:n)')
    
    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements OD-matrix analysis to return the <b>matrix of origin-destination pairs as lines yielding network based costs</b> on a given <b>network dataset between two layer of points (m:n)</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>). Distances are measured accounting for <b>ellipsoids</b>, entry-, exit-, network- and total costs are listed in the result attribute-table.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following parameters must be set to run the algorithm:"\
                "<ul><li>Network layer</li><li>From-point layer</li><li>Unique from-point ID field (numerical)</li><li>To-point layer</li><li>Unique to-point ID field (numerical)</li><li>Cost strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed field</li><li>Default speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is one layer:"\
                "<ul><li>OD-matrix as lines with network based distances as attributes</li></ul>"    

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest Path (distance optimization)'),
                                      self.tr('Fastest Path (time optimization)')]

        self.MATRIX_GEOMETRY_TYPES = [self.tr('Line'),
                                      self.tr('Route')]

        self.ENTRY_COST_CALCULATION_METHODS = [self.tr('Planar'),
                                               self.tr('Ellipsoidal')]
            
        self.addParameter(QgsProcessingParameterFeatureSource(self.GRAPH_LAYER,
                                                              self.tr('Graph layer'),
                                                              [Qgis.ProcessingSourceType.VectorLine]))
        
        self.addParameter(QgsProcessingParameterFeatureSource(self.ORIGIN_POINT_LAYER,
                                                              self.tr('Origin point layer'),
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        
        self.addParameter(QgsProcessingParameterField(self.ORIGIN_ID_FIELD,
                                                       self.tr('Origin point ID field'),
                                                       None,
                                                       self.ORIGIN_POINT_LAYER,
                                                       optional=False))
        
        self.addParameter(QgsProcessingParameterFeatureSource(self.DESTINATION_POINT_LAYER,
                                                      self.tr('Destination point layer'),
                                                      [Qgis.ProcessingSourceType.VectorPoint]))
        
        self.addParameter(QgsProcessingParameterField(self.DESTINATION_ID_FIELD,
                                                     self.tr('Destination point ID field'),
                                                     None,
                                                     self.DESTINATION_POINT_LAYER,
                                                     optional=False))
        
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Optimization Criterion'),
                                                     self.STRATEGIES,
                                                     defaultValue=0))

        params = []
        params.append(QgsProcessingParameterEnum(self.ENTRY_COST_CALCULATION_METHOD,
                                                 self.tr('Entry Cost calculation method'),
                                                 self.ENTRY_COST_CALCULATION_METHODS,
                                                 defaultValue=0))
        params.append(QgsProcessingParameterEnum(self.MATRIX_GEOMETRY_TYPE,
                                                 self.tr('Matrix output type'),
                                                 self.MATRIX_GEOMETRY_TYPES,
                                                 defaultValue=0))
        params.append(QgsProcessingParameterField(self.DIRECTION_FIELD,
                                                  self.tr('Direction field'),
                                                  None,
                                                  self.GRAPH_LAYER,
                                                  optional=True))
        params.append(QgsProcessingParameterString(self.VALUE_FORWARD,
                                                   self.tr('Value for forward direction'),
                                                   optional=True))
        params.append(QgsProcessingParameterString(self.VALUE_BACKWARD,
                                                   self.tr('Value for backward direction'),
                                                   optional=True))
        params.append(QgsProcessingParameterString(self.VALUE_BOTH,
                                                   self.tr('Value for both directions'),
                                                   optional=True))
        params.append(QgsProcessingParameterEnum(self.DEFAULT_DIRECTION,
                                                 self.tr('Default direction'),
                                                 list(self.DIRECTIONS.keys()),
                                                 defaultValue=2))
        params.append(QgsProcessingParameterField(self.SPEED_FIELD,
                                                  self.tr('Speed field'),
                                                  None,
                                                  self.GRAPH_LAYER,
                                                  optional=True))
        params.append(QgsProcessingParameterNumber(self.DEFAULT_SPEED,
                                                   self.tr('Default speed (km/h)'),
                                                   Qgis.ProcessingNumberParameterType.Double,
                                                   5.0, False, 0))
        params.append(QgsProcessingParameterNumber(self.TOLERANCE,
                                                   self.tr('Topology tolerance'),
                                                   Qgis.ProcessingNumberParameterType.Double,
                                                   0.0, False, 0))

        for p in params:
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)

        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Output OD Matrix'), Qgis.ProcessingSourceType.VectorLine), True)

    def processAlgorithm(self, parameters, context, feedback):
        feedback.setProgress(0)
        feedback.pushInfo(self.tr("Running '{}'".format(self.displayName())))

        network: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.GRAPH_LAYER, context)
        origin_points: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.ORIGIN_POINT_LAYER, context)
        origin_id_field: str = self.parameterAsString(parameters, self.ORIGIN_ID_FIELD, context) 
        destination_points: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.DESTINATION_POINT_LAYER, context)
        destination_id_field: str = self.parameterAsString(parameters, self.DESTINATION_ID_FIELD, context)
        strategy: OptimizationStrategy = OptimizationStrategy(self.parameterAsEnum(parameters, self.STRATEGY, context))
        matrix_geometry_type: MatrixType =  MatrixType(self.parameterAsEnum(parameters, self.MATRIX_GEOMETRY_TYPE, context))

        entry_cost_calc_method: int = self.parameterAsEnum(parameters, self.ENTRY_COST_CALCULATION_METHOD, context) 
        directionFieldName: str = self.parameterAsString(parameters, self.DIRECTION_FIELD, context)
        forwardValue: str = self.parameterAsString(parameters, self.VALUE_FORWARD, context) 
        backwardValue: str = self.parameterAsString(parameters, self.VALUE_BACKWARD, context) 
        bothValue: str = self.parameterAsString(parameters, self.VALUE_BOTH, context) 
        defaultDirection: int = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) 
        speedFieldName: str = self.parameterAsString(parameters, self.SPEED_FIELD, context) 
        defaultSpeed: float = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) 
        tolerance: float = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        
        #check if network and points have the same crs
        if network.sourceCrs() == origin_points.sourceCrs() and network.sourceCrs() == destination_points.sourceCrs():
            analysis_crs = network.sourceCrs()
        elif network.sourceCrs() == origin_points.sourceCrs() and network.sourceCrs() != destination_points.sourceCrs():
            raise QgsProcessingException(f"Coordinate reference system (CRS) of graph is {network.sourceCrs().authid()} and doesn't match up with the CRS of the destination point layer ({destination_points.sourceCrs().authid()}). Reproject so that the analysis layers CRSs match up.")
        elif network.sourceCrs() != origin_points.sourceCrs() and network.sourceCrs() == destination_points.sourceCrs():
            raise QgsProcessingException(f"Coordinate reference system (CRS) of graph is {network.sourceCrs().authid()} and doesn't match up with the CRS of the origin point layer ({origin_points.sourceCrs().authid()}). Reproject so that the analysis layers CRSs match up.")
        else:
             raise QgsProcessingException(f"Coordinate reference system (CRS) of graph is {network.sourceCrs().authid()} and doesn't match up with the CRSs of both, origin ({origin_points.sourceCrs().authid()}) and destination ({destination_points.sourceCrs().authid()}) point layers. Reproject so that the analysis layers CRSs match up.")
        
        o_fields = QgsFields()
        o_fields.append(QgsField('fid', QVariant.LongLong))
        o_fields.append(QgsField('user_id', getFieldDatatype(origin_points, origin_id_field)))
        o_fields.append(QgsField('type', QVariant.String))

        #unpack all points into one list
        input_point_features: list[QgsFeature] = []

        for f in origin_points.getFeatures():
            of = QgsFeature(o_fields)
            of["fid"] = f.id()
            of["user_id"] = f[origin_id_field]
            of["type"] = "o"
            of.setGeometry(f.geometry())

            input_point_features.append(of)
        
        d_fields = QgsFields()
        d_fields.append(QgsField('fid', QVariant.LongLong))
        d_fields.append(QgsField('user_id', getFieldDatatype(destination_points, destination_id_field)))
        d_fields.append(QgsField('type', QVariant.String))

        for f in destination_points.getFeatures():
            df = QgsFeature(d_fields)
            df["fid"] = f.id()
            df["user_id"] = f[destination_id_field]
            df["type"] = "d"
            df.setGeometry(f.geometry())
    
            input_point_features.append(df)    

        build_progress_range = ProgressRange(feedback, 0.0, 0.5)

        core = QneatCore(network, 
                         input_point_features, 
                         strategy, 
                         speedFieldName, 
                         defaultSpeed, 
                         tolerance, 
                         entry_cost_calc_method, 
                         build_progress_range, 
                         directionFieldName, 
                         forwardValue, 
                         backwardValue, 
                         bothValue, 
                         defaultDirection)
        
        total_workload = float(pow(len(core.analysis_points),2))

        output_fields: QgsFields = getOdMatrixFields(origin_points, origin_id_field, destination_points, destination_id_field)
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, output_fields, Qgis.WkbType.LineString, analysis_crs)

        feedback.pushInfo(f"{int(total_workload)} od pairs will be routed")
        od_progress_range = ProgressRange(feedback, 0.5, 1.0)

        o_analysis_points = [o for o in core.analysis_points if o.feature["type"] == 'o']
        d_analysis_points = [d for d in core.analysis_points if d.feature["type"] == 'd']

        i: int = 0
        for origin_point in o_analysis_points:
            tree, cost = core.calcDijkstra(origin_point.graph_vertex_id)
            for destination_point in d_analysis_points:
                outfeat = core.queryOdPair(tree, cost, origin_point, origin_id_field, destination_point, destination_id_field, matrix_geometry_type)                
                sink.addFeature(outfeat, QgsFeatureSink.Flag.FastInsert)  
                i+=i
                od_progress_range.feedback().setProgress(i/total_workload)

        results = {}
        results[self.OUTPUT] = dest_id
        return results