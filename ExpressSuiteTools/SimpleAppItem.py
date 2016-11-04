"""
Basic AppItem classes
$Id: SimpleAppItem.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 04/03/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from AccessControl import ClassSecurityInfo
from AccessControl import Permissions as ZopePermissions
from Acquisition import aq_parent
#from Record import Record

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName

import Config, Features
from Config import Roles, Permissions
from ContentCategory import ContentCategory

from SimpleObjects import ContentBase
from Utils import InitializeClass, joinpath


class SimpleAppItem( ContentBase, ContentCategory ):
    """
        Abstract base class for App content objects
    """
    _class_version = 1.0

    __implements__ = ( ContentCategory.__implements__, Features.isPortalContent, )

    security = ClassSecurityInfo()

    def getStateStyle( self ):
        workflow = getToolByName( self, 'portal_workflow', None )
        if workflow is None:
            return ''
        state = workflow.getInfoFor( self, 'state', '' )
        if state:
            style = '%s_%s' % (self.meta_type.replace(' ', '_'), state )
        else:
            style = self.meta_type.replace(' ', '_')
        return style
    """
    #
    # External site interaction methods =============================================================================
    #
    security.declareProtected( ZopePermissions.access_contents_information, 'getSite' )
    def getSite( self ):
        # Returns parent Site object or None
        try:
            return self.getSiteObject()
        except AttributeError:
            return None

    security.declareProtected( ZopePermissions.access_contents_information, 'getSubscription' )
    def getSubscription( self ):
        # Returns parent Subscription object or None
        try:
            return self.getSubscriptionObject()
        except AttributeError:
            return None

    security.declarePublic( 'external_url' )
    def external_url( self, relative=0, **kw ):
        # Returns URL for this object on the external site
        site = self.getSite()
        if site is None:
            return None

        url = self.absolute_url( 1, **kw )
        top = site.getSiteStorage().absolute_url( 1 )
        root = site.getExternalRootUrl( relative=relative )

        return joinpath( root, 'go', url[ len(top): ] )
    #
    # Site presentation interface methods ===========================================================================
    #
    def isPublished( self ):
        # Check whether document is published on the external site
        if not self.getSite():
            return None

        workflow = getToolByName( self, 'portal_workflow', None )
        if workflow is None:
            return None

        return workflow.getStateFor( self ) == 'published'

    security.declareProtected( Permissions.PublishPortalContent, 'setIndexDocument' )
    def setIndexDocument( self, flag=1 ):
        # Set mark on the document, that it must be used as index page for topic on external site
        topic = aq_parent( self )
        flag = not not flag
        topic.setMainPage( flag and self or None )

    security.declarePublic( 'isIndexDocument' )
    def isIndexDocument( self ):
        # Check whether the document is an index page fot its topic
        topic = aq_parent( self )

        main_page = topic.getMainPage()
        if not main_page:
            return None

        return main_page.getUid() == self.getUid()

    security.declareProtected( Permissions.PublishPortalContent, 'setPresentationLevel' )
    def setPresentationLevel( self, level=None ):
        # Set news level of the document
        site = self.getSite()
        if site:
            site.setPresentationLevel( self, level )

    security.declarePublic( 'getPresentationLevel' )
    def getPresentationLevel( self ):
        # Get the way document is displayed on the external site
        site = self.getSite()
        if not site:
            return None
        return site.getPresentationLevel( self )

    def _remote_transfer( self, context=None, container=None, server=None, path=None, id=None, parents=None, recursive=None ):
        # Transfer local object to remote server
        remote = ContentCategory._remote_transfer( self, context, container, server, path, id, parents, recursive )
        ContentBase._remote_onTransfer(self, remote)
        return remote
    """

InitializeClass( SimpleAppItem )


class ObjectBrains:
    """
        Abstract class like catalog mybrains
    """
    __allow_access_to_unprotected_subobjects__ = 1

    def __init__( self, ob, REQUEST=None ):
        self.__data = { 'path'   : ob.physical_path(),
                        'URL'    : ob.absolute_url(),
                        'Title'  : ob.Title(),
                        'state'  : ob.implements('isDocument') and ob.getWorkflowState() or None,
                      '__roles__': ( Roles.Anonymous, ),
                      }
        #ob.manage_permission( CMFCorePermissions.View, ( Roles.Anonymous, ), 0 )
        self.__ob = ob

    def __getattr__( self, name ):
        if self.__data.has_key(name):
            return self.__data[name]
        return getattr(self.__ob, name, None)

    def has_key( self, key ):
        return self.__data.has_key(key)

    def getPath( self ):
        """ Get the physical path for this record """
        return self.__data['path']

    def getURL( self, relative=0 ):
        """ Try to generate a URL for this record """
        return self.__data['URL']

    def getObject( self, REQUEST=None ):
        """ Try to return the object for this record """
        return self.__ob

    def getRID( self ):
        return None
