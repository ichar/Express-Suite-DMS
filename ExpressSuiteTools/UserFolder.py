"""
User Folder class
$Id: UserFolder.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 08/09/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from re import search
from types import StringType, ListType

from Acquisition import aq_base
from AccessControl import ClassSecurityInfo
from AccessControl import Permissions as ZopePermissions
from AccessControl.User import BasicUserFolder

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName

from Products.NuxUserGroups.UserFolderWithGroups import UserFolderWithGroups, BasicGroupFolderMixin, \
     _marker as nux_marker
from DateTime import DateTime

import Config
from Config import Roles
from Exceptions import SimpleError
from SimpleObjects import ContainerBase

from Utils import InitializeClass, cookId

from logging import getLogger
logger = getLogger( 'UserFolder' )

#if Config.UseLDAPUserFolder:
#    from Products.LDAPUserFolder.LDAPUserFolder import LDAPUserFolder


class UserFolder( ContainerBase, BasicUserFolder, BasicGroupFolderMixin ):
    """
        User folder class
    """
    _class_version = 1.0

    id = 'acl_users'
    meta_type = 'DMS Express Suite User Folder'
    title = 'Portal User Folder'
    icon = 'misc_/OFSP/UserFolder_icon.gif'

    isPrincipiaFolderish = BasicUserFolder.isPrincipiaFolderish

    security = ClassSecurityInfo()

    _properties = ContainerBase._properties + (
            { 'id':'auth_frontend',  'type':'boolean', 'mode':'w', 'default':0  },
            { 'id':'managers_group', 'type':'string',  'mode':'w', 'default':'' },
        )

    manage = UserFolderWithGroups.manage
    manage_main = UserFolderWithGroups.manage_main
    manage_options = UserFolderWithGroups.manage_options + ContainerBase.manage_options

    __users_source__ = None
    __groups_source__ = None

    security.declarePublic( 'getUsersType' )
    def getUsersType( self ):
        """
            Returns user folder type
        """
        return _getAuthType( self.__users_source__ )

    security.declarePublic( 'getGroupsType' )
    def getGroupsType( self ):
        """
            Returns group type
        """
        return _getAuthType( self.__groups_source__ )

    security.declarePrivate( 'getSourceFolder' )
    def getSourceFolder( self, auth=None, default=MissingValue, id=None ):
        """
            Returns source folder object
        """
        folder = id and self._getOb( id, None ) or None

        if folder is None and auth:
            folders = self.objectValues( spec=_auth_types[auth]['meta_type'] )
            if folders:
                # TODO handle multiple subfolders of the same type
                folder = folders[0]

        if folder is None:
            if default is MissingValue:
                raise ValueError, id or auth
            return default

        return folder

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setSourceFolder' )
    def setSourceFolder( self, auth=None, id=None, users=None, groups=None ):
        """
            Sets source folder object
        """
        if users is None and groups is None:
            users = groups = 1

        folder = self.getSourceFolder( auth, id=id )
        if folder is None:
            return

        folder = aq_base( folder )
        info = _getAuthInfo( folder )

        # set users source
        ufolder = self.__users_source__
        if users and info['users'] and folder != ufolder:
            ufolder = self.__users_source__ = folder

        # check whether new groups source supports detached groups
        if groups and not info['detached_groups']:
            groups = ( folder.getId() == ufolder.getId() )

        # set groups source
        gfolder = self.__groups_source__
        if groups and info['groups'] and folder != gfolder:
            gfolder = self.__groups_source__ = folder

        # check whether current groups source supports detached groups
        if ufolder != gfolder and not _getAuthInfo( gfolder, 'detached_groups' ):
            # set groups source to either users source or default folder
            if _getAuthInfo( ufolder, 'groups' ):
                self.setSourceFolder( id=ufolder.getId(), groups=1 )
            else:
                # XXX may cause recursion if default type does not support groups
                self.setSourceFolder( 'default', groups=1 )
            gfolder = self.__groups_source__

        # XXX a hack to turn local groups on/off in LDAPUserFolder
        #if _getAuthType( ufolder ) == 'ldap':
        #    ufolder._local_groups = ( ufolder != gfolder )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'createAuthFolder' )
    def createAuthFolder( self, auth=None, id=None ):
        """
            Adds auth folder
        """
        info = _auth_types[auth]
        folder = info['factory']( *info['args'] )
        if folder is None:
            return
        if id:
            folder.id = id # XXX _setId is disabled in BasicUserFolder
        self._setObject( folder.getId(), folder, set_owner=0 )
        return folder.getId()
    #
    #   Implementation of BasicUserFolder methods ================================================================
    #
    def getUserNames( self ):
        if self.__users_source__ is None:
            return None
        return self.__users_source__.getUserNames()

    def getUsers( self ):
        if self.__users_source__ is None:
            return None
        users = self.__users_source__.getUsers()
        self._restoreGroups( users )
        return users

    def getUser( self, name ):
        if self.__users_source__ is None:
            return None
        user = self.__users_source__.getUser( name )
        if user is not None and not hasattr( user, '_usergroups' ):
            self._restoreGroups( [user] )
        return user

    def userFolderAddUser( self, name, password, roles, domains, **kw ):
        """
            API method for creating a new user object
        """
        if not name:
            raise SimpleError, "A username must be specified."

        if self.getUser(name) or ( self._emergency_user and
                                   name == self._emergency_user.getUserName() ):
            raise SimpleError, "A user with the specified name already exists."

        if domains and not self.domainSpecValidate( domains ):
            raise SimpleError, "Illegal domain specification."

        if not roles: roles = []
        if not domains: domains = []

        self._doAddUser( name, password, roles, domains, **kw )

    def _doAddUser( self, name, password, roles, domains, groups=MissingValue, **kw ):
        """
            Creates a new user
        """
        if self.__users_source__ is None:
            return
        users = self.__users_source__
        apply( users._doAddUser, (name, password, roles, domains), kw )
        if groups is not MissingValue:
            self.addGroupsToUser( groups, name )

    def _doChangeUser( self, name, password, roles, domains, groups=MissingValue, **kw ):
        """
            Modifies an existing user
        """
        if self.__users_source__ is None:
            return
        users = self.__users_source__
        # NB the following order is significant for LDAP group-role mapping
        if groups is not MissingValue:
            self.setGroupsOfUser( groups, name )
        apply( users._doChangeUser, (name, password, roles, domains), kw )

    def _doDelUsers( self, names ):
        """
            Deletes one or more users
        """
        if self.__users_source__ is None:
            return
        users = self.__users_source__

        for username in names:
            user = self.getUser( username )
            if user is not None:
                self.delGroupsFromUser( user.getGroups(), username )

        apply( users._doDelUsers, (names,) )

    def authenticate( self, name, password, request ):
        if not name:
            return None

        user = self.getUser( name )
        if user is None or 'Locked' in user.getRoles():
            return None

        if self.auth_frontend and request.environ.get('REMOTE_USER'):
            return user

        user = self.__users_source__.authenticate( name, password, request )
        if user is not None and not hasattr( user, '_usergroups' ):
            self._restoreGroups( [user] )

        return user
    #
    #   Implementation of BasicGroupFolderMixin methods ==========================================================
    #
    def getGroupNames( self ):
        """
            Returns group names list
        """
        groups = ()
        usrc = self.__users_source__
        gsrc = self.__groups_source__

        if gsrc:
            groups = gsrc.getGroupNames()

        if usrc != gsrc and _getAuthInfo( usrc, 'pseudogroups' ) and usrc.enable_pseudogroups:
            groups += usrc.getPseudoGroupNames()

        return groups

    def getGroupById( self, groupname, default=MissingValue ):
        """
            Returns group by given id
        """
        group = None
        usrc = self.__users_source__
        gsrc = self.__groups_source__

        if gsrc:
            group = gsrc.getGroupById( groupname, None )

        if group is None and usrc != gsrc \
                and _getAuthInfo( usrc, 'pseudogroups' ) \
                and usrc.enable_pseudogroups:
            group = usrc.getPseudoGroupById( groupname, None )

        if group is None:
            if default is MissingValue:
                raise KeyError, groupname
            return default

        return group.__of__( self )

    def userFolderAddGroup( self, groupname, title='', **kw ):
        """
            Add group
        """
        if not hasattr( self, '__groups_source__' ):
            raise NotImplementedError, "No groups source defined."
        #if self.__groups_source__ is None:
        #    return

        self.__groups_source__.userFolderAddGroup( groupname, title, **kw )

    def userFolderDelGroups( self, groupnames ):
        """
            Remove groups
        """
        if not hasattr( self, '__groups_source__' ):
            return NotImplementedError, "No groups source defined."
        #if self.__groups_source__ is None:
        #    return

        self.__groups_source__.userFolderDelGroups( groupnames )

    def _restoreGroups( self, users ):
        # LDAP user is not persistent object
        # thus its groups must be restored every time
        groups = {}
        for group in self.getGroupNames():
            groups[ group ] = self.getGroupById( group ).getUsers()
        if not groups:
            return

        for user in users:
            if hasattr( user, '_usergroups' ):
                continue
            name = user.getUserName()
            current = list( user.getGroups() )
            for group, members in groups.items():
                if name in members and group not in current:
                    current.append( group )
            user._setGroups( current )
    #
    #   ItemBase methods =========================================================================================
    #
    def _instance_onCreate( self ):
        if not self.objectIds():
            id = self.createAuthFolder( 'default' )
            self.setSourceFolder( id=id )

    def _containment_onAdd( self, item, container ):
        BasicUserFolder.manage_afterAdd( self, item, container )

    def _containment_onDelete( self, item, container ):
        BasicUserFolder.manage_beforeDelete( self, item, container )
    #
    #   ObjectManager methods ====================================================================================
    #
    def _setObject( self, id, object, roles=None, user=None, set_owner=0 ):
        # XXX a hack to enable multiple userfolders inside
        if id == 'acl_users':
            id = cookId( self, prefix=_getAuthType( object, 'acl' ) )
            # XXX _setId is disabled in BasicUserFolder
            object.id = id

        ContainerBase._setObject( self, id, object, roles, user, set_owner )

    def _delObject( self, id ):
        if self.__users_source__.getId() == id:
            del self.__users_source__

        if self.__groups_source__.getId() == id:
            del self.__groups_source__

        ContainerBase._delObject( self, id )

InitializeClass( UserFolder )


def addUserFolder( dispatcher, id=None, REQUEST=None ):
    """
        Adds a User Folder
    """
    folder = UserFolder()
    id = folder is not None and folder.getId()
    logger.info('addUserFolder id: %s, folder: %s' % ( id, folder ))

    dispatcher.Destination()._setObject( id, folder )

    if REQUEST is not None:
        dispatcher.manage_main( dispatcher, REQUEST )

# mapping: type => info
_auth_types = {}

def registerAuthType( id, **kw ):
    """
        Registers users and/or groups source type
    """
    #print 'registerAuthType', id
    kw.setdefault( 'id', id )
    kw.setdefault( 'args', () )
    kw.setdefault( 'users', 1 )
    kw.setdefault( 'groups', 1 )
    kw.setdefault( 'pseudogroups', 0 )
    kw.setdefault( 'detached_groups', 0 )
    _auth_types[ id ] = kw
    if kw.get('default'):
        _auth_types['default'] = kw
    #print 'OK'

def _getAuthInfo( mtype, prop=None, default=MissingValue ):
    # returns authentication type information by meta type
    if mtype is None:
        mtype = UserFolderWithGroups.meta_type
    elif type(mtype) is not StringType:
        mtype = mtype.meta_type

    for info in _auth_types.values():
        if info['meta_type'] == mtype:
            if prop is None:
                return info
            if info.has_key( prop ):
                return info[ prop ]
            break

    if default is MissingValue:
        raise ValueError, mtype
    return default

def _getAuthType( mtype, default=MissingValue ):
    # returns authentication type ID by meta type
    return _getAuthInfo( mtype, 'id', default )


registerAuthType( 'nux',
        meta_type=UserFolderWithGroups.meta_type,
        detached_groups=1,
        factory=UserFolderWithGroups,
        default=1,
    )
