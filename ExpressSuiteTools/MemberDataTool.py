"""
Member data tool
$Id: MemberDataTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 06/07/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from string import strip
from types import DictType, StringType

from AccessControl import ClassSecurityInfo, Permissions as ZopePermissions
from Acquisition import aq_base, aq_parent
from BTrees.OOBTree import OOBTree

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser, _checkPermission
from Products.CMFCore.MemberDataTool import MemberDataTool as _MemberDataTool, MemberData as _MemberData

import Config
from Config import Roles
from ConflictResolution import ResolveConflict
from SimpleObjects import InstanceBase, ToolBase
from DepartmentDictionary import departmentDictionary

from Utils import InitializeClass, AnonymousUserName

from CustomDefinitions import portalConfiguration

_name_parts = ['fname','mname','lname']


class MemberDataTool( ToolBase, _MemberDataTool ):
    """
        Portal member data
    """
    _class_version = 1.0

    meta_type = 'ExpressSuite Member Data Tool'

    security = ClassSecurityInfo()

    manage_options = _MemberDataTool.manage_options # + ToolBase.manage_options

    _actions = _MemberDataTool._actions + ToolBase._actions

    _properties = _MemberDataTool._properties + (
            # CMF properties
            { 'id':'email',       'type':'string',  'mode':'w', 'default':'', 'title':'E-mail address' },
            { 'id':'portal_skin', 'type':'string',  'mode':'w', 'default':'' },
            { 'id':'listed',      'type':'boolean', 'mode':'w', 'default':'' },
            { 'id':'login_time',  'type':'date',    'mode':'w', 'default':'' },
            { 'id':'activity',    'type':'int',     'mode':'w', 'default':0  },
            # App properties
            { 'id':'fullname',    'type':'string',  'mode':'w', 'default':'', 'title':'Full name'   },
            { 'id':'fname',       'type':'string',  'mode':'w', 'default':'', 'title':'First name'  },
            { 'id':'mname',       'type':'string',  'mode':'w', 'default':'', 'title':'Middle name' },
            { 'id':'lname',       'type':'string',  'mode':'w', 'default':'', 'title':'Last name'   },
            { 'id':'company',     'type':'string',  'mode':'w', 'default':'', 'title':'Company'     },
            { 'id':'notes',       'type':'text',    'mode':'w', 'default':'', 'title':'Notes' },
            { 'id':'phone',       'type':'string',  'mode':'w', 'default':'', 'title':'Phone' },
            { 'id':'rate_sum',    'type':'int',     'mode':'w', 'default':0  },
            { 'id':'rate_users',  'type':'tokens',  'mode':'w', 'default':'' },
            { 'id':'language',    'type':'string',  'mode':'w', 'default':'' },
            { 'id':'department',  'type':'string',  'mode':'w', 'default':'' },
            { 'id':'facsimile',   'type':'string',  'mode':'w', 'default':'' },
        ) + portalConfiguration._instances

    def __init__( self ):
        """
            Initialize class instance
        """
        ToolBase.__init__( self )
        # skip _MemberDataTool.__init__ because it calls _setProperty
        self._members = OOBTree()

    def _p_resolveConflict( self, oldState, savedState, newState ):
        return ResolveConflict( 'MemberDataTool', oldState, savedState, newState, '_members' )

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not ToolBase._initstate( self, mode ):
            return 0

        if self._properties is not self.__class__._properties:
            pdict = self.propdict()
            for prop in self.__class__._properties:
                try:
                    pd = pdict[ prop['id'] ]
                    map( pd.setdefault, prop.keys(), prop.values() )
                except KeyError:
                    self._properties += prop

        if mode > 1:
            members = self._members
            for item in members.keys():
                self._upgrade( item, MemberData, container=members )

        return 1

    security.declarePrivate( 'wrapUser' )
    def wrapUser( self, u ):
        """
            Wraps User object with MemberData object.

            Arguments:

                'u' -- User object.

            Result:

                Wrapped user object.
        """
        id = u.getUserName()
        members = self._members
        if not members.has_key(id):
            # Get a temporary member that might be
            # registered later via registerMemberData().
            temps = self._v_temps
            if temps is not None and temps.has_key(id):
                m = temps[id]
            else:
                base = aq_base(self)
                m = MemberData(base, id)
                if temps is None:
                    self._v_temps = {id:m}
                else:
                    temps[id] = m
        else:
            m = members[id]

        # Create a wrapper with self as containment and
        # the user as context.
        wrapper = m.__of__(self).__of__(u)
        # update wrapper properties from LDAP attributes
        wrapper._updateProperties()

        return wrapper

InitializeClass( MemberDataTool )


class MemberData( InstanceBase, _MemberData ):
    """
        Portal Member object keeps user's settings
    """
    _class_version = 1.0

    meta_type = 'Member Data'

    security = ClassSecurityInfo()

    # restore method overridden by PropertyManager in InstanceBase
    getProperty = _MemberData.getProperty

    def __init__( self, tool, id ):
        """
            Initialize class instance
        """
        InstanceBase.__init__( self )
        _MemberData.__init__( self, tool, id )

    ### New user object interface methods ###

    def _updateProperties( self ):
        # copies property values from the underlying user object
        # (such as LDAPUser) into the member data
        user = self.getUser()
        userfolder = aq_parent( user )

        if not hasattr( aq_base(userfolder), 'getMappedUserProperties' ):
            return

        mapped = userfolder.getMappedUserProperties()
        tool = self.getTool()

        for prop in mapped:
            # get the property value from LDAPUser object
            value = user.getProperty( prop, None )
            if value is None:
                # try to obtain default value
                value = tool.getProperty( prop )

            # redefine the wrapper value only if it differ
            old = getattr( aq_base(self), prop, None )
            if value is None or value == old:
                continue

            # store new value in the wrapper
            setattr( self, prop, value )

            # special handling for some attributes
            # XXX conflict when both fullname and f/m/l-names are given ?
            if prop == 'fullname':
                for name, value in zip( _name_parts, _parseFullName( value ) ):
                    setattr( self, name, value )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setMemberProperties' )
    def setMemberProperties( self, mapping ):
        """
            Sets the properties of the member.

            Arguments:

                'mapping' -- member's properies dictionary like { prop : value }. 
                 May be a REQUEST.
        """
        user = self.getUser()
        userfolder = aq_parent( user )

        if hasattr( aq_base(userfolder), 'getMappedUserProperties' ):
             mapped = userfolder.getMappedUserProperties()
        else:
             mapped = ()

        if mapped:
            updated = {}

            for prop in mapped:
                try:
                    value = mapping[ prop ]
                except KeyError:
                    continue

                old = self.getProperty( prop, None )
                if value != old:
                    updated[ prop ] = value

            if not updated.has_key('fullname'):
                parts = [ mapping.get( prop, '' ) for prop in ['fname','mname','lname'] ]
                value = _formatFullName( parts )
                if value:
                    updated['fullname'] = value

            if updated:
                userfolder.setUserProperties( self.getUserName(), updated )

        _MemberData.setMemberProperties( self, mapping )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setSecurityProfile' )
    def setSecurityProfile( self, password=None, roles=None, domains=None ):
        """
            Sets the user's basic security profile.
        """
        user = self.getUser()
        userfolder = aq_parent( user )

        if roles is None:
            roles = user.getRoles()
        if domains is None:
            domains = user.getDomains()

        userfolder.userFolderEditUser( user.getUserName(), password, roles, domains )

    security.declarePublic('isAnonymousUser')
    def isAnonymousUser( self ):
        return self.getUser().getUserName() == 'Anonymous User' and 1 or 0

    security.declarePublic('getMemberName')
    def getMemberName( self ):
        """
            Returns a full name of the user.

            Result:

                String.
        """
        if self.isAnonymousUser():
            return AnonymousUserName( self )
        parts = [ self.getProperty(p) for p in ('fname','mname','lname') ]
        return _formatFullName( parts, canonical=0 ) or self.getUserName()

    security.declarePublic('getMemberBriefName')
    def getMemberBriefName( self, mode=None ):
        """
            Returns a brief name of the user.

            Result:

                String.
        """
        if self.isAnonymousUser():
            return AnonymousUserName( self )
        parts = [ self.getProperty(p) for p in ('fname','mname','lname') ]
        return _formatBriefName( parts, mode=mode ) or self.getUserName()

    security.declarePublic('getMemberEmail')
    def getMemberEmail( self ):
        """
            Returns the user's email address.

            Result:

                String.
        """
        return self.getProperty('email') or self.getMemberId()

    security.declarePublic('hasHomeCompany')
    def hasHomeCompany( self, mode=None ):
        """
            Checks if member has a home company
        """
        try:
            home_company = self.getHomeFolder().getNomenclativeNumber()
        except:
            home_company = None
        return home_company and departmentDictionary.getCompanyTitle( home_company ) and 1 or 0

    security.declarePublic('getMemberCompany')
    def getMemberCompany( self, mode=None ):
        """
            Returns a company of the user.

            Result:

                String.
        """
        try:
            home_company = self.getHomeFolder().getNomenclativeNumber()
        except:
            home_company = None
        company = home_company or self.getProperty('company', None)
        if not mode or mode == 'title':
            return departmentDictionary.getCompanyTitle( company )
        else:
            return company

    security.declarePublic('getMemberDepartment')
    def getMemberDepartment( self, mode=None ):
        """
            Returns a department of the user.

            Result:

                String.
        """
        department = self.getProperty('department', None)
        if not mode or mode == 'title':
            return departmentDictionary.getDepartmentTitle( department )
        elif mode in ['context','folder']:
            return departmentDictionary.getSubFolderById( self, id=department )
        else:
            return department

    security.declarePublic('getMemberFacsimile')
    def getMemberFacsimile( self, context=None ):
        """
            Returns a facsimile url of the user.

            Arguments:

                'context' -- context to define facsimile language specification.

            Result:

                String.
        """
        facsimile = self.getProperty( 'facsimile', None )
        
        if context is not None:
            language = getattr( context, 'language', '' )
            default_language = getToolByName(self, 'msg').get_default_language()
            postfix = language != default_language and language or ''

            if postfix:
                for x in Config.FacsimileExtensions:
                    #if facsimile.find(x) > 0:
                    facsimile = facsimile.replace( x, '-%s%s' % (postfix,x) )
                    #break

        return facsimile

    security.declarePublic('getMemberNotes')
    def getMemberNotes( self ):
        """
            Returns a notes of the user.

            Result:

                String.
        """
        return self.getProperty('notes', '').strip()

    security.declareProtected( CMFCorePermissions.SetOwnProperties, 'getHomeFolder' )
    def getHomeFolder( self, create=None, no_raise=None, unrestricted=None ):
        """
            Returns the user's home folder, optionally creates it if it does not exist yet.

            Arguments:

                'create' -- Boolean. Indicates whether it is required to create
                            the home folder if it does not exist.

                'no_raise' -- Boolean. No raise error.

            Result:

                Folder object reference.
        """
        portal = getToolByName( self, 'portal_url' ).getPortalObject()
        members = portal['storage']._getOb( 'members', None )
        if members is None:
            if not no_raise:
                raise KeyError, "Members folder does not exists."
            else:
                return None

        username = self.getUserName()
        home = members._getOb( username, None )
        if home is not None:
            if not unrestricted and not _checkPermission( CMFCorePermissions.View, home ):
                if not no_raise:
                    raise Unauthorized, username
                else:
                    return None
            return home

        if not create: return None

        authuser = _getAuthenticatedUser( self ).getUserName()
        if authuser != username and not _checkPermission( ZopePermissions.manage_users, members ):
            if not no_raise:
                raise Unauthorized, username
            else:
                return None

        members.manage_addHeading( id=username, title=self.getMemberName() )
        try: home = members[ username ]
        except: home = None
        if home is None:
            raise SimpleError, 'Home folder is not created.'

        home.changeOwnership( username, recursive=1 )
        home.setLocalRoles( username, ( Roles.Owner, Roles.Editor, ) )
        if authuser != username:
            home.delLocalRoles( authuser )

        home.reindexObject()
        return home

    security.declareProtected( CMFCorePermissions.SetOwnProperties, 'getPersonalFolder' )
    def getPersonalFolder( self, ftype=None, create=None ):
        """
            Returns the user's personal folder, optionally creates it if it does not exist yet.

            Arguments:

                'ftype' -- String. Specifies the personal folder type (i.e.
                          'favorites', 'mail' etc.).

                'create' -- Boolean. Indicates whether it is required to create
                            the personal folder if it does not exist.

            Result:

                Folder object reference.
        """
        home = self.getHomeFolder( create=create )
        if home is None or ftype is None:
            return home

        # TODO: allow users to assign custom folders in the preferences
        folder = home._getOb( ftype, None )
        if folder is not None:
            return folder

        if not create: return None

        msg = getToolByName( self, 'msg', None )
        title = Config.PersonalFolders.get( ftype ) or ftype
        if title and msg:
            title = msg.gettext( title, lang=msg.get_default_language() )

        home.manage_addHeading( id=ftype, title=title )
        return home[ ftype ]

    security.declareProtected( CMFCorePermissions.SetOwnProperties, 'getPersonalFolderPath' )
    def getPersonalFolderPath( self, ftype=None, create=None ):
        """
            Returns the path to the user's personal folder by type.

            Arguments:

                'ftype' -- String. Specifies the personal folder type (i.e.
                          'favorites', 'mail' etc.).

                'create' -- Boolean. Indicates whether it is required to create
                            the personal folder if it does not exist.

            Result:

                List containing the folder physical path or None.
        """
        folder = self.getPersonalFolder( ftype, create )
        if folder is None:
            return None
        return folder.physical_path()

    security.declareProtected( CMFCorePermissions.SetOwnProperties, 'getPersonalFolderUrl' )
    def getPersonalFolderUrl( self, ftype=None, create=None, *args, **kw ):
        """
            Returns the URL of the user's personal folder by type.

            Arguments:

                'ftype' -- String. Specifies the personal folder type (i.e.
                          'favorites', 'mail' etc.).

                'create' -- Boolean. Indicates whether it is required to create
                            the personal folder if it does not exist.

                '*args', '**kw' -- Additional arguments to be passed to the
                                   absolute_url method.

            Result:

                String.
        """
        folder = self.getPersonalFolder( ftype, create )
        if folder is None:
            return None
        return folder.absolute_url( *args, **kw )

    security.declareProtected( CMFCorePermissions.ListPortalMembers, 'isMemberOfGroup' )
    def isMemberOfGroup( self, group ):
        """
            Checks whether the user participates in the given group.

            Arguments:

                'group' -- either group object or identifier string

            Result:

                Boolean value.
        """
        if type(group) is not StringType:
            group = group.getId()
        return ( group in self.getGroups() )
    #
    #   Member Access Permission Levels ==========================================================================
    #
    security.declarePublic('IsManager')
    def IsManager( self, context=None ):
        IsManager = self.has_role('Manager') and 1 or 0
        if context is not None:
            try: IsManager = getToolByName(self, 'portal_membership').checkPermission('Manage portal', context)
            except: IsManager = 0
        return IsManager

    security.declarePublic('IsAdmin')
    def IsAdmin( self, superusers=None ):
        IsManager = self.IsManager()
        IsAdmin = IsManager and self.isMemberOfGroup('_managers_') and ( not superusers or self.getUserName() in superusers ) and 1 or 0
        return IsAdmin

    security.declarePublic('IsVip')
    def IsVip( self ):
        return self.isMemberOfGroup('VIP') and 1 or 0

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setMemberAccessLevel' )
    def setMemberAccessLevel( self, mapping=None ):
        if mapping and type(mapping) is not DictType:
            return
        self.setMemberProperties( mapping )

    security.declarePublic('getMemberAccessLevel')
    def getMemberAccessLevel( self, id=None ):
        """
            Returns member portal access level.

            Arguments:

                'id' -- instance's id from portal configation (String).

            Result:

                String 'R/W' or None or Dictionary.
        """
        if not id:
            instances = portalConfiguration.getAttribute('instances')
            res = []
            for id in instances:
                x = self.getProperty( 'instance_%s' % id, '' )
                value = x in ['R','W'] and x or None
                res.append( { 'id' : id, 'value' : value } )
            return res

        return self.getProperty( 'instance_%s' % id, None )

InitializeClass( MemberData )


# TODO these must be localized

def _parseFullName( name ):
    """
        Splits long human name into first-middle-last name components.

        Arguments:

            'name' -- human name string

        Result:

            Tuple of strings - (first, middle, last).
    """
    parts = name.split()
    if len(parts) == 1:
        return ( parts[0], '', '' )
    # TODO parse "Last F.M." and "F.M. Last"
    if parts[0][-1] == ',':
        return ( parts[1], ' '.join(parts[2:]), parts[0][:-1] )
    else:
        return ( parts[0], ' '.join(parts[1:-1]), parts[-1] )

def _formatFullName( parts, default='', canonical=1 ):
    """
        Returns human name in "First Middle Last" form.

        Arguments:

            'parts' -- tuple of strings (first, middle, last)

            'default' -- value to return if the name is empty

            'canonical' -- optional flag; if true (default),
                        "F-M-L" form is used, "L-M-F" otherwise

        Result:

            String.
    """
    if not canonical:
        parts = parts[-1:] + parts[:-1]
    return ' '.join( filter( None, map( strip, parts ) ) ) or default

def _formatBriefName( parts, default='', mode='FML' ):
    """
        Returns human name in "F.M. Last" form.

        Arguments:

            'parts' -- tuple of strings (first, middle, last)

            'default' -- value to return if the name is empty

        Result:

            String.
    """
    fname, mname, lname = map( strip, parts )
    if lname and not (mname and fname):
        return ('%s %s %s' % (lname, fname, mname)).strip()
    if lname:
        fname, mname = [ n and n[0] not in '!@#$%^&*()_+=-|<>[]{},.?/\ ' and n[0]+'.' or '' for n in fname, mname ]
        if mode == 'FML' or not mode:
            return (fname and fname+mname+' ' or '') + lname
        elif mode in ['LFM','LMF']:
            return lname + (fname and ' '+fname+mname or '')
    if fname:
        return fname + (mname and ' '+mname or '')
    return default
