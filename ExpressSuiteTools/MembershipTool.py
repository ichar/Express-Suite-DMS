"""
MembershipTool with MemberActivity and MemberProperties classes
$Id: MembershipTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 06/07/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys, re
from random import randrange
from string import lower
from types import StringType, ListType, TupleType, DictType
from DateTime import DateTime

import xmlrpclib

from ZODB.POSException import ConflictError, ReadConflictError

from Acquisition import Implicit, aq_inner, aq_base, aq_parent, aq_get
from AccessControl import ClassSecurityInfo, Permissions as ZopePermissions
from AccessControl.User import nobody

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.Expression import Expression
from Products.CMFCore.MembershipTool import MembershipTool as _MembershipTool
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser, _checkPermission, rolesForPermissionOn

import Config
from ConflictResolution import ResolveConflict
from Exceptions import Unauthorized
from ISAMSupporter import ISAMMapping
from SimpleObjects import Persistent, SimpleRecord, ToolBase
from DepartmentDictionary import departmentDictionary
from PortalLogger import portal_log, portal_info, portal_debug, portal_error
from TransactionManager import CommitThread

from Utils import InitializeClass, getLanguageInfo, getNextTitle, getBTreesItem, parseDate, uniqueValues, \
     GetSessionValue, SetSessionValue, ExpireSessionValue, check_request, translit_string, \
     FilterMembersByDefaultAccess, AnonymousUserName

from CustomDefinitions import portalConfiguration, CustomPortalColors
from CustomObjects import ObjectHasCustomCategory, CustomDefs

CURRENT_LEN_PREFERENCES = 12


class MemberProperties( Persistent ):
    """ Members Properties class """
    _class_version = 1.00

    imported = None

    def __init__( self ):
        Persistent.__init__(self)
        self.value = {}

    # CHECK THE OBJECT STATES AND ADVISABLE IGNORE CONFLICT !!!
    # =========================================================
    def _p_resolveConflict( self, oldState, savedState, newState ):
        return 1

    def setValue( self, context, member, name=None, value=None ):
        if context is None or not member:
            return
        if not self.value.has_key(member):
            self.value[member] = {}

        if name:
            self.value[member][name] = value
        else:
            self.value[member] = value

        self._p_changed = 1

        #CommitThread( context, 'MemberProperties', no_hook=1 )

    def hasValue( self, member, name=None ):
        if member and self.value.has_key( member ):
            if name:
                if type(self.value[member]) is DictType:
                    if self.value[member].has_key( name ):
                        return 1
            else:
                return 1
        return 0

    def getValue( self, member, name=None, default=None ):
        if not member:
            return default
        try: mp = self.value.get( member ) or {}
        except: mp = {}
        if name:
            return mp.get(name) or default
        return mp

    def delValue( self, context, member ):
        if context is None or not member:
            return
        if not self.value.has_key(member):
            return
        del self.value[member]

        self._p_changed = 1

        #CommitThread( context, 'MemberProperties', no_hook=1 )


class MemberActivity( Persistent, Implicit ):
    """ Members Activity statistics class """

    id = 'MemberActivity'

    def __init__( self ):
        """
            Initialize class instance
        """
        Persistent.__init__( self )
        self._values = ISAMMapping( self.getId(), Config.default_member_activity_columns )

    def getId( self ):
        return getattr(self, 'id', None)

    def setup( self, force=None ):
        """
            Initialize ISAM class instance
        """
        if not force and Config.CheckZODBBeforeInstall:
            if getattr(self, '_values', None) is not None:
                return

        values = ISAMMapping( self.getId(), Config.default_member_activity_columns )

        value = getattr(self, 'value', {}).items()
        value.sort()

        for id, v in value:
            values[id] = ( v[0], v[1], v[2][0], v[2][1], )

        if Config.DropZODBContent:
            if hasattr(self, 'value'):
                del self.value

        self._values = values
        self._p_changed = 1

    def default_user_runtime( self ):
        return [ 0, 0 ]

    def data( self ):
        for n in range(2):
            try:
                items = self._values._state()
                break
            except:
                self.setup()
        rs = {}
        for id, login_time, activity, x1, x2 in items:
            rs[id] = ( login_time, activity, [ x1, x2 ] )
        return rs

    def setValue( self, context, id=None, runtime=None ):
        """
            Sets activity value of member with given id
        """
        if not id:
            id = _getAuthenticatedUser(self).getUserName()

        login_time, activity, user_runtime = self.getValue(id)

        if not login_time or not login_time.isCurrentDay():
            user_runtime = self.default_user_runtime()
            activity = 0

        login_time = DateTime()

        if runtime:
            user_runtime[0] += 1
            user_runtime[1] = ( user_runtime[1] + runtime ) / ( user_runtime[1] and 2.0 or 1.0 )

        activity += 1
        self._values.set( id, ( login_time, activity, user_runtime[0], user_runtime[1] ), no_raise=1, ignore=1 )

    def getValue( self, id=None ):
        """
            Returns activity value of member with given id
        """
        default_user_runtime = self.default_user_runtime()
        v = id and self._values.get( id )
        if v:
            v = v[0]
            if len(v) >= 4 and id == v[0]:
                login_time = DateTime(v[1])
                return ( login_time, v[2], [ v[3], v[4] ] )
            login_time = None
            activity = 0
            return ( login_time, activity, default_user_runtime )
        return ( None, 0, default_user_runtime )


class MembershipTool( ToolBase, _MembershipTool ):
    """ Portal Membership Tool """
    _class_version = 1.03

    meta_type = 'ExpressSuite Membership Tool'

    security = ClassSecurityInfo()

    manage_options = _MembershipTool.manage_options # + ToolBase.manage_options

    memberareaCreationFlag = 0
    member_activity = None
    member_properties = None

    _actions = (
            ActionInformation(id='logout'
                        , title='Log out'
                        , description='Click here to logout'
                        , action=Expression( text='string: ${portal_url}/logout' )
                        , permissions=(CMFCorePermissions.View,)
                        , category='user'
                        , condition=Expression(text='member')
                        , visible=1
                        ),
            ActionInformation(id='manageGroups'
                        , title='Manage groups'
                        , description='User groups management'
                        , action=Expression( text='string: ${portal_url}/manage_groups_form' )
                        , permissions=(CMFCorePermissions.ManagePortal,)
                        , category='user'
                        , condition=None
                        , visible=1
                        ),
            ActionInformation(id='manageUsers'
                        , title='Manage users'
                        , action=Expression( text='string: ${portal_url}/manage_users_form?abc=À' )
                        , permissions=(ZopePermissions.manage_users,)
                        , category='user'
                        , condition=None
                        , visible=1
                        ),
            ActionInformation(id='addUser'
                        , title='Create user'
                        , action=Expression( text='string: ${portal_url}/join_form' )
                        , permissions=(ZopePermissions.manage_users,)
                        , category='user'
                        , condition=None
                        , visible=1
                        ),
            ActionInformation(id='preferences'
                        , title='Personal properties'
                        , description='Change your user preferences'
                        , action=Expression( text='string: ${portal_url}/personalize_form' )
                        , permissions=(CMFCorePermissions.View,)
                        , category='user'
                        , condition=Expression(text='member')
                        , visible=1
                        ),
            ActionInformation(id='interfacePreferences'
                        , title='Interface preferences'
                        , description='Change your interface preferences'
                        , action=Expression( text='string: ${portal_url}/interface_preferences_form' )
                        , permissions=(CMFCorePermissions.View,)
                        , category='user'
                        , condition=Expression(text='member')
                        , visible=1
                        ),
            ActionInformation(id='changePassword'
                        , title='Change password'
                        , description='Change your password'
                        , action=Expression( text='string: ${portal_url}/password_form' )
                        , permissions=(CMFCorePermissions.View,)
                        , category='user'
                        , condition=Expression(text='member')
                        , visible=1
                        ),
            ActionInformation(id='favorites'
                        , title='Add to Favorites'
                        , description='Add to Favorites'
                        , action=Expression( text='string: ${object_url}/addtoFavorites' )
                        , permissions=(CMFCorePermissions.View,)
                        , category='object'
                        , condition=Expression(text='python: portal.portal_membership.getPersonalFolder() and folder is not object')
                        , visible=1
                        ),
        ) + ToolBase._actions

    _default_properties = {
        'taskTemplates'        : {},
        'main_filter_id'       : None,
        'filters'              : {},
        'current_folder_view'  : 'table',
        'folder_views'         : {
                        'default'  : {},
                        'table'    : { 'reverse' : '', 'sort_by' : 'Title' },
                        'outgoing' : {}
            },
        'interfacePreferences' : {
                        'viewing_document_number' : 10,
                        'cleanup'                 : 1,
                        'external_editor_buttons' : 0,
                        'contents_size'           : 1,
                        'show_link_to_tabs'       : 1,
                        'show_description'        : 1,
                        'save_registry_filter'    : 0,
                        'save_frameset_width'     : 0,
                        'copy_clipboard'          : 0,
                        'show_nav_members'        : 1,
                        'finalize_settings'       : 'all',
            },
        'commissions'          : None
        }

    # override methods security
    security.declareProtected( CMFCorePermissions.ListPortalMembers, 'listMemberIds' )

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not ToolBase._initstate( self, mode ):
            return 0

        if getattr( self, 'role_map', None ) is None:
            self.role_map = {}

        if getattr( self, 'member_activity', None ) is None:
            self.member_activity = MemberActivity()

        if getattr( self, 'member_properties', None ) is None or type(self.member_properties) is not type({}):
            self.member_properties = MemberProperties()

        return 1

    def _p_resolveConflict( self, oldState, savedState, newState ):
        return ResolveConflict( 'MembershipTool', oldState, savedState, newState, ( \
               'role_map', 'member_properties', ) 
               )

    security.declarePublic('getAuthenticatedMember')
    def getAuthenticatedMember(self):
        """
            Returns the currently authenticated member object
            or the Anonymous User.  Never returns None.
        """
        u = _getAuthenticatedUser(self)
        if u is None:
            u = nobody
        return self.wrapUser(u, 1)

    def wrapUser( self, u, wrap_anon=0 ):
        """
            Sets up the correct acquisition wrappers for a user
            object and provides an opportunity for a portal_memberdata
            tool to retrieve and store member data independently of
            the user object.
        """
        b = getattr(u, 'aq_base', None)
        if b is None:
            # u isn't wrapped at all.  Wrap it in self.acl_users.
            b = u
            u = u.__of__(self.acl_users)
        if ( b is nobody and not wrap_anon ) or hasattr(b, 'getMemberId'):
            # This user is either not recognized by acl_users or it is
            # already registered with something that implements the 
            # member data tool at least partially.
            return u

        parent = self.aq_inner.aq_parent
        base = getattr(parent, 'aq_base', None)
        if hasattr(base, 'portal_memberdata'):
            # Apply any role mapping if we have it
            if hasattr(self, 'role_map'):
                for portal_role in self.role_map.keys():
                    if self.role_map.get(portal_role) in u.roles and portal_role not in u.roles:
                        u.roles.append(portal_role)

            # Get portal_memberdata to do the wrapping.
            md = getToolByName( parent, 'portal_memberdata' )
            try:
                portal_user = md.wrapUser(u)
                # Check for the member area creation flag and
                # take appropriate (non-) action
                if getattr(self, 'memberareaCreationFlag', 0) != 0:
                    if self.getHomeUrl(portal_user.getId()) is None:
                        self.createMemberarea(portal_user.getId())
                return portal_user
            #except ConflictError:
            #    raise
            except:
                type, value, tb = sys.exc_info()
                try:
                    portal_error( 'MembershipTool.wrapUser', "Error during wrapUser:\nType:%s\nValue:%s\n" % ( type, value ) )
                finally:
                    tb = None # Avoid leaking frame
                pass
        # Failed.
        return u
    #
    #   Users Support ============================================================================================
    #
    def addMember( self, id, password, roles, domains, properties=None ):
        """
            Adds a new member to the user folder.
        """
        self.__getPUS().userFolderAddUser( id, password, roles, domains )

        member = self.getMemberById( id )
        if member is None:
            return

        if properties is not None:
            member.setMemberProperties( properties )

        # this is required if stored password is encrypted
        # and must be mailed to the user after registration
        member.getUser().__ = password

    security.declarePublic('set_pwd')
    def set_pwd( self, id, password, sync=None ):
        """
            Returns 1 if success
        """
        if not ( id and password ):
            return 0
        member = self.getMemberById( id )
        if member is None:
            return 0
        IsError = 0
        if not sync:
            member.getUser().__ = password
        else:
            IsError = self.sync_property( 'set_pwd', id, password )
        return sync and not IsError and 1 or IsError

    security.declarePublic('setCommissions')
    def setCommissions( self, value=None, sync=None ):
        """
            Sets commissions membership for current user.
            Returns 0 if success
        """
        try:
            if self.getMemberProperties( name='commissions' ) != value:
                self.setMemberProperties( name='commissions', value=value )
            IsError = 0
        except:
            IsError = 1
        if sync and not IsError:
            IsError = self.sync_property( 'setCommissions', value )
        return IsError

    def sync_property( self, method, *args ):
        """
            Sync update property
        """
        IsError = 0
        for addr in portalConfiguration.getAttribute( attr='remote_portal_addresses', context=self ):
            try:
                remote_membership = xmlrpclib.Server( '%s/%s' % ( addr, 'portal_membership' ) )
                IsError = apply( getattr(remote_membership, method), args )
            except:
                portal_error( 'MembershipTool.sync_property', 'Synchronizing property error: instance %s, args: %s' % ( addr, str(args) ) )
                IsError = 1
        return IsError

    security.declareProtected( CMFCorePermissions.ManagePortal, 'deleteMembers' )
    def deleteMembers( self, userids ):
        """
            Delete one or more members
        """
        if not userids:
            return
        # XXX should we verify each ids in the list?

        userfolder = self.__getPUS()
        catalog = getToolByName( self, 'portal_catalog', None )
        memberdata = getToolByName( self, 'portal_memberdata', None )

        # cleanup objects ownership
        results = catalog.unrestrictedSearch( Creator=userids )
        portal_info( 'MembershipTool.deleteMembers', 'Removing ownership in %d objects' % len(results) )

        for item in results:
            object = item.getObject()
            if object is None:
                continue
            meta_type = getattr(object, 'meta_type', None)
            signer = self.getObjectSigner( object, exclude_user=object.Creator() )
            object.changeOwnership( signer )

            if meta_type in ['HTMLDocument']:
                object.reindexObject( idxs=['SearchableText'] )

        # cleanup local roles
        roles = [ 'user:%s' % id for id in userids ]
        results = catalog.unrestrictedSearch( allowedRolesAndUsers=roles )
        portal_info( 'MembershipTool.deleteMembers', 'Removing local roles in %d objects' % len(results) )

        for item in results:
            object = item.getObject()
            if object is None:
                continue # should not happen
            try:
                object.manage_delLocalRoles( userids )
            except:
                object.manage_delLocalRoles( userids )
            object.reindexObject( idxs=['allowedRolesAndUsers','Creator'] )

        # remove member properties
        for id in userids:
            self.member_properties.delValue(self, id)

        # filter out orphaned users
        accounts = userfolder.getUserNames()
        accounts = [ id for id in userids if id in accounts ]

        # remove user accounts
        userfolder.userFolderDelUsers( accounts )

        # purge member data; this is the last since it looks in the userfolder
        memberdata.pruneMemberDataContents()

    security.declareProtected( CMFCorePermissions.View, 'getObjectSigner' )
    def getObjectSigner( self, object, exclude_user=None, signer_only=0 ):
        """
            Returns object's owner candidate, the document signer or any followup involved user
        """
        if object is None or getattr(object, 'meta_type', None) not in ['HTMLDocument']:
            return None

        if not ObjectHasCustomCategory( object ):
            return None

        try: tasks = object.followup.getBoundTasks()
        except: tasks = None
        if not tasks:
            return None

        signers = []
        involved_users = []

        for task in tasks:
            if not task: continue
            x = task.InvolvedUsers( no_recursive=1 )
            if x and exclude_user and exclude_user in x:
                x.remove( exclude_user )
            if task.BrainsType() == 'signature_request':
                signers.extend( x )
            elif not signer_only:
                involved_users.extend( x )

        if not signers and not involved_users:
            return None

        member_ids = signers + involved_users

        for userid in member_ids:
            member = self.getMemberById( userid )
            if member is not None:
                return userid

        return None

    security.declareProtected( CMFCorePermissions.View, 'getMemberById' )
    def getMemberById( self, id, containment=None, raise_exc=None, check_only=None ):
        """
            Returns the given member
        """
        users = self.__getPUS()
        if containment:
            users = aq_inner( users )
        u = users.getUser(id)
        if u is not None:
            if check_only: return 1
            if containment:
                u = u.__of__( users )
            u = self.wrapUser(u, 1)
        elif raise_exc:
            raise KeyError, id
        return u

    def validateMember( self, member=None ):
        try:
            if member is None:
                member = self.getAuthenticatedMember()
                uname = member.getUserName()
            else:
                uname = member
                member = self.getMemberById( id=uname )
        except: 
            uname = member = None
        return ( member, uname )

    security.declareProtected( CMFCorePermissions.ListPortalMembers, 'listMemberNames' )
    def listMemberNames( self ):
        """
            Returns (id, full name) tuple for each member
        """
        results = []
        for user_id in self.__getPUS().getUserNames():
             results.append( {'user_id' : user_id, 'user_name' : self.getMemberName(user_id)} )

        results.sort(lambda x, y: cmp(lower(x['user_name']), lower(y['user_name'])))

        return results

    security.declarePublic('getMemberName')
    def getMemberName( self, u_id=None ):
        """
            Returns the formatted member name/surname or just login if no user data specified.
        """
        if u_id and u_id != 'Anonymous User':
            member = self.getMemberById( u_id )
        else:
            member = self.getAuthenticatedMember()
        if member is None:
            return u_id
        try:
            return member.getMemberName()
        except:
            return u_id

    security.declarePublic('getMemberBriefName')
    def getMemberBriefName( self, u_id, mode=None ):
        """
            Returns the formatted member brief
            or just login if no user data specified.
        """
        member = self.getMemberById( u_id )
        return member is not None and member.getMemberBriefName( mode ) or u_id

    security.declarePublic('getMemberEmail')
    def getMemberEmail( self, u_id ):
        """
            Returns the user email address or None if
            no user data specified.
        """
        member = self.getMemberById( u_id )
        return member is not None and member.getMemberEmail()

    security.declarePublic('getMemberFacsimile')
    def getMemberFacsimile( self, u_id ):
        """
            Returns the user's facsimile url.

            Result:

                String.
        """
        member = self.getMemberById( u_id )
        try:
            facsimile = member.getProperty('facsimile', None)
        except:
            facsimile = None
        return facsimile

    security.declarePublic('getUserInfo')
    def getUserInfo( self, u_id ):
        """
            Get user personal data
            Returns: user info dictionary
        """
        info = {}
        member = self.getMemberById( u_id )
        if member is not None:
            for key in member.getTool().propertyIds():
                try:
                    if key == 'fullname':
                        info[key] = self.getMemberName( u_id )
                    else:
                        info[key] = member.getProperty( key )
                except:
                    info[key] = None
        return info
    #
    #   User groups interface methods ============================================================================
    #
    security.declareProtected( CMFCorePermissions.ListPortalMembers, 'getGroup' )
    def getGroup( self, id ):
        """
            Returns the group object
        """
        try:
            group = self.__getPUS().getGroupById( id )
        except:
            group = None
        return group

    def getGroupIdByTitle( self, title ):
        """
            Returns the group id by title
        """
        if title:
            title = title.strip().lower()
        else:
            return None

        for x in self.listGroups():
            group_id = x.getId()
            group_title = self.getGroupTitle( group_id )
            if group_title.lower() == title:
                return group_id

    def getGroupMembers( self, id, sort=None ):
        """
            Returns the group members list
        """
        group = self.getGroup(id)
        users = group is not None and list(group.getUsers()) or []
        if sort:
            users.sort()
        return users

    security.declareProtected( CMFCorePermissions.ListPortalMembers, 'listGroups' )
    def listGroups( self ):
        """
            Return a user's groups list
        """
        return map( self.__getPUS().getGroupById, self.__getPUS().getGroupNames() )

    def getListGroups( self, attr=None, sys=None, keys=None ):
        """
            Return a user groups id-title mapping list
        """
        res = []
        if attr and type(attr) not in (ListType, TupleType):
            attr = [attr]
        if keys and type(keys) in (ListType, TupleType) and len(keys) >= 2:
            id, title = keys[0:2]
        else:
            id = 'group_id'
            title = 'group_title'
        for group in self.listGroups():
            group_id = group.getId()
            group_title = self.getGroupTitle( group_id )
            if not sys:
                if group_title.startswith('sys:'):
                    continue
            if attr is None:
                res.append( { id : group_id, title: group_title } )
            else:
                for key in attr:
                    if self.getGroupAttribute( group_id, attr_name=key ):
                        res.append( { id : group_id, title : group_title } )
                        break
        return res

    def expandUserList( self, user_groups=(), members=() ):
        """
            Returns a plain users list using groups and
        """
        userlist = list( members )

        for group_id in user_groups:
            group = self.getGroup(group_id)
            if group is not None:
                userlist.extend( group.getUsers() )

        # Filter duplicates
        result = []
        for value in userlist:
            if value not in result:
                result.append(value)
        return result

    def isGroupInheritsRole( self, object, groupid, role ):
        """
            Does this role is inherited from the parent?
        """
        return role not in object.get_local_roles_for_groupid( groupid ) \
           and self.isGroupInRole( object, groupid, role )

    def getForbidFolderInJungle( self, object ):
        """
            Returns 'forbid_folder_in_jungle' property for folder
        """
        return object.forbid_folder_in_jungle

    def isGroupInRole( self, object, groupid, role ):
        """
            Check whether the group has
            the given permission over the object
        """
        while not object.implements('isPortalRoot'):
            if role in object.get_local_roles_for_groupid( groupid ):
                return 1
            object = object.aq_parent
        return 0

    security.declareProtected(CMFCorePermissions.ManagePortal, 'manage_groups')
    def manage_groups( self, REQUEST, addGroup=None, delGroup=None ):
        """
            Create or delete the user group
            Called by the management screen.
        """
        if addGroup is None and delGroup is None:
            addGroup = REQUEST.get('addGroup', '')
            delGroup = REQUEST.get('delGroup', '')

        if addGroup:
            title = REQUEST.get('group')
            if title:
                id = translit_string( title, self.getLanguage() )
                return self._addGroup( id, title, REQUEST )

        if delGroup:
            ids = REQUEST.get('groups')
            return self._delGroups( ids, REQUEST )

        if REQUEST is not None:
            return self.redirect( action='manage_groups_form', REQUEST=REQUEST )

    def _addGroup( self, group, title=None, REQUEST=None ):
        if not group:
            return

        self.__getPUS().userFolderAddGroup( group, title or group )

        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect( self.portal_url() + '/group_editor_form?group_id=' + group )

    def _delGroups( self, groups, REQUEST ):
        if not groups: return

        self.__getPUS().userFolderDelGroups(groups)

        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect( self.portal_url() + '/manage_groups_form' )

    def getGroupInfo( self, group_id ):
        """
            Returns the group info list
        """
        group = self.getGroup(group_id)
        if group is None:
            return None
        group_title = self.getGroupTitle(group_id)
        return [ group_title, getattr(group, 'group_attr', {}) ]

    def getGroupTitle( self, group_id ):
        """
            Returns the group title
        """
        group = self.getGroup(group_id)
        return group is not None and group.Title().strip()

    def getGroupAttribute( self, group_id, attr_name=None, mapping=None ):
        """
            Returns the group attribute
        """
        group_info = self.getGroupInfo(group_id)

        if attr_name:
            g_attr = group_info[1]
            attr_value = g_attr.has_key(attr_name) and g_attr[attr_name] or None
        else:
            group_attr = group_info[1]
            for key in self.getGroupKeys().keys():
                if not group_attr.has_key(key):
                    group_attr[key] = 0
            if mapping:
                attr_value = [ { 'attr_name' : key, 'attr_value' : group_attr[key] } for key in group_attr.keys() ]
            else:
                attr_value = group_attr

        return attr_value

    def getGroupKeys( self ):
        """
            Returns the group custom attribute keys
        """
        group_keys = { 'SD' : 0, 'CH' : 0, 'DA' : 0 }
        return group_keys

    security.declareProtected(CMFCorePermissions.ChangePermissions, 'manage_changeGroup')
    def manage_changeGroup( self, group=None, group_users=None, title=None, REQUEST=None ):
        """
            Assign the users to the given group and change the group description and attributes
        """
        if group is None:
            group_id = REQUEST.get('group')
            group_users = REQUEST.get('group_users', [])
            group_title = REQUEST.get('title', '')
        else:
            if group_users is None:
                group_users = []
            group_title = title or ''
            group_id = group

        if group_id:
            if REQUEST is not None:
                g_attr = self.getGroupAttribute( group_id )

                for x in self.getGroupKeys().keys():
                    if type(g_attr) is DictType:
                        g_attr[x] = int(REQUEST.get(x, 0))

                group = self.getGroup( group_id )
                if group is not None:
                    setattr(group, 'group_attr', g_attr)

            acl_users = self.__getPUS()
            acl_users.setUsersOfGroup(group_users, group_id)

            if group_title:
                acl_users.getGroupById(group_id).setTitle(group_title)

        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect( self.portal_url() + '/manage_groups_form' )

    security.declareProtected( CMFCorePermissions.ListPortalMembers, 'canListMembers' )
    def canListMembers( self, group ):
        """
            Checks whether the current user can list members of a group.

            Arguments:

                'group' -- group object or identifier of interest

            Result:

                Boolean value.
        """
        policy = Config.GroupAccessPolicy

        if policy == 'all':
            # any user can list members of any group
            return 1

        if _checkPermission( ZopePermissions.manage_users, self ):
            # portal manager can list members of any group
            return 1

        if policy == 'member':
            # only group member can list other members of the group
            return self.getAuthenticatedMember().isMemberOfGroup( group )

        # users cannot list group members
        return 0

    #security.declareProtected( CMFCorePermissions.ListPortalMembers, 'listGroupMembers' )
    def listGroupMembers( self, group, member=1, access=None ):
        """
            Returns members of a given group.

            Arguments:

                'group' -- either group object or identifier string

                'member' -- checks the member authority to get group members list, Boolean

                'access' -- check member default access, Boolean

            Result:

                List of user objects (MemberData).
        """
        if type(group) is StringType:
            group = self.getGroup( group )

        if group is None:
            return []

        if member and not self.canListMembers( group ):
            raise Unauthorized( group )

        if access:
            group_users = FilterMembersByDefaultAccess( self, group.getUsers() )
        else:
            group_users = group.getUsers()

        if member:
            # XXX group may return invalid users in case users/groups source was switched
            return filter( None, map( self.getMemberById, group_users ) )
        else:
            return group_users

    security.declarePrivate( 'listSubordinateUsers' )
    def listSubordinateUsers( self, user=None, include_chief=None ):
        """
            Returns names of users subordinate to the specified user.

            Positional arguments:

                'user' -- optional user object or username of the user
                        whose subordinates are requested; if not given
                        subordinates of the current user are returned

            Keyword arguments:

                'include_chief' -- boolean flag indicating that the user
                        himself should be included in results list too;
                        default is not to include

            Result:

                List of usernames (user IDs).
        """
        user_ids = []
        member = self.getAuthenticatedMember()
            
        if type(user) is StringType:
            user_ids.append( user )
        elif user is not None:
            user_id = user.getId()
            user_ids.append( user_id )
        
        if include_chief and member != user:
            user_ids.append( member.getId() )

        return user_ids
    #
    #   Personal folders =========================================================================================
    #
    security.declarePublic( 'getPersonalFolder' )
    def getPersonalFolder( self, *args, **kw ):
        """
            Returns the current user's personal folder object by type.
        """
        return self.getAuthenticatedMember().getPersonalFolder( *args, **kw )

    security.declarePublic( 'getPersonalFolderPath' )
    def getPersonalFolderPath( self, no_instance=None, *args, **kw ):
        """
            Returns the path to the current user's personal folder by type.
        """
        path = self.getAuthenticatedMember().getPersonalFolderPath( *args, **kw )
        if path and no_instance:
            instance= getToolByName( self, 'portal_properties' ).instance_name()
            path = path.replace( '/'+instance, '' )
        return path

    security.declarePublic( 'getPersonalFolderUrl' )
    def getPersonalFolderUrl( self, *args, **kw ):
        """
            Returns the URL of the current user's personal folder by type.
        """
        return self.getAuthenticatedMember().getPersonalFolderUrl( *args, **kw )

    security.declarePublic( 'getMemberWhomFolder' )
    def getMemberWhomFolder( self, object, to_whom=None ):
        """
            Returns member's folder object by given member attribute
        """
        member = self.getAuthenticatedMember()
        uname = member.getUserName()
        IsCreator = object is not None and object.Creator() == uname and 1 or 0

        if uname in CustomDefs('operators', context=self) and IsCreator:
            pass
        elif IsCreator:
            pass
        else:
            if not to_whom:
                return None
            member_id = type(to_whom) in ( ListType, TupleType ) and to_whom[0] or to_whom
            if member_id is None:
                return None
            member = self.getMemberById( member_id )

        folder_to_move = member.getHomeFolder( unrestricted=1 )
        return folder_to_move

    def getObjectOwners( self, object ):
        """
            Returns object owners list including possible owner changing
        """
        if object is None:
            return []
        local_roles = getattr( object, '__ac_local_roles__', {} )
        owners = local_roles and [ id for id in local_roles.keys() \
            if 'VersionOwner' in local_roles[id] or 'Owner' in local_roles[id] ] or []
        creator = object.Creator()
        if not creator:
            return owners
        if creator in owners:
            owners.remove(creator)
        owners.insert( 0, creator )
        return owners

    def listAllowedUsers( self, object, roles=None, local_only=None, check_only=None, with_access=None ):
        """
            Returns a list of users with roles permission.
            Used by PortalCatalog to filter out items you're not allowed to see.
        """
        allowed = []
        try:
            instance = getToolByName( self, 'portal_properties' ).instance_name()
        except:
            instance = None

        roles = roles or Config.ManagedLocalRoles
        if type(roles) not in ( ListType, TupleType ):
            roles = [ roles ]

        if local_only and hasattr(object, 'getLocalRoles'):
            for u_id, u_roles in object.getLocalRoles():
                if not roles or True in filter(None, map( lambda x, r=roles: x in r, u_roles )):
                    if with_access and instance:
                        member = self.getMemberById( u_id )
                        if member is None:
                            continue
                        if not member.getMemberAccessLevel( instance ):
                            continue
                    if check_only: 
                        return 1
                    allowed.append( u_id )

            if check_only:
                return 0
            return uniqueValues( allowed )

        permission = 'View'
        allowed_roles = rolesForPermissionOn( permission, object )
        object_roles = getattr( object, '__roles__', [] )

        for u_id in self.listMemberIds():
            if allowed and check_only:
                return 1
            member = self.getMemberById( u_id )
            if member is None:
                continue
            if with_access and instance:
                if not member.getMemberAccessLevel( instance ):
                    continue

            roles_in_context = uniqueValues(member.getRolesInContext( object ))

            for role in roles:
                if u_id in allowed:
                    break
                if not role in allowed_roles or not role in roles_in_context:
                    continue
                if member.has_role(role, object):
                    allowed.append( u_id )
                    break

        return allowed

    def listManagers( self ):
        """
            Returns portal managers id list
        """
        managers = []
        for u_id in self.listMemberIds():
            if self.getMemberById( u_id ).has_role('Manager'):
                managers.append( u_id )
        return managers

    security.declarePublic('getMemberIds')
    def getMemberIds( self, access=None ):
        """ 
            Returns portal members list with current instance access level checking.

            Arguments:

                'access' -- allowed access levels, String ('RW')

            Results:

                Members with given access level, List.
        """
        users = []
        members = self.listMemberIds()
        try:
            instance = getToolByName( self, 'portal_properties' ).instance_name()
        except:
            return members

        allowed_access_levels = access or portalConfiguration.getAccessLevels( simple=1 )

        for id in members:
            if not id:
                continue
            member = self.getMemberById( id )
            if member is None:
                continue
            if not instance:
                access_level = ( member.IsAdmin() or member.IsManager() ) and 'W' or None
            else:
                access_level = member.getMemberAccessLevel( instance )
            if access_level and access_level in allowed_access_levels:
                users.append(id)

        return users

    security.declarePublic('listMembers')
    def listMembers( self, letter=None, company=None, department=None, mode=None, REQUEST=None ):
        """ 
            Returns portal members list.

            Arguments:

                'letter' -- first letter of user name (family name), string

                'company' -- user's company name, string

                'department' -- user's department name, string

                'mode' -- family name template ('LFM', 'FML'), string.

            Results tuple:

                [0] -- total members

                [1] -- full user's first name sorted list ['A','B','C' ...], in russian

                [2] -- user mapped dictionary list: { 'user_id', 'user_list' } just the same as listSortedUserNames. 
        """
        abc = []
        users = []
        ids = self.listMemberIds()

        for id in ids:
            if not id:
                continue
            member = self.getMemberById( id )
            if member is None:
                continue
            member_name = mode and member.getMemberBriefName( mode ) or member.getMemberName()
            if not member_name:
                continue

            A = member_name[0:1].upper()
            if not A in abc: abc.append(A)

            IsAdd = 1
            if letter:
                IsAdd = letter[0:1].upper() == A and 1 or 0
            if company:
                IsAdd = company == member.getProperty('company', None) and 1 or 0
            if department:
                IsAdd = department == member.getProperty('department', None) and 1 or 0

            if IsAdd: users.append( {'user_id': id, 'user_name': member_name } )

        abc.sort(lambda x, y: cmp(lower(x), lower(y)))
        users.sort(lambda x, y: cmp(lower(x['user_name']), lower(y['user_name'])))

        return ( len(ids), abc, users )

    security.declarePublic('listSortedUserNames')
    def listSortedUserNames( self, ids, mode=None, no_sort=None, contents=None ):
        """ 
            Returns sorted list of user names.

            Arguments:

                ids -- members id list, may be as '__role_:<name>', 'group:<name>', '<name>'

                mode -- member brief name format

                no_sort -- don't sort results

                contents -- structure of results: <id>, <name> simple list or dictionary.
        """
        if not ids: return []

        res_groups = []
        res_members = []
        res_mails = []
        res = []

        msg = getToolByName( self, 'msg' )
        if type(ids) is not ListType and type(ids) is not TupleType:
            ids = [ ids ]

        for id in ids:
            if not id: continue
            if id.startswith('__role_'):
                x = {'user_id': id, 'user_name': '_'+msg('Role')+': '+msg(id[7:]) }
                res_members.append( x )
            elif id.startswith('__edit_role_'):
                x = {'user_id': id, 'user_name': '_'+msg('Edit Role')+': '+msg(id[12:]) }
                res_members.append( x )
            elif id.startswith('group'):
                group_id = id[6:]
                group_title = self.getGroupTitle(group_id)
                if contents == 'id':
                    x = {'user_id': 'group:' + group_title, 'user_name': group_title }
                    res_groups.append( x )
                else:
                    x = {'user_id': id, 'user_name': group_title }
                    res_groups.append( x )
            else:
                member = self.getMemberById( id )
                if member:
                    member_name = mode and member.getMemberBriefName( mode ) or member.getMemberName()
                    x = {'user_id': id, 'user_name': member_name }
                    res_members.append( x )
                else:
                    x = {'user_id': id, 'user_name': id }
                    res_mails.append( x )

            res.append( x )

        if not no_sort:
            res_groups.sort(lambda x, y: cmp(lower(x['user_name']), lower(y['user_name'])))
            res_members.sort(lambda x, y: cmp(lower(x['user_name']), lower(y['user_name'])))
            res_mails.sort(lambda x, y: cmp(lower(x['user_name']), lower(y['user_name'])))

            res = res_mails + res_groups + res_members

        if contents == 'id':
            return map(lambda x: x['user_id'], res)
        elif contents == 'name':
            return map(lambda x: x['user_name'], res)

        return res

    def MemberHasRoleInContext( self, context, user_id, role ):
        """
            Check whether the user has given role in context
        """
        member = self.getMemberById( user_id )
        if member is None:
            return 0
        folder = departmentDictionary.getUserDepartment( self, member )
        return ( \
            role in member.getRolesInContext( context ) or \
            folder is not None and role in member.getRolesInContext( folder ) ) and \
            1 or 0
    #
    #   Interface Preferences functions ==========================================================================
    #
    def setMemberProperties( self, member=None, name=None, value=None ):
        if member is None:
            member = self.__getMember().getUserName()
        mp = getattr( self, 'member_properties', None )
        if mp is None:
            return
        mp.setValue( self, member, name, value )

    def getMemberProperties( self, member=None, name=None, default=None ):
        if member is None:
            member = self.__getMember().getUserName()
        mp = getattr( self, 'member_properties', None )
        if mp is None:
            return default
        if mp.hasValue( member, name ):
            return mp.getValue( member, name, default )
        elif name:
            if type(self._default_properties[name]) is DictType:
                return self._default_properties[name].copy()
            return self._default_properties.get(name)
        else:
            return default

    security.declarePublic( 'setInterfacePreferences' )
    def setInterfacePreferences( self, REQUEST=None ):
        """
            Set the member's interface preferences
        """
        if REQUEST is None:
            return

        property_name = 'interfacePreferences'
        preferences = self.getMemberProperties( name=property_name, default={} )
        IsRun = 0

        for key in self._default_properties.get(property_name).keys():
            IsChanged = 0
            value = None

            if REQUEST.has_key(key):
                value = REQUEST.get(key)
                if not preferences.has_key(key) or value != preferences[key]:
                    preferences[key] = value
                    IsChanged = 1
            else:
                if preferences[key] is not None:
                    preferences[key] = None
                    IsChanged = 1

            if IsChanged:
                portal_log( self, 'MembershipTool', 'setInterfacePreferences', 'key %s:[%s]' % ( key, value ) )
                IsRun = 1

        if IsRun:
            self.setMemberProperties( name='interfacePreferences', value=preferences )

    security.declarePublic( 'getInterfacePreferences' )
    def getInterfacePreferences( self, name=None ):
        """
            Returns the member's interface preferences
            If 'name' is None, the whole settings map is returned.
        """
        property_name = 'interfacePreferences'
        preferences = self.getMemberProperties( name=property_name, default={} )

        if name:
            if not preferences.has_key(name):
                return self._default_properties[property_name].get(name)
            else:
                return preferences.get(name)

        return preferences
    #
    #   Task templates support functions =========================================================================
    #
    security.declarePublic( 'saveTaskTemplate' )
    def saveTaskTemplate( self, template_id=None, template_name='', supervisors='', users=[] ):
        """
            Save task Template for current user.
        """
        taskTemplates = self.getMemberProperties( name='taskTemplates', default={} )

        if not template_id:
            template_id = str(randrange(1, 2000000000))
            while taskTemplates.has_key(template_id):
                template_id = str(randrange(1, 2000000000))

        taskTemplates[ template_id ] = { 'name' : template_name, 'responsible_users' : users, 'supervisors' : supervisors }
        self.setMemberProperties( name='taskTemplates', value=taskTemplates )

        return template_id

    security.declarePublic( 'deleteTaskTemplate' )
    def deleteTaskTemplate( self, template_id ):
        """
            Remove task template with given template_id.
        """
        taskTemplates = self.getMemberProperties( name='taskTemplates', default={} )
        if not taskTemplates.has_key(template_id):
            return

        del taskTemplates[ template_id ]
        self.setMemberProperties( name='taskTemplates', value=taskTemplates )

    security.declarePublic( 'getTaskTemplate' )
    def getTaskTemplate( self, template_id ):
        """
            Return task template having template_id, if not exists - return empty template.
        """
        res_template = { 'name' : '', 'responsible_users' : [], 'supervisors' : [] }
        taskTemplates = self.getMemberProperties( name='taskTemplates', default={} )

        if not taskTemplates:
            return res_template

        if template_id and taskTemplates.has_key(template_id):
            res_template = taskTemplates[ template_id ]

        return res_template

    security.declarePublic( 'listTaskTemplates' )
    def listTaskTemplates( self ):
        """
            Return all task templates for current user
        """
        x = self.getMemberProperties( name='taskTemplates', default={} )
        if x.has_key('supervisor'):
            x['supervisors'] = x['supervisor']
            del x['supervisor']
            self.setMemberProperties( name='taskTemplates', value=x )
        return x

    security.declarePublic( 'processTemplateActions' )
    def processTemplateActions( self, REQUEST ):
        """
            Function for processing all template form actions
        """
        come_from_doc_confirmation_form = REQUEST.get('from_document_confirmation') is not None
        action = str(REQUEST.get('template_action', ''))

        if action == 'save_template':
            template_id = REQUEST.get('template_list', None)
            template_name = REQUEST.get('template_name', '')
            if come_from_doc_confirmation_form:
                membership = getToolByName( self, 'portal_membership' )
                template = membership.getTaskTemplate(template_id)
                # leave old value of supervisors, because we dont change them
                supervisors = template['supervisors']
                involved_users = REQUEST.get('requested', [])
            else:
                supervisors = REQUEST.get('supervisors', [])
                involved_users = REQUEST.get('involved', [])

            if template_name and involved_users:
                self.saveTaskTemplate( template_id, template_name, supervisors, involved_users )

        elif action == 'create_new_template':
            template_name = REQUEST.get('template_name', '')
            supervisors = REQUEST.get('supervisors', [])
            if come_from_doc_confirmation_form:
                involved_users = REQUEST.get('requested', [])
            else:
                involved_users = REQUEST.get('involved', [])
            if template_name and involved_users:
                self.saveTaskTemplate( None, template_name, supervisors, involved_users )

        elif action == 'delete_template':
            self.deleteTaskTemplate( REQUEST.get('template_list', None) )

        brains_type = REQUEST.get('brains_type', None)

        if REQUEST['URL2'] == self.portal_url():
            url = self.portal_url() + '/storage'
        elif come_from_doc_confirmation_form:
            url = REQUEST['URL2'] + '/document_confirmation_form'
        else:
            url = REQUEST['URL2'] + '/task_add_form'
        if brains_type:
            url += '?brains_type=' + brains_type

        REQUEST.RESPONSE.redirect( url )
    #
    #   Filter suport functions ==================================================================================
    #
    def saveFilter( self, filter_id=None, filter_name='', folderFilter='', user_name=None ):
        filters = self.getMemberProperties( member=user_name, name='filters', default={} )

        if not filter_id:
            while 1:
                filter_id = str(randrange(1, 2000000000))
                if not filters.has_key(filter_id):
                    break

        filters[ filter_id ] = { 'filter' : folderFilter, 'name' : filter_name }
        self.setMemberProperties( member=user_name, name='filters', value=filters )
        # if this is first filter make it as main filter
        if len(filters.keys()) == 1:
            self.setMemberProperties( member=user_name, name='main_filter_id', value=filter_id )

        return filter_id

    def deleteFilter( self, filter_id ):
        """
            Delete fiter with filter_id
        """
        filters = self.getMemberProperties( name='filters', default={} )
        if not filters.has_key(filter_id):
            return

        del filters[ filter_id ]
        self.setMemberProperties( name='filters', value=filters )

        # if this is main filter make other filter as main
        main_filter_id = self.getMemberProperties( name='main_filter_id' )
        if main_filter_id != filter_id:
            return

        main_filter_id = len(filters) > 0 and filters.keys()[0] or None
        self.setMemberProperties( name='main_filter_id', value=main_filter_id )

    def setMainFilter( self, filter_id ):
        """
            Set filter with filter_id as main filter
        """
        filters = self.getMemberProperties( name='filters', default={} )
        if filters.has_key(filter_id):
            self.setMemberProperties( name='main_filter_id', value=filter_id )

    security.declarePublic( 'listFilters' )
    def listFilters( self ):
        # return list of filtres in format: [[filter_id, filter_name], ...]
        result_list = []
        filters = self.getMemberProperties( name='filters', default={} )
        for id, item in filters.items():
            result_list.append( { 'id' : id, 'name' : item['name'] } )
        return result_list

    security.declarePublic( 'isMainFilterId' )
    def isMainFilterId( self, filter_id='' ):
        """
            Returns truth if filter with filter_id is main filter
        """
        main_filter_id = self.getMemberProperties( name='main_filter_id' )
        return main_filter_id == filter_id

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setDefaultFilters' )
    def setDefaultFilters( self, user_name=None ):
        """
            Set default filters to user 'user_name' and deletes other filters of user 'user_name'
        """
        for item in self.listFilters():
            self.deleteFilter( item['id'] )

    security.declarePublic( 'getFilter' )
    def getFilter( self, REQUEST ):
        # return current selected filter as dictionary with format
        # {'name':filter_name, 'filter':filter_content}
        # if hasn't current filter - return main filter and make it as current
        filters = self.getMemberProperties( name='filters', default={} )
        res_filter = { 'name' : '', 'filter' : '' }

        if not ( filters and GetSessionValue( self, 'filter_is_on', None, REQUEST, cookie=1 ) ):
            return res_filter

        currFilterId = GetSessionValue( self, 'current_filter_id', 0, REQUEST )
        if not ( currFilterId and filters.has_key( currFilterId ) ):
            currFilterId = self.getMemberProperties( name='main_filter_id' )
            if currFilterId:
                SetSessionValue( self, 'current_filter_id', currFilterId, REQUEST )

        return filters[ currFilterId ]

    security.declarePublic( 'processFilterActions' )
    def processFilterActions( self, REQUEST ):
        """
            This function for processing all filter form actions uses '*.x' REQUEST keys from input 'image' elements
        """
        filter_id = GetSessionValue( self, 'current_filter_id', 0, REQUEST )
        msg = getToolByName( self, 'msg' )
        qs = REQUEST.get('qs', None)
        view_type = REQUEST.get('view_type', 'default')

        if REQUEST.get('save_filter.x') or REQUEST.get('action_save_filter'):
            filter_name = REQUEST.get('filter_name') or msg('Default filter')
            folderFilter = self.encodeFolderFilter(REQUEST)
            self.saveFilter(filter_id, filter_name, folderFilter)

            if REQUEST.get('set_main_filter', 0):
                self.setMainFilter( filter_id )

        elif REQUEST.get('create_new_filter.x'):
            name = REQUEST.get('filter_name') or None
            name = getNextTitle( name or msg('Filter'), [ item['name'] for item in self.listFilters() ] )
            folderFilter = self.encodeFolderFilter( REQUEST )
            filter_id = self.saveFilter( None, name, folderFilter )

            if filter_id:
                SetSessionValue( self, 'current_filter_id', filter_id, REQUEST )
                qs = 1

        elif REQUEST.get('load_filter.x'):
            SetSessionValue( self, 'filter_is_on', 1, REQUEST, cookie=1 )
            filter_id = REQUEST.get('filterList')

            if filter_id:
                SetSessionValue( self, 'current_filter_id', filter_id, REQUEST )
                qs = 1

        elif REQUEST.get('delete_filter.x'):
            self.deleteFilter( filter_id )
            SetSessionValue( self, 'current_filter_id', 0, REQUEST )
            qs = 1

        elif REQUEST.get('open_filter_form.x') or REQUEST.get('open_filter_form'):
            #REQUEST.RESPONSE.setCookie('filter_is_on', '1', path='/', expires='Wed, 19 Feb 2020 14:28:00 GMT')
            #REQUEST.RESPONSE.setCookie('show_filter_form', '1', path='/', expires='Wed, 19 Feb 2020 14:28:00 GMT')
            SetSessionValue( self, 'filter_is_on', 1, REQUEST, cookie=1 )
            SetSessionValue( self, 'show_filter_form', 1, REQUEST, cookie=1 )

        elif REQUEST.get('close_filter_form.x'):
            #REQUEST.RESPONSE.expireCookie('show_filter_form', path='/')
            ExpireSessionValue( self, 'show_filter_form', REQUEST, cookie=1 )

        elif REQUEST.get('disable_filter.x'):
            #REQUEST.RESPONSE.expireCookie('filter_is_on', path='/')
            #REQUEST.RESPONSE.expireCookie('show_filter_form', path='/')
            ExpireSessionValue( self, 'filter_is_on', REQUEST, cookie=1 )
            ExpireSessionValue( self, 'show_filter_form', REQUEST, cookie=1 )
            qs = 1

        params = '?view_type=%s%s' % ( view_type, qs and '&qs=%s' % qs or '' )

        if REQUEST['URL2'] == self.portal_url():
           REQUEST.RESPONSE.redirect( '%s%/storage%s#filter' % ( self.portal_url(), params ) )
        else:
           REQUEST.RESPONSE.redirect( '%s/%s#filter' % ( REQUEST['URL2'], params ) )
    #
    #   Folder views support functions ===========================================================================
    #
    security.declarePublic( 'listFolderViews' )
    def listFolderViews( self ):
        folder_views = self.getMemberProperties( name='folder_views', default={} )
        return folder_views.keys()

    security.declarePublic( 'setFolderView' )
    def setFolderView( self, view_name='', REQUEST=None ):
        """ 
            Function for setting current folder view 
        """
        folder_views = self.getMemberProperties( name='folder_views' )

        if folder_views.has_key(view_name):
            self.setMemberProperties( name='current_folder_view', value=view_name )

        if REQUEST is not None:
           qs = REQUEST.get('qs', 0)
           if qs == 'undefined':
               qs = 0
           if REQUEST['URL2'] == self.portal_url():
              REQUEST.RESPONSE.redirect(self.portal_url() + '/storage/folder_contents?qs=' + str(qs))
           else:
              REQUEST.RESPONSE.redirect(REQUEST['URL2'] + '/folder_contents?qs=' + str(qs))

    security.declarePublic( 'getCurrentFolderView' )
    def getCurrentFolderView( self ):
        current_folder_view = self.getMemberProperties( name='current_folder_view', default='default' )
        return current_folder_view

    security.declarePublic( 'setCurrFolderViewParam' )
    def setCurrFolderViewParam( self, param_name='', param_value='', REQUEST=None ):
        """
            Function for setting current folder view param value
        """
        current_folder_view = self.getMemberProperties( name='current_folder_view' )
        folder_views = self.getMemberProperties( name='folder_views' )

        if folder_views[ current_folder_view ].has_key(param_name):
            folder_views[ current_folder_view ][ param_name ] = param_value
            self.setMemberProperties( name='folder_views', value=folder_views )

        if REQUEST is not None:
            REQUEST.RESPONSE.redirect(REQUEST['URL2'] + '/')

    security.declarePublic( 'getCurrFolderViewParam' )
    def getCurrFolderViewParam( self, param_name ):
        # XXX
        current_folder_view = self.getMemberProperties( name='current_folder_view' )
        folder_views = self.getMemberProperties( name='folder_views' )

        if folder_views[ current_folder_view ].has_key(param_name):
            return folder_views[ current_folder_view ][ param_name ]

        return ''
    #
    #   Navigator's expanded folder view support functions =======================================================
    #
    security.declarePublic( 'getExpandedFolders' )
    def getExpandedFolders( self ):
        expanded_folders = self.getMemberProperties( name='expanded_folders', default=[] )
        return expanded_folders

    security.declarePublic( 'setExpandedFolders' )
    def setExpandedFolders( self, REQUEST=None ):
        pass

    security.declarePublic( 'getLanguage' )
    def getLanguage( self, preferred=None, REQUEST=None ):
        """
            Returns selected language for the current user.
        """
        if not preferred:
            REQUEST = REQUEST or aq_get( self, 'REQUEST', None )
            lang = REQUEST and REQUEST.get('LOCALIZER_LANGUAGE')
            if lang and getLanguageInfo( lang, None ):
                return lang

        return self.getAuthenticatedMember().getProperty( 'language', None ) \
            or getToolByName( self, 'msg' ).get_default_language()

    security.declareProtected( CMFCorePermissions.SetOwnProperties, 'setMemberLanguage' )
    def setMemberLanguage( self, lang ):
        """
            Changes language for the current user.
        """
        if lang:
            member = self.getAuthenticatedMember()
            member.setProperties( language=lang )

    security.declarePublic( 'getFontFamily' )
    def getFontFamily( self, style='general', REQUEST=None ):
        """
            Returns font names by style for the current language.
        """
        lang = self.getLanguage( REQUEST=REQUEST )
        return getLanguageInfo( lang ).get( style+'_font', '' )
    #
    #   Different useful functions ===============================================================================
    #
    security.declarePublic('convertToList')
    def convertToList( self, obj ):
        if not obj: return []
        elif type(obj)==type(''): return [obj]
        return obj

    def __getMember( self, user_name=None ):
        """
            This function return current authorized member and add to member, if it needed, some params
        """
        if user_name is None:
            m = self.getAuthenticatedMember()
        else:
            m = self.getMemberById( str(user_name) )
        if aq_base( m ) is nobody:
            return m
        member = m.getUser()
        return member

    def __checkDocumentForAction( self, doc ):
        """
            This function return True, if current user is site admin or has role 'Editor' for this document,
            else return False
        """
        member = self.__getMember()
        username = member.getUserName()
        return username in doc.requiredUsers or \
                doc.state=='awaiting' and \
                 ( 'Manager' in member.getRoles() or 'Editor' in doc.getObject().user_roles() )

    security.declarePublic( 'filterDocumentsForAction')
    def filterDocumentsForAction( self, allDocuments ):
        return filter(self.__checkDocumentForAction, allDocuments)
    #
    #   LDAP support =============================================================================================
    #
    security.declareProtected( CMFCorePermissions.ManagePortal, 'getUsersSource' )
    def getUsersSource( self ):
        """
        """
        return self.__getPUS().getUsersType()

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getGroupsSource' )
    def getGroupsSource( self ):
        """
        """
        return self.__getPUS().getGroupsType()

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setUsersSource' )
    def setUsersSource( self, auth ):
        """
        """
        return self.__getPUS().setSourceFolder( auth, users=1 )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setGroupsSource' )
    def setGroupsSource( self, auth ):
        """
        """
        return self.__getPUS().setSourceFolder( auth, groups=1 )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getAuthSettings' )
    def getAuthSettings( self, auth ):
        """
        """
        userfolder = self.__getPUS()

        if auth == 'ldap':
            info = userfolder.getLDAPSettings()
            if info is None:
                info = SimpleRecord( address=None, binduid='', read_only=1 )
        else:
            info = SimpleRecord()

        info.auth_frontend = userfolder.getProperty('auth_frontend')
        return info

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setAuthSettings' )
    def setAuthSettings( self, auth, data ):
        """
        """
        userfolder = self.__getPUS()
        userfolder._updateProperty( 'auth_frontend', data.auth_frontend )

        try:
            userfolder.getSourceFolder( auth )
        except ValueError:
            userfolder.createAuthFolder( auth )

        if auth == 'ldap':
            userfolder.setLDAPSettings( data )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setPropertiesMapping' )
    def setPropertiesMapping( self, auth, mapping ):
        """
        """
        userfolder = self.__getPUS()
        if auth == 'ldap':
            userfolder.setLDAPSchemaMapping( mapping )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'changePropertyMapping' )
    def changePropertyMapping( self, auth, id, title='', property=None ):
        """
        """
        userfolder = self.__getPUS()
        if auth == 'ldap':
            userfolder.changeLDAPSchemaAttribute( id, title, property )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'refreshUserRecords' )
    def refreshUserRecords( self ):
        """
        """
        self.__getPUS().invalidateCache()
    #
    #   In-Progress Settings and Utilities =======================================================================
    #
    def _parseInProgressOptions( self, REQUEST=None ):
        """
            Returns in-progress request options
        """
        group = []
        scale = 0

        if REQUEST is not None:
            period = int(REQUEST.get('period') or 0)
            group = filter( None, uniqueValues( REQUEST.get('group') ) )
            cols = int(REQUEST.get('cols') or 200)
            state = not REQUEST.has_key('archive_search') and 2 or None
        else:
            period = 1
            cols = 200
            state = None

        if not group:
            group = ['all_users']

        portal_info( '%s._parseInProgressOptions' % self.getId(), \
            'period: %s, group: %s, scale: %s, cols: %s, state: %s' % ( \
                period, group, scale, cols, state ) \
            )
        return ( period, group, scale, cols, state )
    #
    #   Docflow Activity Statistics ==============================================================================
    #
    security.declarePrivate( 'updateLoginTime' )
    def updateLoginTime( self, user=None, runtime=None, info=None ):
        """
            Updates member's login time. Invoked during authorisation and getting up a document cooked body.
            Runs importing login_time procedure from MemberData items if it has not been activated before.
        """
        if not user:
            user = self.getAuthenticatedMember().getUserName()
        else:
            user = str(user)

        properties = getToolByName( self, 'portal_properties', None )
        if properties is None or not properties.getProperty('member_activity') or \
            properties.getProperty( 'emergency_service' ):
            return
        REQUEST = aq_get( self, 'REQUEST', None ) or {}
        if REQUEST.get('x_committed') == 1:
            return

        self.member_activity.setValue( self, user, runtime )

        portal_info( 'updateLoginTime', "Authenticate user %s" % ( \
            user + ( runtime and ": [%s]%s" % ( str(runtime)[:12], info and ', %s' % info or '' ) or '' ) ) )

    security.declarePublic('getMemberActivity')
    def getMemberActivity( self, user_id, attr='login_time' ):
        """
            Returns member's activity values such as login_time or activity.
        """
        login_time, activity, user_runtime = self.member_activity.getValue( user_id )

        if attr == 'login_time' or not attr:
            return login_time
        elif attr == 'activity':
            return activity

    security.declarePublic( 'TotalCurrentUsers' )
    def TotalCurrentUsers( self, is_current_date=1 ):
        """
            Returns Total Current Users counter
        """
        total = 0
        current_users = 0

        data = self.member_activity.data()

        for user_id in self.listMemberIds():
            if not user_id in data.keys():
                continue
            login_time, activity, user_runtime = data[user_id]
            if not login_time:
                continue
            if is_current_date is None or is_current_date:
                if login_time.isCurrentDay():
                    current_users += 1
                total += 1
            elif activity > 0:
                total += 1

        return ( total, current_users, )

    security.declarePublic( 'SystemPerfomanceEstimate' )
    def SystemPerfomanceEstimate( self, period=None, today_only=1 ):
        """
            Calculates SPE index.

            Returns:

                activity -- current user's requests count

                t -- activity time in seconds since first daily connection

                spe[1] -- count of user's requests per second

                spe[2] -- average transaction run-time.
        """
        users_activity = self.UsersActivityStatistics( period, today_only )

        now = DateTime()
        start_time = DateTime(now.strftime('%x'))
        activity = 0
        tts = 0
        users_transactions = 0
        runtime = 0

        for item in users_activity:
            if item['login_time'] < start_time:
                start_time = item['login_time']
            if item.has_key('run_time'):
                users_transactions += item['run_time'][0]
                user_runtime = item['run_time'][1]
                if user_runtime:
                    runtime += user_runtime
                    tts += 1
            activity += item['activity']

        t = int((now - start_time) * 86400) * 1.0
        tts = tts * 1.0
        spe1 = t > 0 and round( activity / t, 5 ) or 0
        spe2 = tts > 0 and round( runtime / tts, 2 ) or 0

        return ( activity, int(t), spe1, spe2, users_transactions )

    security.declarePublic( 'UsersActivityStatistics' )
    def UsersActivityStatistics( self, period=None, today_only=None, brief=None ):
        """
            Returns member's activity statistics list.

            Arguments:

                period -- integer or string, quantity in seconds of activity (0 - 90000, 0 - any time), number.
        """
        users_activity = []

        if period is None:
            period = 10
        elif type(period) is StringType:
            if len(period) > 5:
                period = '0'
            period = int(period)

        if period > 90000 or period < 0:
            period = 0

        now = DateTime()
        today = DateTime(now.strftime('%Y/%m/%d')) # '%x'

        data = self.member_activity.data()

        for user_id in self.listMemberIds():
            if not user_id in data.keys():
                continue

            member = self.getMemberById( user_id )
            login_time, activity, user_runtime = data[user_id]

            if member is None or not login_time:
                continue
            if today_only and login_time < today:
                continue

            time_after = now - float(period * 60) / 86400

            if period == 0 or period > 0 and login_time > time_after and activity > 0:
                users_activity.append( {
                    'user_id'    : user_id,
                    'user_name'  : not brief and member.getMemberBriefName('LFM') or None,
                    'activity'   : activity,
                    'login_time' : login_time,
                    'run_time'   : user_runtime
                } )

        return users_activity

    def getMembersActivityStatistics( self, REQUEST=None ):
        """
            Returns member's activity statistics for portal instances
        """
        if REQUEST is None:
            REQUEST = check_request( self, REQUEST )

        period, group, scale, cols, state = self._parseInProgressOptions( REQUEST )

        date_mask = '%Y/%m/%d %H:%M'
        time_mask = '%H:%M'

        services = getToolByName( self, 'portal_services', None )
        if services is not None:
            IsError, res = services.sync_property( 'get_activity_stat', state, 'portal_membership', 1, \
                1, period, group \
            )
        else:
            IsError = None
            res = []

        res.append( self.get_activity_stat( 0, period, group )[1] )

        docflow_info = [ ('Member', 'Docflow Instance', 'Total activity', 'Activity diagram', 'Last login time', ), \
                          [], \
                         ('Total', 'Total users', 'Total active users', 'Total current users', \
                          'Portal activity', 'Created documents', \
                          "SPE1 (count of user's requests per second)", "SPE2 (average transaction run-time)", \
                          'Users transactions', 'Conflict errors',), \
                          [], \
                          [], \
                          [], \
                        ]
        values = {}
        total_instances = len(res)
        counter = 0
        total_users = len(self.listMemberIds())
        total_active_users = 0
        users = 0
        activity = spe1 = ratio = spe2 = users_transactions = 0
        errors = []
        n = -1

        for i, x, t, c, u, s, e in res:
            n += 1
            docflow_info[1].append(i) # Docflow Instance
            docflow_info[3].append(t) # Total
            for m, v in x.items():
                if not values.has_key(m):
                    values[m] = [ (0, '', None) for r in range(total_instances) ]
                    total_active_users += 1
                values[m][n] = v      # Member values
            users += u[1]             # Total current users
            activity += s[0]          # Activity & SPE
            spe1 = ( spe1 + s[2] ) / 2
            ratio += s[2]
            spe2 = ( spe2 + s[3] ) / 2
            counter += c              # Created documents
            users_transactions += s[4]
            errors.append(e)          # Conflict errors

        spe1 = ( spe1, int(round( ratio*60 )) )
        docflow_info[5].append( ( total_users, total_active_users, users, activity, counter, spe1, spe2, users_transactions, errors ) )

        total = 0                     # Total activity & Last login time
        last_login = ''
        value_min = 1000
        value_max = 0

        for x in values.keys():
            s = sum([ v[0] for v in values[x] ])
            l = max([ v[1] for v in values[x] ])
            last_login = max(l, last_login)
            values[x] = [ v[0] for v in values[x] ]
            values[x].append(s)
            values[x].append(DateTime(l).strftime(date_mask))
            if not s:
                continue
            if s < value_min: value_min = s
            if s > value_max: value_max = s
            total += s
        docflow_info[3].append( total )
        docflow_info[3].append( last_login and DateTime(last_login).strftime(time_mask) or '-' )

        values = values.items()       # Sorting (by activity)
        values.sort( lambda x, y: cmp(x[1][-2:][0], y[1][-2:][0]) )
        values.reverse()

        res = []                      # Activity diagram     
        threshold = 0
        step = int(value_max/cols) + 1

        docflow_info[4].append( ( value_min, value_max, step, threshold ) )

        colors = CustomPortalColors()
        default_color = '#4F4FFF'

        for key, value in values:
            diagram = []
            if value[-2:][0] > 0:
                for i in range(len(value[:-1])):
                    x = int(value[i]/step)
                    if i < total_instances:
                        t = docflow_info[1][i]
                        c = colors[t][5]
                        h = 1
                        p = None
                    else:
                        t = 'total'
                        c = default_color
                        h = 10
                        p = range(int(x/10))
                    diagram.append( { 'value':x, 'title':t, 'color':c, 'height':h, 'preview':p } )
                diagram = tuple(diagram)
            try:
                name = self.getMemberById(key).getMemberBriefName('LFM')
            except:
                name = key
            res.append( { 'key':key, 'name':name, 'value':value, 'diagram':diagram, 'scale':scale } )

        del values

        return ( total, docflow_info, res, IsError, )

    def get_activity_stat( self, mode, period, group ):
        """
            Returns counters of members group activity
        """
        res = {}
        IsError = 0

        portal = self.getPortalObject()
        instance = portal.getId()

        total = 0
        today_only = period == 1 and 1 or None
        users_activity = self.UsersActivityStatistics( period=0, today_only=today_only, brief=1 )

        for x in users_activity:
            user_id = x['user_id']
            for id in group:
                members = self.getGroupMembers( id, sort=1 )
                if user_id not in members or user_id in res.keys():
                    continue
                res[user_id] = ( x['activity'], str(x['login_time']), x['run_time'] )
                total += x['activity']

        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is not None:
            kw = {}
            kw['created'] = { 'query' : DateTime().strftime('%Y/%m/%d'), 'range':'min' }
            counter = catalog.countResults( REQUEST=None, implements='isHTMLDocument', **kw )
        else:
            counter = 0

        total_current_users = self.TotalCurrentUsers()
        spe = self.SystemPerfomanceEstimate( period=0, today_only=1 )

        from Zope2.App.startup import conflict_errors

        return ( IsError, ( instance, res, total, counter, total_current_users, spe, conflict_errors, ), )
    #
    #   Public membership helper functions =======================================================================
    #
    def getMemberGroupList( self, id=None ):
        """
            Returns member's group list, where user with given id is a member
        """
        results = []

        if id is None:
            member = self.getAuthenticatedMember()
        else:
            member = self.getMemberById( id )

        if member is None:
            return results

        for group in self.listGroups():
            group_id = group.getId()
            if not group_id:
                continue
            if member.isMemberOfGroup(group):
                results.append(group_id)

        return results

    def listAllowedUsersForRole( self, role_id ):
        """
            List of users for role id
        """
        if not role_id:
            return None
        elif role_id in ['SignatureRequest','Chief_Department']:
            return self.listAllowedUsersForSignatureRequest( context=self )
        elif role_id == 'Resolution':
            return self.listAllowedUsersForResolution()
        elif role_id == 'DeliverExecution':
            return self.listAllowedUsersForDeliverExecution()
        return None

    def listAllowedGroupsForSignatureRequest( self ):
        """
            List of groups with signing permission
        """
        results = []
        for group in self.listGroups():
            group_id = group.getId()
            group_title = self.getGroupTitle( group_id )
            if group_title.startswith('sys:'):
                continue
            if self.getGroupAttribute( group_id, attr_name='DA' ):
                results.append( { 'group_id' : group_id, 'group_title' : group_title } )
                
        return results

    def listAllowedUsersForSignatureRequest( self, context, department=None, check_groups=1, local_only=0 ):
        """
            Returns list of users with signing permission. Checks member's department folder to have signing roles.
            By default Editor and Writer in current context have permissions.

            We look inside another department folders where current user is a member and check signing role there.

            Arguments:

                'context' -- document object for signing

                'department' -- member's department folder object

                'check_groups' -- Boolean, by default used to view SD-groups list to check permissions 
                        for current member if he is included inside theirs. 

                'local_only' -- Boolean, applies only local folder roles or inherited folders tree.

            Results:

                List of members id.
        """
        signing_roles = ['Editor','Writer']
        member = self.getAuthenticatedMember()
        results = [ member.getUserName() ]

        if department is not None:
            users = self.listAllowedUsers( department, signing_roles, local_only=local_only )
            if users:
                for user in users:
                    if user and user not in results:
                        results.append( user )

        if results and not check_groups:
            return results

        if context is None:
            return results

        for group in self.listGroups():
            group_id = group.getId()
            if not group_id:
                continue
            if group_id[0:1] == '_' or group_id in ['all_users'] or not group.getGroupAttribute( group_id, attr_name='SD' ):
                continue
            if member.isMemberOfGroup( group ):
                folder = departmentDictionary.getSubFolderById( context, None, group_id )
                if folder is None:
                    continue
                users = self.listAllowedUsers( folder, signing_roles, local_only=local_only )
                for user in users:
                    if user and user not in results:
                        results.append( user )

        for user in self.listGroupMembers( group='_SIGN_', member=0 ):
            if user not in results:
                results.append( user )

        for x in self.getListGroups( attr=['CH'], sys=1 ):
            for user in self.listGroupMembers( group=x['group_id'], member=0 ):
                if user not in results:
                    results.append( user )

        if 'admin' in results: results.remove('admin')
        return results

    def listAllowedUsersForResolution( self, member=None ):
        """
            List of users with resolution permission
        """
        results = []
        member, uname = self.validateMember( member )
        if member is None:
            return None

        for group_id in self.getMemberGroupList( id=uname ):
            group = self.getGroup(group_id)
            if not group_id:
                continue
            if group_id[0:1] == '_' or group_id in ['all_users'] or not group.getGroupAttribute( group_id, attr_name='DA' ):
                continue
            results.append( 'group:%s' % group_id )

        return results

    def listAllowedUsersForDeliverExecution( self, member=None ):
        """
            List of users which authenticated member can deliver execution
        """
        results = []
        member, uname = self.validateMember( member )
        if member is None:
            return None

        for group_id in self.getMemberGroupList( id=uname ):
            group = self.getGroup(group_id)
            if not group_id:
                continue
            if group_id[0:1] == '_' or group_id in ['all_users'] or not group.getGroupAttribute( group_id, attr_name='SD' ):
                continue

            for user in self.getGroupMembers(group_id):
                if user and user not in results and user != uname:
                    results.append( user )

        return results

    def getGroupOrMemberName( self, id ):
        if not id: return ''
        if id[:5] == 'group':
            name = self.getGroupTitle( id[6:] )
        else:
            member = self.getMemberById( id )
            try: name = ('%s %s' % ( member.getMemberNotes(), member.getMemberBriefName() )).strip()
            except: name = id
        return name

    def listMemberHomeFolders( self, check=None ):
        """
            Returns member personal home folders list to view via members navigator
        """
        instance = getToolByName( self, 'portal_properties' ).instance_name()
        path = '/%s/storage/members' % instance

        try: folder = self.unrestrictedTraverse( path )
        except: folder = None

        if folder is None:
            return None

        objects = folder.objectValues()
        member = self.getAuthenticatedMember()
        members = []
        n = 0

        for obj in objects:
            if obj is None: continue
            if not _checkPermission( CMFCorePermissions.View, obj ): continue
            n += 1
            if check and n > check:
                return n
            try:
                id = obj.getId()
                url = obj.absolute_url() #obj.physical_path()
                title = obj.Title()
            except:
                continue
            #if not url.endswith(id): continue

            p={}
            p['id'] = id
            p['title'] = title
            p['url'] = url
            members.append(p)

        members.sort(lambda x, y: cmp(lower(x['title']), lower(y['title'])))
        return check and len(members) or members
    #
    #   Special extra fuctions ===================================================================================
    #
    def getDate( self, name, REQUEST, default=None ):
        # XXX. Additional function. Returned parsed datetime value
        return parseDate( name, REQUEST, default )

    security.declarePublic( 'protection' )
    def protection( self, context=None, REQUEST=None ):
        """
            Access Level and supervisors protection check
        """
        #username = REQUEST is not None and REQUEST.get('AUTHENTICATED_USER', None) or \
        #    _getAuthenticatedUser(self).getUserName()
        username = self.getAuthenticatedMember().getUserName()
        member = self.getMemberById(username)

        url_protection = '%s/%s' % ( self.portal_url(), 'protection_message?expand=1' )
        url_emergency_service = '%s/%s' % ( self.portal_url(), 'emergency_service_message?expand=1' )

        if member is None:
            #raise Unauthorized
            #portal_info( 'MembershipTool.protection', ( \
            #    'member is unauthorized', context is not None and context.absolute_url(), username ), exc_info=False )
            #return REQUEST.RESPONSE.redirect( url_protection + '&no_member=%s' % username )
            return 1

        try:
            IsManager = member.IsManager()
            IsAdmin = member.IsAdmin()
        except:
            IsManager = IsAdmin = 0

        properties = getToolByName( self, 'portal_properties', None )
        instance = properties.instance_name()

        if not IsAdmin:
            if not instance:
                return REQUEST.RESPONSE.redirect( url_protection + '&no_instance=1' )
            elif REQUEST.get('URL','').find( '%s/%s' % ( instance, instance ) ) > 0:
                return REQUEST.RESPONSE.redirect( url_protection + '&bad_instance=1' )

            if properties.getProperty( 'emergency_service' ):
                return REQUEST.RESPONSE.redirect( url_emergency_service )

            if context is None:
                instance = properties.getProperty( 'instance' )
                if member.getMemberAccessLevel( id=instance ):
                    return 1
                return REQUEST.RESPONSE.redirect( url_protection + '&no_access_level=1' )

        if context == 'password':
            if REQUEST is not None and REQUEST.get('userid', None) and username not in CustomDefs('superusers'):
                return REQUEST.RESPONSE.redirect( url_protection + '&password=1' )
            else:
                return 1

        if not IsAdmin and context is not None:
            if context in ['undo']:
                return 1
            return REQUEST.RESPONSE.redirect( url_protection + '&undo=1' )

        return 1

    security.declarePublic( 'recover' )
    def recover( self, REQUEST=None ):
        """
            Check and take off emergency service. Redirect to home
        """
        properties = getToolByName( self, 'portal_properties', None )
        if properties.getProperty( 'emergency_service' ):
            return 1
        return REQUEST.RESPONSE.redirect( self.portal_url() )

InitializeClass( MembershipTool )
