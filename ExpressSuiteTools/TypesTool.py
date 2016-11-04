"""
Portal Types tool
$Id: TypesTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 02/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from string import lower
from types import StringType

from Acquisition import aq_base, aq_parent, aq_inner
from AccessControl import ClassSecurityInfo, getSecurityManager
from Interface.Implements import instancesOfObjectImplements

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import getToolByName, _checkPermission
from Products.CMFCore.TypesTool import TypesTool as _TypesTool, typeClasses, \
     TypeInformation, FactoryTypeInformation as _FactoryTypeInformation
from Products.CMFCore.exceptions import AccessControl_Unauthorized

from ActionsTool import createExprContext
from SimpleObjects import InstanceBase, ToolBase

from Utils import InitializeClass, getClassByMetaType

from logging import getLogger
logger = getLogger( 'TypesTool' )


class TypesTool( ToolBase, _TypesTool ):
    """
        Portal types tool
    """
    _class_version = 1.01

    meta_type = 'ExpressSuite Types Tool'

    security = ClassSecurityInfo()

    manage_options = _TypesTool.manage_options # + ToolBase.manage_options

    _actions = _TypesTool._actions + ToolBase._actions

    _default_factory_form = 'invoke_factory_form'

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not ToolBase._initstate( self, mode ):
            return 0

        if getattr( self, '_groups', None ) is None:
            self._groups = {}

        if mode > 1:
            for tname, tinfo in self.objectItems():
                if getattr( aq_base( tinfo ), '_isTypeInformation', None ):
                    self._upgrade( tname, FactoryTypeInformation )

        return 1

    ### Override TypesTool interface methods ###

    #security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'listTypeInfo' )
    #def listTypeInfo( self, container=None, groups=0 ):
    #    """ Returns a sequence of TypeInformation instances """
    #    types = _TypesTool.listTypeInfo( self, container )
    #    if groups:
    #        types = filter( lambda ti: not ti.type_group, types )
    #    else:
    #        types = filter( lambda ti: ti.type_group is not None, types )
    #    return types

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'listSortedTypeInfo' )
    def listSortedTypeInfo( self, searchable=None ):
        """
            Returns sorted type information
        """
        type_items = self.listTypeInfo()
        msg = getToolByName( self, 'msg', None )

        ids = ( 'HTMLDocument', 'HTMLCard', 'Registry', 'Task Item', 'Discussion Item', 'Heading', \
                'Search Profile', 'Shortcut', 'Fax Incoming Folder', \
                'FS Folder', 'FS File', \
                ) # 'Incoming Mail Folder','Outgoing Mail Folder',
        res = [ ( msg(x.Title()), x.getId() ) for x in type_items if not searchable or x.getId() in ids ]

        res.append( ( msg('File Attachment'), 'File Attachment' ) )
        res.append( ( msg('Image Attachment'), 'Image Attachment' ) )
        res.sort()

        res = [ id for name, id in res ]
        return res

    def getObjectTitle( self, ob ):
        """
            Returns customized heading titles
        """
        if ob is None: return '---'

        title = ob.Title()
        if ob.meta_type in ['Heading']:
            id = ob.getId()
            if id in ['NOTE','PR','NDOC','OUT','TOSIGN']:
                folder = aq_parent(aq_inner(ob))
                title = folder and folder.Title() or title

        return title

    # TODO: this is a fixed version from CMF 1.3-release
    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'listContentTypes' )
    def listContentTypes( self, container=None, by_metatype=0 ):
        """
            Return list of content types
        """
        typenames = {}
        for t in self.listTypeInfo( container ):
            if by_metatype:
                name = t.Metatype()
            else:
                name = t.getId()
            if name:
                typenames[ name ] = None

        result = typenames.keys()
        result.sort()
        return result

    ### New interface methods ###

    def addType( self, id, info ):
        """
            Adds new type
        """
        if not getattr( aq_base(info), '_isTypeInformation', 0 ):
            if info.has_key('content_meta_type') or info.has_key('meta_type'):
                klass = FactoryTypeInformation
                group = info.get('type_group')
            else:
                klass = TypeGroupInformation
                group = None
            if group:
                group = self._getOb( group, None )
            info = klass( group=group, **info )

        self._setObject( id, info )
        return self._getOb( id )

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'listTypeGroups' )
    def listTypeGroups( self ):
        """
            Return a sequence of TypeGroupInformation instances
        """
        return filter( lambda ob: getattr( aq_base(ob), '_isTypeGroup', 0 ), self.objectValues() )

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'getDefaultFactoryForm' )
    def getDefaultFactoryForm( self ):
        """
            Returns a default form used to create a new object instance
        """
        return self._default_factory_form

InitializeClass( TypesTool )


class TypeGroupInformation( InstanceBase, TypeInformation ):
    """ Portal content factory """
    _class_version = 1.0

    meta_type = 'Types Group'

    _isTypeGroup = 1

    security = ClassSecurityInfo()

    manage_options = TypeInformation.manage_options + \
                     InstanceBase.manage_options

    _properties = _FactoryTypeInformation._properties + (
        {'id':'disallow_manual', 'type': 'boolean', 'mode':'w',
         'label':'Disallow manual creation?'},
        {'id':'sort_order', 'type': 'float', 'mode':'w',
         'label':'Sort order'},
        )

    ### Default attribute values ###

    disallow_manual = 0
    sort_order = 0.75

    # restore method overriden by ItemBase
    Title = TypeInformation.Title

    def __init__( self, id, factory_form=None, **kw ):
        """
            Initialize class instance
        """
        InstanceBase.__init__( self )
        TypeInformation.__init__( self, id, **kw )

        if factory_form:
            self.factory_form = factory_form

    security.declarePublic('getFactoryForm')
    def getFactoryForm( self ):
        """
            Returns a form used to create a new object instance
        """
        factory_form = getattr(self, 'factory_form', None)
        if factory_form is None:
            types_tool = getToolByName(self, 'portal_types')
            factory_form = types_tool.getDefaultFactoryForm()

        return factory_form

    security.declarePublic( 'typeImplements' )
    def typeImplements( self, feature=None ):
        """
            Checks whether the type implements given interface or feature.
        """
        if feature[0] == '_':
            return 0
        return 1

        # XXX check whether all group members implement the feature
        klass = getClassByMetaType( self.Metatype() )
        for iface in instancesOfObjectImplements( klass ):
            if iface.__name__ == feature:
                return 1

        return 0

    security.declarePublic('isConstructionAllowed')
    def isConstructionAllowed( self, container ):
        """
            Does the current user have the permission required in
            order to construct an instance?
        """
        return 0

    security.declarePublic('disallowManual')
    def disallowManual( self ):
        """
            Should manual creation of objects of this type be disallowed?
        """
        return 1

InitializeClass( TypeGroupInformation )


class FactoryTypeInformation( InstanceBase, _FactoryTypeInformation ):
    """ Portal content factory """
    _class_version = 1.0

    meta_type = 'ExpressSuite Factory-based Type Information'

    security = ClassSecurityInfo()

    manage_options = _FactoryTypeInformation.manage_options + \
                     InstanceBase.manage_options

    _properties = TypeGroupInformation._properties + (
        {'id':'type_group', 'type': 'string', 'mode':'w',
         'label':'Types group name'},
        {'id':'permissions', 'type': 'lines', 'mode':'w',
         'label':'Required permissions'},
        {'id':'condition', 'type': 'string', 'mode':'w',
         'label':'Required condition'},
        )

    ### Default attribute values ###

    disallow_manual = TypeGroupInformation.disallow_manual
    sort_order = TypeGroupInformation.sort_order
    type_group = ''
    permissions = ()
    condition = ''

    # restore method overriden by ItemBase
    Title = _FactoryTypeInformation.Title

    def __init__( self, id, group=None, condition=None, factory_form=None, **kw ):
        """
            Initialize class instance
        """
        if group:
            for prop, value in group.propertyItems():
                kw.setdefault( prop, value )

        if condition and type( condition ) == type( '' ):
            self.condition = Expression( condition )
        elif condition:
            self.condition = condition

        if factory_form:
            self.factory_form = factory_form

        InstanceBase.__init__( self )
        _FactoryTypeInformation.__init__( self, id, **kw )

        for action in self._actions:
            try:
                condition = action.get('condition', None)
                if type( condition ) is StringType:
                    action['condition'] = Expression( condition )
            except: pass

    ### Override FactoryTypeInformation interface methods ###
    #
    #   Agent methods
    #
    security.declarePublic('isConstructionAllowed')
    def isConstructionAllowed( self, container ):
        """
            Does the current user have the permission required in
            order to construct an instance?
        """
        #logger.info('FactoryTypeInformation title: %s' % self.title)
        if self.permissions:
            allowed = 0
            for perm in self.permissions:
                if _checkPermission( perm, container ):
                    allowed = 1
                    break
            if not allowed:
                return 0

        if self.condition:
            #logger.info("FactoryTypeInformation condition: %s" % self.condition)
            if container is None or not hasattr(container, 'aq_base'):
                #we can not get portal and folder
                #so we can not test condition
                #FIX!!!
                #logger.info('FactoryTypeInformation container is None: %s'% `container`)
                pass

            portal = container.getPortalObject()

            folder = container
            # Search up the containment hierarchy until we find an
            # object that claims it's a folder.
            while folder is not None:
                if getattr(aq_base(folder), 'isPrincipiaFolderish', 0):
                    # found it.
                    break
                else:
                    folder = aq_parent(aq_inner(folder))
            container_url = container is not None and container.absolute_url() or ''
            ec = createExprContext( folder, portal, container, url=container_url )
            if self.condition and not self.condition(ec):
                #logger.info('FactoryTypeInformation condition() is false')
                return 0
            #logger.info('FactoryTypeInformation condition() is true')

        return _FactoryTypeInformation.isConstructionAllowed( self, container )

    security.declarePublic('allowType')
    def allowType( self, contentType ):
        """
            Can objects of 'contentType' be added to containers whose type object we are?
        """
        tinfo = self.getTypeInfo( contentType )
        if tinfo is not None and tinfo.globalAllow() and tinfo.disallowManual():
            return 0

        # workaround for the bug in the 'list' converter
        if type(self.allowed_content_types) is StringType:
            del self.allowed_content_types

        return _FactoryTypeInformation.allowType( self, contentType )

    ### New interface methods ###

    security.declarePublic('disallowManual')
    def disallowManual( self ):
        """
            Should manual creation of objects of this type be disallowed?
        """
        return getattr( self, 'disallow_manual', None )

    security.declarePublic('getFactoryForm')
    def getFactoryForm( self ):
        """
            Returns a form used to create a new object instance
        """
        factory_form = getattr(self, 'factory_form', None)
        if factory_form is None:
            types_tool = getToolByName(self, 'portal_types')
            factory_form = types_tool.getDefaultFactoryForm()

        return factory_form

    security.declarePublic( 'typeImplements' )
    def typeImplements( self, feature=None ):
        """
            Checks whether the type implements given interface or feature.
        """
        if feature[0] == '_':
            return 0

        klass = getClassByMetaType( self.Metatype() )
        for iface in instancesOfObjectImplements( klass ):
            if iface.__name__ == feature:
                return 1

        return 0

InitializeClass( FactoryTypeInformation )


def registerTypeFactory( klass, action ):
    name = klass.meta_type

    for item in typeClasses[:]:
        if item['name'] == name:
            typeClasses.remove( item )

    typeClasses.append( {
            'class'      : klass,
            'name'       : name,
            'action'     : action,
            'permission' : CMFCorePermissions.ManagePortal,
        } )

registerTypeFactory( FactoryTypeInformation, 'manage_addFactoryTIForm' )
registerTypeFactory( TypeGroupInformation, 'manage_addFactoryTIForm' )
