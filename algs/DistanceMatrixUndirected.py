import os
from qgis.core import QgsProcessing, QgsWkbTypes, QgsProcessingParameterNumber
from PyQt5.QtGui import QIcon

from processing.algs.qgis.QgisAlgorithm import QgisFeatureBasedAlgorithm

from QNEAT3.QneatFramework import *

pluginPath = os.path.split(os.path.dirname(__file__))[0]

class DistanceMatrixUndirected(QgisFeatureBasedAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'
    PERCENTAGE = 'PERCENTAGE'
    SEGMENTS = 'SEGMENTS'

    def __init__(self):
        super().__init__()
        self.percentage = None
        self.segments = None

    def name(self):
        return 'undirected_od_matrix_as_table'

    def displayName(self, *args, **kwargs):
        return 'Undirected OD-Matrix as table'

    def shortHelpString(self):
        return 'Given an input polygon layer and a percentage value, this ' \
               'algorithm creates a buffer area for each feature so that the ' \
               'area of the buffered feature is the specified percentage of ' \
               'the area of the input feature.\n' \
               'For example, when specifying a percentage value of 200 %, ' \
               'the buffered features would have twice the area of the input ' \
               'features. For a percentage value of 50 %, the buffered ' \
               'features would have half the area of the input features.\n' \
               'The segments parameter controls the number of line segments ' \
               'to use to approximate a quarter circle when creating rounded ' \
               'offsets.'

    def group(self):
        return self.tr('OD-Matrix')

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'algs', 'icon_matrix.svg'))

    def inputLayerTypes(self):
        return [QgsProcessing.TypeVectorPolygon]

    def outputName(self):
        return self.tr('Undirected_OD_Matrix')

    def outputType(self):
        return QgsProcessing.TypeVectorPolygon

    def outputWkbType(self, input_wkb_type):
        return QgsWkbTypes.Polygon

    def initParameters(self, config=None):
        self.addParameter(QgsProcessingParameterNumber(self.PERCENTAGE,
                                                       self.tr('Percentage'),
                                                       type=QgsProcessingParameterNumber.Double,
                                                       defaultValue=100.0))
        self.addParameter(QgsProcessingParameterNumber(self.SEGMENTS,
                                                       self.tr('Segments'),
                                                       type=QgsProcessingParameterNumber.Integer,
                                                       minValue=1,
                                                       defaultValue=5))

    def prepareAlgorithm(self, parameters, context, feedback):
        self.percentage = self.parameterAsDouble(parameters, self.PERCENTAGE,
                                                 context)
        self.segments = self.parameterAsInt(parameters, self.SEGMENTS, context)

        return True

    def processFeature(self, feature, context, feedback):
        input_geometry = feature.geometry()
        if input_geometry:
            return feature