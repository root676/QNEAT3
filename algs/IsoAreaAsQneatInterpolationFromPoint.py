# -*- coding: utf-8 -*-
"""
***************************************************************************
    IsoAreaAsQneatInterpolationPoint.py
    ---------------------
    
    Partially based on QGIS3 network analysis algorithms. 
    Copyright 2016 Alexander Bruy    
    
    Date                 : July 2018
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

__author__ = 'Clemens Raffler'
__date__ = 'February 2018'
__copyright__ = '(C) 2018, Clemens Raffler'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
from collections import OrderedDict

import osgeo.gdal as gdal
from osgeo import osr

from numpy import array, meshgrid, linspace, zeros

from qgis.PyQt.QtGui import QIcon

from qgis.core import (QgsFeatureSink,
                       QgsFeatureRequest,
                       QgsSpatialIndex,
                       QgsPointXY,
                       QgsVectorLayer,
                       QgsProcessing,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterPoint,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterDefinition)

from qgis.analysis import QgsVectorLayerDirector

from QNEAT3.Qneat3Framework import Qneat3Network, Qneat3AnalysisPoint
from QNEAT3.Qneat3Utilities import getFeatureFromPointParameter, getFeaturesFromQgsIterable

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class IsoAreaAsQneatInterpolationFromPoint(QgisAlgorithm):

    INPUT = 'INPUT'
    START_POINT = 'START_POINT'
    MAX_DIST = "MAX_DIST"
    CELL_SIZE = "CELL_SIZE"
    STRATEGY = 'STRATEGY'
    METHOD = 'METHOD'
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

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_interpolation.png'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'isoareaasqneatinterpolationfrompoint'

    def displayName(self):
        return self.tr('Iso-Area as Qneat-Interpolation (from Point)')

    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements iso-area analysis to return the <b>network-distance interpolation for a maximum cost level</b> on a given <b>network dataset for a manually chosen point</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>) and increments the iso-areas cost regarding to distance/default speed value. Distances are measured accounting for <b>ellipsoids</b>.<br>Please, <b>only use a projected coordinate system (eg. no WGS84)</b> for this kind of analysis.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following Parameters must be set to run the algorithm:"\
                "<ul><li>Network Layer</li><li>Startpoint</li><li>Maximum cost level for Iso-Area</li><li>Cellsize in Meters (increase default when analyzing larger networks)</li><li>Cost Strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction Field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed Field</li><li>Default Speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is one layer:"\
                "<ul><li>TIN-Interpolation Distance Raster</li></ul>"
    
    def msg(self, var):
        return "Type:"+str(type(var))+" repr: "+var.__str__()

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest Path (distance optimization)'),
                           self.tr('Fastest Path (time optimization)')
                           ]
        
        self.METHODS = [self.tr('QGIS TIN-Interpolation (faster but not exact)'),
                        self.tr('QNEAT-Interpolation (slower but more exact')
                        ]

        self.ENTRY_COST_CALCULATION_METHODS = [self.tr('Planar (only use with projected CRS)')]
            

        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Network Layer'),
                                                              [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterPoint(self.START_POINT,
                                                      self.tr('Start point')))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_DIST,
                                                   self.tr('Size of Iso-Area (distance or time value)'),
                                                   QgsProcessingParameterNumber.Double,
                                                   2500.0, False, 0, 99999999.99))
        self.addParameter(QgsProcessingParameterNumber(self.CELL_SIZE,
                                                    self.tr('Cellsize of interpolation raster'),
                                                    QgsProcessingParameterNumber.Integer,
                                                    10, False, 1, 99999999))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Optimization Criterion'),
                                                     self.STRATEGIES,
                                                     defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(self.METHOD,
                                                     self.tr('Interpolation Method'),
                                                     self.METHODS,
                                                     defaultValue=1))

        params = []
        params.append(QgsProcessingParameterEnum(self.ENTRY_COST_CALCULATION_METHOD,
                                                 self.tr('Entry Cost calculation method'),
                                                 self.ENTRY_COST_CALCULATION_METHODS,
                                                 defaultValue=0))
        params.append(QgsProcessingParameterField(self.DIRECTION_FIELD,
                                                  self.tr('Direction field'),
                                                  None,
                                                  self.INPUT,
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
                                                  self.INPUT,
                                                  optional=True))
        params.append(QgsProcessingParameterNumber(self.DEFAULT_SPEED,
                                                   self.tr('Default speed (km/h)'),
                                                   QgsProcessingParameterNumber.Double,
                                                   5.0, False, 0, 99999999.99))
        params.append(QgsProcessingParameterNumber(self.TOLERANCE,
                                                   self.tr('Topology tolerance'),
                                                   QgsProcessingParameterNumber.Double,
                                                   0.0, False, 0, 99999999.99))

        for p in params:
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)
        
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, self.tr('Output Interpolation')))

    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushInfo(self.tr("[QNEAT3Algorithm] This is a QNEAT3 Algorithm: '{}'".format(self.displayName())))
        network = self.parameterAsSource(parameters, self.INPUT, context) #QgsProcessingFeatureSource
        startPoint = self.parameterAsPoint(parameters, self.START_POINT, context, network.sourceCrs()) #QgsPointXY
        max_dist = self.parameterAsDouble(parameters, self.MAX_DIST, context)#float
        cell_size = self.parameterAsInt(parameters, self.CELL_SIZE, context)#int
        strategy = self.parameterAsEnum(parameters, self.STRATEGY, context) #int
        interpolation_method = self.parameterasEnum(parameters, self.METHOD, context)#int

        entry_cost_calc_method = self.parameterAsEnum(parameters, self.ENTRY_COST_CALCULATION_METHOD, context) #int
        directionFieldName = self.parameterAsString(parameters, self.DIRECTION_FIELD, context) #str (empty if no field given)
        forwardValue = self.parameterAsString(parameters, self.VALUE_FORWARD, context) #str
        backwardValue = self.parameterAsString(parameters, self.VALUE_BACKWARD, context) #str
        bothValue = self.parameterAsString(parameters, self.VALUE_BOTH, context) #str
        defaultDirection = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) #int
        speedFieldName = self.parameterAsString(parameters, self.SPEED_FIELD, context) #str
        defaultSpeed = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) #float
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context) #float
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        analysisCrs = network.sourceCrs()
        input_coordinates = [startPoint]
        input_point = getFeatureFromPointParameter(startPoint)
        
        feedback.pushInfo("[QNEAT3Algorithm] Building Graph...")
        feedback.setProgress(10)  
        net = Qneat3Network(network, input_coordinates, strategy, directionFieldName, forwardValue, backwardValue, bothValue, defaultDirection, analysisCrs, speedFieldName, defaultSpeed, tolerance, feedback)
        feedback.setProgress(40)
        
        analysis_point = Qneat3AnalysisPoint("point", input_point, "point_id", net, net.list_tiedPoints[0], entry_cost_calc_method, feedback)
        
        feedback.pushInfo("[QNEAT3Algorithm] Calculating Iso-Pointcloud...")
        iso_pointcloud = net.calcIsoPoints([analysis_point], max_dist)
        feedback.setProgress(70)
        
        uri = "Point?crs={}&field=vertex_id:int(254)&field=cost:double(254,7)&field=origin_point_id:string(254)&index=yes".format(analysisCrs.authid())
        
        iso_pointcloud_layer = QgsVectorLayer(uri, "iso_pointcloud_layer", "memory")
        iso_pointcloud_provider = iso_pointcloud_layer.dataProvider()
        iso_pointcloud_provider.addFeatures(iso_pointcloud, QgsFeatureSink.FastInsert)
        
        feedback.pushInfo("[QNEAT3Algorithm] Calculating Iso-Interpolation-Raster using QGIS TIN-Interpolator...")
        if interpolation_method == 0:
            feedback.pushInfo("[QNEAT3Algorithm] Calculating Iso-Interpolation-Raster using QGIS TIN-Interpolator...")
            net.calcIsoTinInterpolation(iso_pointcloud_layer, cell_size, output_path)
            feedback.setProgress(99)
        else:

            #implement spatial index for lines (closest line, etc...)
            spt_idx = QgsSpatialIndex(iso_pointcloud_layer.getFeatures(QgsFeatureRequest()), self.feedback)
            
            #prepare numpy coordinate grids
            NoData_value = -9999
            raster_rectangle = iso_pointcloud_layer.extent()
            
            #top left point
            xmin = raster_rectangle.xMinimum()
            ymin = raster_rectangle.yMinimum()
            xmax = raster_rectangle.xMaximum()
            ymax = raster_rectangle.yMaximum()
            
            cols = int((xmax - xmin) / cell_size)
            rows = int((ymax - ymin) / cell_size)
            
            output_interpolation_raster = gdal.GetDriverByName('GTiff').Create(output_path, cols, rows, 1, gdal.GDT_Float64 )
            output_interpolation_raster.SetGeoTransform((xmin, cell_size, 0, ymax, 0, -cell_size))
            
            band = output_interpolation_raster.GetRasterBand(1)
            band.SetNoDataValue(NoData_value)
            
            #initialize zero array with 2 dimensions (according to rows and cols)
            raster_routingcost_data = zeros(shape=(rows, cols))
            
            #compute raster cell MIDpoints
            x_pos = linspace(xmin+(cell_size/2), xmax -(cell_size/2), raster_routingcost_data.shape[1])
            y_pos = linspace(ymax-(cell_size/2), ymin + (cell_size/2), raster_routingcost_data.shape[0])
            x_grid, y_grid = meshgrid(x_pos, y_pos) 
            
            gridpoint_list = array(list(zip(x_grid.flatten(),y_grid.flatten())))
    
            list_cellpoints_interpolation = [QgsPointXY(coords[0],coords[1]) for coords in gridpoint_list]
            list_cellpoints_interpolation.insert(0, startPoint)
            
            iso_net = Qneat3Network(network, list_cellpoints_interpolation, strategy, directionFieldName, forwardValue, backwardValue, bothValue, defaultDirection, analysisCrs, speedFieldName, defaultSpeed, tolerance, feedback)
            
            iso_analysis_start_point = Qneat3AnalysisPoint("point", input_point, "point_id", iso_net, iso_net.list_tiedPoints[0], entry_cost_calc_method, feedback)
            
            #add 1 because of iso_analysis_start_point that is prepended
            list_to_apoints = [Qneat3AnalysisPoint("to", feature, "vertex_id", iso_net, iso_net.list_tiedPoints[1+i], entry_cost_calc_method, feedback) for i, feature in enumerate(getFeaturesFromQgsIterable(iso_pointcloud_layer))]
            
            total_workload = float(len(list_to_apoints))
            current_point_index = 0
            #raster data indices
            
            
            dijkstra_query = net.calcDijkstra(iso_analysis_start_point.network_vertex_id, 0)
            i = 0
            while i < len(raster_routingcost_data):
                j = 0
                while j < len(raster_routingcost_data[i]):
                    if (current_point_index%1000)==0:
                        feedback.pushInfo("[QNEAT3Algorithm] {} cells interpolated...".format(current_point_index))
                    if dijkstra_query[0][list_to_apoints[current_point_index].network_vertex_id] == -1:
                        #write nodata to raster
                        raster_routingcost_data[i][j] = -9999
                    else:
                        network_cost = dijkstra_query[1][list_to_apoints[current_point_index].network_vertex_id]
                        raster_routingcost_data[i][j] = iso_analysis_start_point.entry_cost + network_cost + list_to_apoints[current_point_index].entry_cost 
                    current_point_index = current_point_index + 1
                    feedback.setProgress((current_point_index/total_workload)*100)
                    j=j+1
                i=i+1
                    
            band.WriteArray(raster_routingcost_data)
            outRasterSRS = osr.SpatialReference()
            outRasterSRS.ImportFromWkt(self.AnalysisCrs.toWkt())
            output_interpolation_raster.SetProjection(outRasterSRS.ExportToWkt())
            band.FlushCache()

        
        feedback.pushInfo("[QNEAT3Algorithm] Ending Algorithm")
        feedback.setProgress(100)           
        
        results = {}
        results[self.OUTPUT] = output_path
        return results