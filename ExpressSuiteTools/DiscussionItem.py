"""
Discussion items definition class
$Id: DiscussionItem.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 26/02/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import TupleType, ListType, StringType
#from copy import copy

from AccessControl import ClassSecurityInfo
from Acquisition import aq_base
from DateTime import DateTime

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import _getAuthenticatedUser
from Products.CMFDefault.DiscussionItem import DiscussionItem as _DiscussionItem, \
     DiscussionItemContainer as _DiscussionItemContainer,\
     factory_type_information as _DiscussionItem_fti

from OFS.ObjectManager import ObjectManager

import Features
from Config import Roles
from SimpleObjects import ContentBase, InstanceBase
from Utils import InitializeClass, cookId, getToolByName

factory_type_information = _DiscussionItem_fti[:]
factory_type_information[0]['disallow_manual'] = 1


def addDiscussionItem( self, id, title='', description='', text_format='', text='', reply_to=None, \
                       RESPONSE=None, **kwargs ):
    """
        Add a discussion item

        'title' is also used as the subject header
        if 'description' is blank, it is filled with the contents of 'title'
        'reply_to' is the object (or path to the object) which this is a reply to

        Otherwise, same as addDocument
    """
    item = DiscussionItem( id, title=title, description=( description or title ), \
                           text_format=text_format, text=text, \
                           **kwargs \
                         )
    item._parse()

    self._setObject( id, item )
    item = self._getOb( id )

    if reply_to:
        item.setReplyTo( reply_to )

    if RESPONSE is not None:
        RESPONSE.redirect( self.absolute_url() )


class DiscussionItem( ContentBase, _DiscussionItem ):
    """
        Class for content which is a response to other content.
    """
    _class_version = 1.00

    meta_type = 'Discussion Item'
    portal_type = 'Discussion Item'

    __implements__ = Features.createFeature('isDiscussionItem'), \
                     ContentBase.__implements__, \
                     _DiscussionItem.__implements__

    security = ClassSecurityInfo()

    def __init__( self, id, text_format='', text='', **kwargs ):
        ContentBase.__init__( self, id, **kwargs )
        _DiscussionItem.__init__( self, id, self.title, self.description, text_format, text )

    SearchableText = _DiscussionItem.SearchableText
    Creator = _DiscussionItem.Creator
    getPrincipalVersionId = ''

    def getBase( self ):
        base = self
        while base is not None and not base.implements('isDocument'):
            if base.implements('isPortalRoot'):
                base = None
                break
            base = base.aq_parent
        return base

    security.declareProtected( CMFCorePermissions.View, 'listCreators' )
    def listCreators( self ):
        """
            List Dublin Core Creator elements - resource authors.
        """
        creators = getattr(aq_base(self), 'creators', None)
        if not creators:
            # for content created with CMF versions before 1.5
            if hasattr(aq_base(self), 'creator') and self.creator != 'unknown':
                creators = ( self.creator, )
            else:
                creators = ()
            self.creators = creators
        return creators

    security.declareProtected( CMFCorePermissions.ReplyToItem, 'edit_item' )
    def edit_item( self, REQUEST, RESPONSE ):
        """
            Makes changes in reply item
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return
        if self.Creator() == membership.getAuthenticatedMember().getUserName():
            self._editMetadata( title=REQUEST.get('title'), description=REQUEST.get('title') )
            self._edit( REQUEST.get('text') )
            self.reindexObject()
        return self.redirect()

    def setNotifiedUsers( self, users=None ):
        """
            Sets notify users list
        """
        if users is None:
            setattr( self, 'notified_users', [] )
            self._p_changed = 1
            return
        if type(users) is StringType:
            users = [ users ]
        if type(users) in [ ListType,TupleType ]:
            setattr( self, 'notified_users', users )
            self._p_changed = 1

    def getNotifiedUsers( self ):
        """
            Returns notify users list 
        """
        users = getattr( self, 'notified_users', [] )
        if type(users) is StringType:
            users = [ users ]
        return users

InitializeClass( DiscussionItem )


