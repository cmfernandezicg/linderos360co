def classFactory(iface):
    from .linderos_plugin import LinderosPlugin
    return LinderosPlugin(iface)
