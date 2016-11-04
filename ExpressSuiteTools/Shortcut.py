""" 
Shortcuts are references to other objects within the site
$Id: Shortcut.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 30/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import string
import urlparse
from types import StringType
from zLOG import LOG, DEBUG, INFO

from Globals import InitializeClass
from AccessControl import ClassSecurityInfo
from Acquisition import aq_parent, aq_inner, aq_base

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName
from Products.CMFDefault.Link import Link as CMFLink

from Config import Roles
from SimpleAppItem import SimpleAppItem

from Utils import getObjectByUid, InitializeClass, joinpath

factory_type_information = ( { 'id'             : 'Shortcut'
                             , 'meta_type'      : 'Shortcut'
                             , 'title'          : 'Shortcut'
                             , 'description'    : """\
A Shortcut is a Link to an intra-portal resource."""
                             , 'icon'           : 'link_icon.gif'
                             , 'sort_order'     : 0.8
                             , 'product'        : 'ExpressSuiteTools'
                             , 'factory'        : 'addShortcut'
                             , 'factory_form'   : 'shortcut_add_form'
                             , 'permissions'    : ( CMFCorePermissions.View, )
                             , 'disallow_manual': 0
                             , 'actions'        :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View'
                                  , 'action'        : ''
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  },
                                  { 'id'            : 'edit'
                                  , 'name'          : 'Edit'
                                  , 'action'        : 'shortcut_edit_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  }
                                )
                             }
                           ,
                           )

def addShortcut( self, id, remote, title='', description='' ):
    """
        Add a Shortcut
    """
    o = Shortcut(id, title, description)
    self._setObject(id,o)

    # Bind shortcut to the document
    shortcut = getattr(self, id)
    shortcut.edit(remote=remote)


class Shortcut( SimpleAppItem, CMFLink ): #, ProxyReaderFactory
    """
        A Shortcut (special kind of link)
    """
    meta_type = 'Shortcut'

    security = ClassSecurityInfo()

    def __init__( self, id, title, description='' ):
        """
            Initialize class instance
        """
        SimpleAppItem.__init__( self, id )
        #ProxyReaderFactory.__init__( self, id )
        # Can not create link right now because a Shortcut object was not instantiated yet

        self.title = title
        self.description = description
        self.link_id = None

    security.declarePublic( 'locate' )
    def locate( self, REQUEST=None ):
        # XXX
        LOG('Shortcut.locate', DEBUG, 'id: %s' % self.id)
        not_found = 'Unfortunatly, requested item was not found.'
        ob = self.getObject()
        if ob is not None:
            url = ob.absolute_url( canonical=1 ) + '?expand=1'
            return REQUEST.RESPONSE.redirect( url )
        return not_found

    security.declarePublic( 'title_or_id') 
    def title_or_id( self ):
        # Returns design title or id
        return self.title or self.id

    def getContentsSize( self ):
        """
           Returns number of objects in the destination folder
        """
        ob = self.getObject()

        if ob is None:
            return None
        elif getattr(ob, 'meta_type', None) == 'Heading':
            catalog = self.portal_catalog
            kw = {}
            kw['meta_type'] = ['HTMLDocument', 'HTMLCard']
            kw['parent_path'] = ob.relative_url() + '/%'
            return catalog.countResults( **kw ) or 0
        elif hasattr(aq_base( ob ), 'get_size'):
            return ob.get_size()
        else:
            return 0

    def getRemoteUrl( self, **kw ):
        """
            Returns the remote URL of the Link
        """
        obj = self.getObject()
        if obj:
            return obj.absolute_url(**kw)
        return self.aq_parent.relative_url( message='Unable to find the linked document' )

    def getIcon( self, relative_to_portal=0 ):
        """
            Instead of a static icon, like for Link objects, we want to display an icon based on
            what the Shortcut links to.
        """
        try:
            obj = self.getObject()
            if obj is not None:
                return obj.getIcon( relative_to_portal )
            else:
                return None
        except:
            return 'p_/broken'

    def getObject( self ):
        """
            Returns the actual object that the Shortcut is linking to
        """
        link = self._getLink()
        return link is not None and link.getDestinationObject()

    def getObjectUid( self ):
        """
            Returns the actual object uid that the Shortcut is linking to
        """
        link = self._getLink()
        return link is not None and link.getDestinationUid()

    def _getLink( self ):
        links = getToolByName( self, 'portal_links', None )
        if links is None:
            return
        link_id = self.link_id
        return link_id and getattr( links, link_id, None )

    def edit( self, remote ):
        """
            Update and reindex.
            'remote' can be either remote object itself or an object uid string
        """
        self._edit( remote )
        self.reindexObject()

    def _edit( self, remote ):
        """
            Edits the Shortcut
        """
        if type(remote) is StringType:
            remote = getObjectByUid(self, remote)
        if not self.Title():
            self.setTitle(remote.Title())

        # Create a link to the remote object.
        # Link is the one and only way to keep in touch with the
        # remote document.
        links = getToolByName( self, 'portal_links', None )
        if links is None:
            return
        self.link_id = links.createLink( source_uid=self.getUid(), destination_uid=remote.getUid(), relation=0 )
        self.portal_type = remote.portal_type

    def externalEditLink_( self, object, borrow_lock=0 ):
        """
            Insert the external editor link to an object if appropriate
        """
        link = ''
        if object is self:
            object = self.getObject()
        if object:
            link = object.externalEditLink_(object, borrow_lock)
        return link

InitializeClass( Shortcut, __version__ )

def getSize(ob):
    n = 0
    values = getattr(ob, '_objects', [])
    for v in values:
        id = v.get('id')
        try: x = ob._getOb(id)
        except: continue
        if getattr(x, 'meta_type', None) == 'Heading':
            n += getSize(x)
        else:
            n += 1
    return n