class DiscussionItemContainer( InstanceBase, _DiscussionItemContainer ):
    """
        Store DiscussionItem objects. Discussable content that
        has DiscussionItems associated with it will have an
        instance of DiscussionItemContainer injected into it to
        hold the discussion threads.
    """
    _class_version = 1.00

    security = ClassSecurityInfo()

    def __init__( self, id=None, title=None ):
        InstanceBase.__init__( self, id, title )
        _DiscussionItemContainer.__init__( self )
    #
    #   Containment events handlers:
    #       'self' -- discussion container, not an item (i.e. talkback).
    #       'item' -- HTMLDocument object, which consists this discussion container
    #       'container' -- Heading object, which consists this document
    #
    def _check_containment( self, mode=None ):
        """
            Checks either document exists in the catalog
        """
        res = []
        for item in self.objectValues():
            try: s = item._p_changed
            except: s = 0
            res.append( s )
        return res
    #
    #   Instance events handlers =================================================================================
    #
    def _containment_onAdd( self, item, container ):
        ObjectManager.manage_afterAdd.im_func( self, item, container )

    def _containment_onDelete( self, item, container ):
        ObjectManager.manage_beforeDelete.im_func( self, item, container )

    def _instance_onClone( self, source, item ):
        ObjectManager.manage_afterClone.im_func( self, item )
    #
    #   Object Manager overriden =================================================================================
    #
    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'objectIds' )
    def objectIds( self, spec=None ):
        """
            Returns a list of the ids of our DiscussionItems
        """
        if spec and spec is not DiscussionItem.meta_type:
            return []
        return self._container.keys()

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'objectItems' )
    def objectItems( self, spec=None ):
        """
            Returns a list of (id, subobject) tuples for our DiscussionItems
        """
        r = []
        a = r.append
        g = self._container.__getitem__
        for id in self.objectIds(spec):
            a( (id, g( id ).__of__(self) ) )
        return r

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'objectValues' )
    def objectValues(self, spec=None):
        """
            Returns a list of our DiscussionItems
        """
        return [ x[1] for x in self.objectItems( spec=spec ) ]

    security.declareProtected( CMFCorePermissions.ReplyToItem, 'createReply' )
    def createReply( self, title, text, Creator, version=None, email=None ):
        """
            Creates a reply in the proper place
        """
        container = self._container

        id = cookId( container, prefix='discussion')
        discussion = DiscussionItem( id, title=title, description=title, text_format='structured-text', text=text )

        container[ id ] = discussion
        discussion = container[ id ].__of__(self)
        discussion.manage_afterAdd(discussion, self)

        if Creator:
            discussion.creator = Creator

        discussion.setReplyTo( self._getDiscussable() )

        if len(discussion.parentsInThread()) == 1:
            discussion.doc_ver = version
            discussion.email = email

        return id

    security.declareProtected( CMFCorePermissions.ReplyToItem, 'delete_item' )
    def delete_item( self, REQUEST, RESPONSE ):
        """ """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return
        reply = self.getReply( REQUEST.get('id') )
        action = None

        if reply.Creator() == membership.getAuthenticatedMember().getUserName() and not self.hasReplies( reply ):
            self.deleteReply( reply.getId() )
            reply = self._getDiscussable(1)
            action = 'document_comments'
        return reply.redirect( action=action )

    security.declareProtected( CMFCorePermissions.View, 'notifiedUsersForReply' )
    def notifiedUsersForReply( self, reply ):
        """
            Returns users list to make discussion reply notification
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None

        member = membership.getAuthenticatedMember()
        who_id = member.getId()

        supervisor_users = membership.listManagers() # ['admin']
        local_users = []
        users = []

        if reply is None:
            pass
        elif reply.meta_type != 'Discussion Item':
            obj = reply
            local_users.extend( obj.users_with_local_role( Roles.Editor ))
            local_users.extend( obj.users_with_local_role( Roles.Writer ))
            local_users.extend( obj.users_with_local_role( Roles.Reader ))

            allowed_users = \
                membership.listAllowedUsers( obj, roles=['Editor','Writer'], local_only=0 ) + \
                membership.listAllowedUsers( obj, roles=['Reader'], local_only=1 )
            res = filter( lambda x, _users=local_users: x not in _users, allowed_users )
            local_users.extend( res )

            owner = obj.Creator()
            users.append( owner )
        else:
            obj = reply.aq_parent.aq_parent
            local_users.extend( obj.users_with_local_role( Roles.Editor ) )
            local_users.extend( obj.users_with_local_role( Roles.Writer ) )
            local_users.extend( obj.users_with_local_role( Roles.Reader ) )

            users.append( reply.Creator() )
            if hasattr( reply, 'notified_users' ):
                for user in reply.getNotifiedUsers():
                    if user not in users:
                        users.append( user )

            for rep in reply.parentsInThread():
                if hasattr( rep, 'Creator' ) and not users.count( rep.Creator() ) and \
                    rep.Creator() != reply.Creator():
                    users.append( rep.Creator() )

            owner = obj.Creator()
            if not users.count( owner ) and owner != reply.Creator():
                users.append( owner )

        for user in local_users:
            if not users.count( user ) and user != reply.Creator():
                users.append( user )

        for user in users:
            if user == who_id or not membership.getMemberById( user, check_only=1 ):
                users.remove( user )

        for x in supervisor_users:
            if not x in users:
                users.append( x )

        return filter( lambda x: x, users )

InitializeClass( DiscussionItemContainer )
