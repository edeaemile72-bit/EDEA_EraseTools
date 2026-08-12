# -*- coding: utf-8 -*-
"""Plugin QGIS : EDEA_EraseTools v6.0"""

def classFactory(iface):
    from .edea_erasetools import EdeaEraseToolsPlugin
    return EdeaEraseToolsPlugin(iface)
