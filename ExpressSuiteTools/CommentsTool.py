"""
Comments tool
$Id: CommentsTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 10/12/2007 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import StringType, ListType, TupleType

from AccessControl import ClassSecurityInfo
from Acquisition import aq_base
from BTrees.OOBTree import OOBTree, OOSet
from OFS.SimpleItem import SimpleItem

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import _checkPermission, _getAuthenticatedUser

import Config
from SimpleObjects import InstanceBase, ToolBase, ContainerBase
from Utils import InitializeClass, cookId, get_param

from logging import getLogger
logger = getLogger( 'CommentsTool' )


class CommentTemplate( InstanceBase ):
    """
        Comment template
    """
    _class_version = 1.0

    meta_type = 'Comment Template'

    security = ClassSecurityInfo()

    _properties = InstanceBase._properties + (
            {'id':'description',       'type':'string',        'mode':'w'},
        )

    def __init__( self, id, title, description ):
        """
            Initialize class instance
        """
        InstanceBase.__init__( self, id, title )
        self.description = description
        self.interval = None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'edit' )
    def edit( self, REQUEST=None, **kw ):
        """
            Edit attributes
        """
        title = get_param( 'title', REQUEST, kw, None )
        if title:
            self.title = title
        description = get_param( 'description', REQUEST, kw, None )
        if description:
            self.description = description
        interval = get_param( 'interval', REQUEST, kw, None )
        if interval:
            self.interval = interval

    def Description( self ):
        """
            Returns comment description
        """
        return self.description or ''

InitializeClass( CommentTemplate )


class CommentsTool( ToolBase, SimpleItem, ContainerBase ):
    """
        Portal comments
    """
    _class_version = 1.0

    id = 'portal_comments'
    meta_type = 'ExpressSuite Comments Tool'

    manage_options = ToolBase.manage_options + \
                     ContainerBase.manage_options[:-1] # exclude 'Properties'

    _actions = (
         ActionInformation( id='manageComments'
                 , title='Manage resolutions'
                 , description='Manage document resolutions'
                 , action=Expression( text='string: ${portal_url}/manage_comments_form' )
                 , permissions=( CMFCorePermissions.ManagePortal, )
                 , category='global'
                 , condition=None
                 , visible=1
                 ),
        ) + ToolBase._actions

    security = ClassSecurityInfo()

    def __init__( self ):
        """
            Initialize class instance
        """
        ToolBase.__init__( self )
        self._contexts = OOBTree()

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not ToolBase._initstate( self, mode ):
            return 0

        if mode > 1 and getattr( self, '_contexts', None ) is None:
            self._contexts = OOBTree()

        return 1

    security.declareProtected( CMFCorePermissions.ManagePortal, 'addContext' )
    def addContext( self, context ):
        """
            Add new context
        """
        if not context:
            raise
        try:
            comments = self._contexts.get( context ) or None
            if comments is not None:
                return comments
        except:
            pass
        comments = self._contexts[ context ] = OOSet()
        return comments

    security.declareProtected( CMFCorePermissions.ManagePortal, 'delContext' )
    def delContext( self, context ):
        """
            Remove context
        """
        if not context:
            raise
        if len(self._contexts[ context ]) > 0:
            return
        try: del self._contexts[ context ]
        except: pass

    security.declareProtected( CMFCorePermissions.ManagePortal, 'addComment' )
    def addComment( self, context=None, id=None, title=None, description=None, REQUEST=None, **kw ):
        """
            Add a comment
        """
        if not id:
            id = cookId( self, prefix='comment' )

        self._setObject( id, CommentTemplate( id, title, description ), set_owner=0 )

        context = context or 'global'
        comments = self.addContext( context )
        comments.insert( id )

        ob = self._getOb( id )
        ob.edit( REQUEST, **kw )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'editComment' )
    def editComment( self, id, REQUEST=None, **kw ):
        """
            Edit comment
        """
        save_id = get_param( 'save_id', REQUEST, kw, None )
        logger.info('editComment id %s, save_id %s' % ( id, save_id )) 
        try: ob = self._getOb( id )
        except: ob = self._getOb( save_id )
        
        if ob is None:
            raise KeyError, 'comment object is None, id [%s], save_id [%s]' % ( id, save_id )

        if id != save_id:
            self.deleteComment( save_id )
            setattr( ob, 'id', id )
            self._setObject( id, ob, set_owner=0 )

        ob.edit( REQUEST, **kw )

        context = get_param( 'context_type', REQUEST, kw, None )
        object_context = self._getObjectContext( id )
        logger.info('editComment new_context %s, old_context %s' % ( context, object_context ))

        if object_context != context:
            if object_context is not None:
                self._contexts[ object_context ].remove( id )
                if len(self._contexts[ object_context ]) == 0:
                    self.delContext( object_context )
            comments = self.addContext( context )
            if id not in comments: 
                comments.insert( id )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'deleteComment' )
    def deleteComment( self, id ):
        """
            Remove comment
        """
        for ids in self._contexts.values():
            try: ids.remove( id )
            except KeyError: pass

        self._delObject( id )

    security.declareProtected( CMFCorePermissions.View, 'listContexts' )
    def listContexts( self, id=None ):
        """
            Returns list of contexts
        """
        if id is None:
            return list( self._contexts.keys() )
        results = []
        for name, comments in self._contexts.items():
            if id in comments:
                results.append( name )
        return results

    security.declareProtected( CMFCorePermissions.View, 'listComments' )
    def listComments( self, context=None, exact=None, sort=None ):
        """
            Returns list of comment for given context id
        """
        if context is None:
            return None

        contexts = self._contexts
        results  = []

        if exact:
            parts = [ context ]
        else:
            parts = context.split('.')
            parts = [ '.'.join( parts[:i] ) for i in range( 1, len(parts)+1 ) ]
            parts.insert( 0, 'global' )

        for part in parts:
            for id in contexts.get( part, [] ):
                results.append( self[ id ] )

        if sort:
            results.sort( lambda x, y: cmp(x.Title(), y.Title()) )

        return results

    def getCommentsTitle( self, ids ):
        """
            Returns comment title
        """
        res = []
        if type(ids) is StringType:
            ids = [ ids ]
        for id in ids:
            try: ob = self._getOb( id )
            except: continue
            if ob is not None:
                res.append( ob.Title() )
        return res

    def _getObjectContext( self, id ):
        """
            Returns object context
        """
        for key in self._contexts.keys():
            ids = self._contexts[ key ]
            if id in ids:
                return key
        return None

InitializeClass( CommentsTool )
