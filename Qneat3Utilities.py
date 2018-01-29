"""
***************************************************************************
    Qneat3Utilities.py
    ---------------------
    Date                 : November 2017
    Copyright            : (C) 2017 by Clemens Raffler
    Email                : clemens dot raffler at gmail dot com
***************************************************************************
"""
from qgis.core import *
from qgis.analysis import *

from PyQt5.QtCore import QVariant

def AssignAnalysisCrs(vlayer):
    logPanel("Setting analysis CRS")
    AnalysisCrs = vlayer.crs()
    return AnalysisCrs

def logPanel(message):
    QgsMessageLog.logMessage(message, "QNEAT3")
    
def isGeometryType(vlayer, type_obj):
    geom_type = vlayer.geometryType()
    if geom_type == type_obj:
        return True
    else:
        return False

def buildQgsVectorLayer(string_geomtype, string_layername, crs, list_geometry, list_qgsfield):
    
    #create new vector layer from self.crs
    vector_layer = QgsVectorLayer(string_geomtype, string_layername, "memory")
    
    #set crs from class
    vector_layer.setCrs(crs)
    
    #set fields
    provider = vector_layer.dataProvider()
    provider.addAttributes(list_qgsfield) #[QgsField('fid',QVariant.Int),QgsField("origin_point_id", QVariant.Double),QgsField("iso", QVariant.Int)]
    vector_layer.updateFields()
    
    #fill layer with geom and attrs
    vector_layer.startEditing()
    for i, geometry in enumerate(list_geometry):
        feat = QgsFeature()
        feat.setGeometry(geometry)#geometry from point
        feat.setAttributes(list_qgsfield[i])
        vector_layer.addFeature(feat, True)
    vector_layer.commitChanges()

    return vector_layer


def getFeaturesFromLayer(vlayer):
    fRequest = QgsFeatureRequest().setFilterFids(vlayer.allFeatureIds())
    return vlayer.getFeatures(fRequest)

def getFieldIndexFromQgsProcessingFeatureSource(feature_source, field_name):
    if field_name != "":
        return feature_source.fields().lookupField(field_name)
    else:
        return -1

def getListOfPoints(vlayer):
    fRequest = QgsFeatureRequest().setFilterFids(vlayer.allFeatureIds())
    features = vlayer.getFeatures(fRequest)
    return [f.geometry().asPoint() for f in features]

def getLayerGeometryType(vlayer):
    wkbType = vlayer.wkbType()
    try:
        if wkbType in (QGis.WKBPoint, QGis.WKBMultiPoint,
                       QGis.WKBPoint25D, QGis.WKBMultiPoint25D):
            return QGis.WKBPoint
        elif wkbType in (QGis.WKBLineString, QGis.WKBMultiLineString,
                         QGis.WKBMultiLineString25D,
                         QGis.WKBLineString25D):

            return QGis.WKBLineString
        elif wkbType in (QGis.WKBPolygon, QGis.WKBMultiPolygon,
                         QGis.WKBMultiPolygon25D, QGis.WKBPolygon25D):

            return QGis.WKBPolygon
        else:
            return QGis.WKBUnknown
    except:
        return None

def extractGeometryAsSingle(geom): #must be called per multigeometry object
    multiGeom = QgsGeometry()
    list_singleGeometries = []
    if geom.type() == QGis.Point:
        if geom.isMultipart():
            multiGeom = geom.asMultiPoint()
            for i in multiGeom:
                list_singleGeometries.append(QgsGeometry().fromPoint(i))
        else:
            list_singleGeometries.append(geom)
    elif geom.type() == QGis.Line:
        if geom.isMultipart():
            multiGeom = geom.asMultiPolyline()
            for i in multiGeom:
                list_singleGeometries.append(QgsGeometry().fromPolyline(i))
        else:
            list_singleGeometries.append(geom)
    elif geom.type() == QGis.Polygon:
        if geom.isMultipart():
            multiGeom = geom.asMultiPolygon()
            for i in multiGeom:
                list_singleGeometries.append(QgsGeometry().fromPolygon(i))
        else:
            list_singleGeometries.append(geom)
    return list_singleGeometries

def getMultiGeometryAsList(vlayer):
    list_geometry = [feature.geometry() for feature in vlayer]
    return list_geometry


def getSingleGeometryAsList(vlayer):
    list_multigeom = getMultiGeometryAsList(vlayer)
    list_singlegeom = []
    for geom in list_multigeom:
        extracted_geom = extractGeometryAsSingle(geom)
        list_singlegeom.extend(extracted_geom)
    return list_singlegeom


