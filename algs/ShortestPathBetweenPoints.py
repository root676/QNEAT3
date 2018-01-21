import os
from qgis.core import QgsProcessing, QgsWkbTypes, QgsProcessingParameterNumber
from PyQt5.QtGui import QIcon

from processing.algs.qgis.QgisAlgorithm import QgisFeatureBasedAlgorithm

from QNEAT3.QneatFramework import *

pluginPath = os.path.split(os.path.dirname(__file__))[0]

class ShortestPathUndirected(QgisAlgorithm):
    
    INPUT = 'INPUT'
    START_POINT = 'START_POINT'
    END_POINT = 'END_POINT'
    STRATEGY = 'STRATEGY'
    DIRECTION_FIELD = 'DIRECTION_FIELD'
    VALUE_FORWARD = 'VALUE_FORWARD'
    VALUE_BACKWARD = 'VALUE_BACKWARD'
    VALUE_BOTH = 'VALUE_BOTH'
    DEFAULT_DIRECTION = 'DEFAULT_DIRECTION'
    SPEED_FIELD = 'SPEED_FIELD'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    TOLERANCE = 'TOLERANCE'
    TRAVEL_COST = 'TRAVEL_COST'
    OUTPUT = 'OUTPUT'

    def __init__(self):
        super().__init__()

    def name(self):
        return 'ShortestPathUndirected'

    def displayName(self, *args, **kwargs):
        return 'Undirected Shortest Path between two points'

    def shortHelpString(self):
        return 'Help for the QNEAT-Shortest Path between Points Algorithm.'

    def group(self):
        return self.tr('Shortest Paths')

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'algs', 'icon_matrix.svg'))

    def inputLayerTypes(self):
        return [QgsProcessing.TypeVectorLine, QgsProcessing.TypeVectorPoint]

    def outputName(self):
        return self.tr('Shortest_Path')

    def outputType(self):
        return QgsProcessing.TypeVectorPolygon

    def outputWkbType(self, input_wkb_type):
        return QgsWkbTypes.MultiLineString

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest'),
                           self.tr('Fastest')
                           ]

        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Vector layer representing network'),
                                                              [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterPoint(self.START_POINT,
                                                      self.tr('Start point')))
        self.addParameter(QgsProcessingParameterPoint(self.END_POINT,
                                                      self.tr('End point')))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Path type to calculate'),
                                                     self.STRATEGIES,
                                                     defaultValue=0))

        params = []
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

        self.addOutput(QgsProcessingOutputNumber(self.TRAVEL_COST,
                                                 self.tr('Travel cost')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,
                                                            self.tr('Shortest path'),
                                                            QgsProcessing.TypeVectorLine))
    def prepareAlgorithm(self, parameters, context, feedback):
        self.percentage = self.parameterAsDouble(parameters, self.PERCENTAGE,
                                                 context)
        self.segments = self.parameterAsInt(parameters, self.SEGMENTS, context)

        return True

    def processFeature(self, feature, context, feedback):
        input_geometry = feature.geometry()
        if input_geometry:
            return feature