"""
HTMLCard class
$Id: HTMLCard.py, v 1.0 2009/05/30 12:00:00 Exp $

*** Checked 13/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
import threading

from AccessControl import ClassSecurityInfo, Permissions as ZopePermissions
from OFS.ObjectManager import ObjectManager

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser, _checkPermission
from Products.CMFDefault.Document import Document

import Config, Features
from Config import Permissions
from ConflictResolution import ResolveConflict
from Features import createFeature
from HTMLDocument import HTMLDocument
from SimpleAppItem import SimpleAppItem
from PortalLogger import portal_log, portal_info, portal_debug, portal_error

from Utils import InitializeClass, getLanguageInfo, getPlainText

SYSTEM_FIELDS = ()

timeout = 3.0
default_content_type = 'text/html'

factory_type_information = ( 
                            { 'id'              : 'HTMLCard'
                            , 'meta_type'       : 'HTMLCard'
                            , 'title'           : 'Record card'
                            , 'description'     : """HTML-card registration pattern"""
                            , 'icon'            : 'card_icon.gif'
                            , 'sort_order'      : 0.41
                            , 'product'         : 'ExpressSuiteTools'
                            , 'factory'         : 'addHTMLCard'
                            , 'immediate_view'  : 'card_edit_form'
                            , 'allow_discussion': 0
                            , 'actions'         :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View'
                                  , 'action'        : 'card_view'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'edit'
                                  , 'name'          : 'Edit'
                                  , 'action'        : 'card_edit_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  , 'condition'     : 'python: object.checkVersionModifyPerm()'
                                  }
                                , { 'id'            : 'metadata'
                                  , 'name'          : 'Metadata'
                                  , 'action'        : 'metadata_edit_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  }
                                , { 'id'            : 'attachments'
                                  , 'name'          : 'Attachments'
                                  , 'action'        : 'document_attaches'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'link'
                                  , 'name'          : 'Links'
                                  , 'action'        : 'document_link_form'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'export_document'
                                  , 'name'          : 'Export document'
                                  , 'action'        : 'export_import_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  }
                                , { 'id'            : 'reply_to_document'
                                  , 'name'          : 'Reply to document'
                                  , 'action'        : 'reply_to_document'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                )
                            }
                           ,
                           )


def addHTMLCard( self, id, title='', description='', text_format='html', text='', attachments=() ):
    """ 
        Add an HTML card (invoke factory constructor).

        Arguments:

            'attachments' -- list of file objects to attach to the card
    """
    o = HTMLCard( id, title, description, text_format, text )

    IsError = 0
    repeat_action = 0
    ob = None
    msg = ''
    n = 0

    while n < 3:
        n += 1
        try:
            self._setObject( id, o )
            ob = self._getOb( id )
            IsError = 0
            break

        except Exception, message:
            IsError = 1
            msg = str(message)
            if not repeat_action:
                break
            portal_error( 'HTMLCard.addHTMLCard', '%s, id: %s' % ( msg, id ), exc_info=True )
            threading.Event().wait( timeout*n )
            continue

    try: path = ob is not None and ob.physical_path() or ''
    except: path = ''

    if not IsError:
        for idx in range( len(attachments) ):
            file = attachments[ idx ]
            params = {}
            if isinstance( file, TupleType ):
                file, params = file

            new_id = ob.addFile( file=file, **params )

        portal_info( 'HTMLCard.addHTMLCard', 'successfully created new card, path: %s' % path )
    else:
        portal_error( 'HTMLCard.addHTMLCard', '%s, id: %s, path: %s' % ( msg or 'exception', id, path ) )

    del o, ob


class HTMLCard( HTMLDocument ):
    """
        Subclassed HTMLDocument type
    """
    _class_version = 1.03

    meta_type = 'HTMLCard'
    portal_type = 'HTMLCard'

    __implements__ = ( createFeature('isHTMLCard'),
                       HTMLDocument.__implements__,
                     )

    security = ClassSecurityInfo()

    def reindex( self ):
        """
            Apply extra (recursive) reindex for this object
        """
        ob = self.getVersionable()
        if ob is None:
            return 'Object is None!'
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is not None:
            catalog.reindexObject(ob, recursive=1)
        return 'OK.'

    #def __init__( self, id, title='', description='', text_format='html', text='' ):
    #    HTMLDocument.__init__( self, id, title, description, text_format, text )

    # CHECK THE OBJECT STATES AND ADVISABLE IGNORE CONFLICT !!!
    # =========================================================
    def _p_resolveConflict( self, o, s, n ):
        return ResolveConflict('HTMLCard', o, s, n, 'modification_date', mode=-1, trace=0, default=1)

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not SimpleAppItem._initstate( self, mode ):
            return 0

        if getattr( self, 'changes_log', None ) is None:
            self.changes_log = []

        if not hasattr( self, 'selected_template'):
            self.selected_template = None

        if not hasattr( self, 'registry_data' ):
            self.registry_data = {}

        if not hasattr( self, 'followup' ):
            self.followup = None

        return 1

    security.declareProtected( CMFCorePermissions.View, 'SearchableText' )
    def SearchableText( self ):
        """
            Used by the catalog for basic full text indexing.
            We should check type of object: document or attachment. Indexing may be applied for every type.
            We exclude seachable text for files and images.
        """
        if self.implements('isHTMLCard'):
            body = getPlainText( self.CookedBody( view=1, no_update=1 ) ) #EditableBody()
            body = re.sub(r'\[(.*?)\]', '', body)
            body = re.sub(r'[\f\r\t\v\n ]+', ' ', body)
            return '%s %s %s %s' % ( self.Title(), self.Description(), body, self.getAttachmentsInfo() )
        return '%s %s' % ( self.Title(), self.Description() )


InitializeClass( HTMLCard )
