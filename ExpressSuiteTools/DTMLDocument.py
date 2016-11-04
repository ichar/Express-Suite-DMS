"""
DTMLDocument class
$Id: DTMLDocument.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 04/03/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re, string, os.path

from AccessControl import ClassSecurityInfo
from Acquisition import aq_base
from OFS.DTMLMethod import DTMLMethod

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.CMFCatalogAware import CMFCatalogAware
from Products.CMFCore.utils import getToolByName, _getViewFor

import Features
from Config import Permissions
from Exceptions import ResourceLockedError
from SimpleAppItem import SimpleAppItem

from Utils import InitializeClass, installPermission

factory_type_information = ( { \
                   'id'             : 'DTMLDocument'
                 , 'meta_type'      : 'DTMLDocument'
                 , 'title'          : 'DTML Document'
                 , 'description'    : """\
Simple DTML-document"""
                 , 'icon'           : 'dtml_icon.gif'
                 , 'sort_order'     : 0.45
                 , 'product'        : 'ExpressSuiteTools'
                 , 'factory'        : 'addDTMLDocument'
                 , 'immediate_view' : 'metadata_edit_form'
                 , 'permissions'    : ( Permissions.AddDTMLDocuments, )
                 , 'actions'        :
                    ( 
                      { 'id'            : 'edit'
                      , 'name'          : 'Edit'
                      , 'action'        : 'dtml_edit_form'
                      , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                      }
                    , { 'id'            : 'metadata'
                      , 'name'          : 'Metadata'
                      , 'action'        : 'metadata_edit_form'
                      , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                      }
                    )
                 },
               )

class DTMLDocument( SimpleAppItem, DTMLMethod ):
    """
        ExpressSuite DTML document
    """
    _class_version = 1.0

    meta_type = 'DTMLDocument'
    portal_type = 'DTMLDocument'

    __implements__ = ( Features.isDocument,
                       Features.isCategorial,
                       DTMLMethod.__implements__,
                       SimpleAppItem.__implements__,
                     )

    security = ClassSecurityInfo()

    manage_options = SimpleAppItem.manage_options + \
                     DTMLMethod.manage_options

    effective_date = None
    expiration_date = None

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'PUT' )
    PUT = DTMLMethod.PUT

    def __init__( self, id, title='', text='' ):
        """
            Initialize class instance
        """
        SimpleAppItem.__init__( self, id )
        DTMLMethod.__init__( self, text, None, id )

    def _initstate( self, mode ):
        # initialize attributes
        if not SimpleAppItem._initstate( self, mode ):
            return 0

        # versions < 1.38 used to be Item_w__name__
        if not getattr( self, 'id', None ):
            self.id = self.__name__

        return 1

    security.declareProtected( CMFCorePermissions.View, '__call__' )
    __call__ = DTMLMethod.__call__

    security.declareProtected( CMFCorePermissions.View, 'view' )
    def view( self, REQUEST=None ):
        """
            This method is called only from user interface (and is not called by default)
        """
        REQUEST = REQUEST or self.REQUEST
        return self.dtml_edit_form( self, REQUEST )

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'edit' )
    def edit( self, title, data, REQUEST=None ):
        if self.wl_isLocked():
            raise ResourceLockedError, 'This DTML Method is locked via WebDAV'
        if title: self.title=str(title)
        if type(data) is not type(''): data=data.read()
        self.munge(data)
        self.ZCacheable_invalidate()
        if REQUEST is not None:
            message = "Content changed."
            return self.view( self, REQUEST, potal_status_message=message )

    def upload( self, file='', REQUEST=None ):
        """
            Replace the contents of the document with the text in file
        """
        self._validateProxy(REQUEST)
        if self.wl_isLocked():
            raise ResourceLockedError, ('This document has been locked via WebDAV.')
        if type(file) is not type(''): file=file.read()
        self.munge(file)
        self.ZCacheable_invalidate()
        if REQUEST is not None:
            message = "Content uploaded."
            return self.dtml_edit_form( self, REQUEST, portal_status_message=message )

    def SearchableText( self ):
        return DTMLMethod.PrincipiaSearchSource(self)

installPermission( DTMLDocument, CMFCorePermissions.ReplyToItem )
InitializeClass( DTMLDocument )


default_dd_html="""<dtml-var standard_html_header>
<h2><dtml-var title_or_id></h2>
<p>
This is the <dtml-var id> DTML Document.
</p>
<dtml-var standard_html_footer>"""

def addDTMLDocument( self, id, title='', file='', REQUEST=None, submit=None ):
    """
        Add a DTML Document object with the contents of file. If 'file' is empty,
        default document text is used.
    """
    if type(file) is not type(''):
        file = file.read()
    if not file:
        file = default_dd_html

    id = str(id)
    title = str(title)

    ob = DTMLDocument( id, text=file )

    ob.title = title
    id = self._setObject(id, ob)

    if REQUEST is not None:
        try: u=self.DestinationURL()
        except: u=REQUEST['URL1']
        if submit==" Add and Edit ":
            u="%s/%s" % ( u, quote(id) )
        REQUEST.RESPONSE.redirect( u+'/manage_main' )

    return ''
