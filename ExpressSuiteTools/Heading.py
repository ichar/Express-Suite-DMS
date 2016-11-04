"""
Heading class
$Id: Heading.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 30/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from zLOG import LOG, ERROR, INFO, DEBUG

from urllib2 import urlopen
from string import join, lower
from sys import exc_info
from types import StringType, ListType, TupleType, DictType
from DateTime import DateTime

from Acquisition import aq_parent, aq_base, aq_inner, aq_get
from AccessControl import ClassSecurityInfo
from AccessControl import Permissions as ZopePermissions
from AccessControl.Permission import Permission

from Globals import HTMLFile, get_request
from OFS.CopySupport import CopyError

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.CMFCatalogAware import CMFCatalogAware
from Products.CMFCore.Expression import Expression
from Products.CMFCore.PortalFolder import PortalFolder
from Products.CMFCore.utils import getToolByName, _getViewFor, _checkPermission, _getAuthenticatedUser

import Config, Features
from Config import Roles, Permissions
from ConflictResolution import ResolveConflict
from Exceptions import SimpleError, ResourceLockedError
from MemberDataTool import MemberData
from HTMLDocument import HTMLDocument
from HTMLCard import HTMLCard
from Shortcut import Shortcut
from SimpleAppItem import SimpleAppItem, ObjectBrains
from SimpleObjects import ContainerBase
from PortalLogger import portal_log

from Utils import InitializeClass, refreshClientFrame, get_param, joinpath, splitpath, pathdelim

from logging import getLogger
logger = getLogger( 'Heading' )

default_max_level = 10

factory_type_information = ( { 'id'             : 'Heading'
                             , 'meta_type'      : 'Heading'
                             , 'title'          : 'Heading'
                             , 'description'    : """\
Heading is a kind of folder that is used to store documents and other CMF objects."""
                             , 'icon'           : 'folder_icon.gif'
                             , 'sort_order'     : 0.2
                             , 'product'        : 'ExpressSuiteTools'
                             , 'factory'        : 'addHeading'
                             , 'permissions'    : ( CMFCorePermissions.AddPortalFolders, )
                             , 'filter_content_types' : 0
                             , 'immediate_view' : 'folder'
                             , 'allowed_content_types' :
                                ( 'FS Folder',
                                  'Fax Incoming Folder',
                                  'HTMLDocument',
                                  'HTMLCard',
                                  'Heading',
                                  'Registry',
                                  'Search Profile',
                                  'Shortcut',
                                )
                             , 'actions'        :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View'
                                  , 'action'        : 'folder'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'edit'
                                  , 'name'          : 'Properties'
                                  , 'action'        : 'folder_edit_form'
                                  , 'permissions'   : ( CMFCorePermissions.ChangePermissions, )
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'filter'
                                  , 'name'          : 'Content filter'
                                  , 'action'        : 'portal_membership/processFilterActions?open_filter_form=1'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'viewing_order'
                                  , 'name'          : 'Viewing order'
                                  , 'action'        : 'viewing_order'
                                  , 'permissions'   : ( CMFCorePermissions.ChangePermissions, )
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'accessgroups'
                                  , 'name'          : 'Access control'
                                  , 'action'        : 'manage_access_form'
                                  , 'permissions'   : ( CMFCorePermissions.ChangePermissions, )
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'accesslist'
                                  , 'name'          : 'Access list'
                                  , 'action'        : 'access_list_form'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  , 'category'      : 'folder'
                                  }
                                )
                             }
                           ,
                           )

default_root_allowed_types = ( 'Heading', 'Site Container', 'Fax Incoming Folder', )


def addHeading( self, id, title='', set_owner=1 ):
    """
        Add a new Heading object with id *id*
    """
    self._setObject( id, Heading( id, title ), set_owner=set_owner )
    ob = self._getOb( id )

    try: path = ob is not None and ob.physical_path() or ''
    except: path = ''

    logger.info("addHeading successfully created new heading, path: %s" % path)


class Heading( ContainerBase, SimpleAppItem, PortalFolder ):
    """
        Heading class
    """
    _class_version = 2.0

    meta_type = 'Heading'
    portal_type = 'Heading'

    isPrincipiaFolderish = 1

    __implements__ = ( Features.canHaveSubfolders,
                       Features.isContentStorage,
                       Features.isPrincipiaFolderish,
                       Features.hasContentFilter,
                       Features.isPublishable,
                       PortalFolder.__implements__,
                     )

    security = ClassSecurityInfo()

    security.declareProtected( CMFCorePermissions.ManageProperties, 'setTitle' )
    security.declareProtected( CMFCorePermissions.ManageProperties, 'setDescription' )
    security.declareProtected( CMFCorePermissions.ManageProperties, 'setSubject' )
    security.declareProtected( CMFCorePermissions.View, 'manage_copyObjects' )
    security.declareProtected( CMFCorePermissions.AddPortalContent, 'manage_pasteObjects' )
    security.declareProtected( CMFCorePermissions.AddPortalContent, 'manage_cutObjects' )
    security.declareProtected( ZopePermissions.delete_objects, 'manage_renameObject' )

    index_html = None
    managed_roles  = Config.ManagedLocalRoles
    manage_options = PortalFolder.manage_options

    _properties = SimpleAppItem._properties
    _getCopy = SimpleAppItem._getCopy

    content_type = PortalFolder.content_type
    manage_addFolder = PortalFolder.manage_addFolder

    # CMF 1.3 overcome
    indexObject = CMFCatalogAware.indexObject
    #reindexObject = CMFCatalogAware.reindexObject
    unindexObject = CMFCatalogAware.unindexObject

    # attributes saved during remote object synchronization
    _sync_reserved = ()
    _sync_subobjects = ()

    _actions = SimpleAppItem._actions

    _owner_role = None
    _maxNumberOfPages = 0
    _archiveProperty = None

    main_page = ''

    def __init__( self, id, title='' ):
        """
            Construct instance
        """
        SimpleAppItem.__init__( self )
        PortalFolder.__init__( self, id, title )
        self.forbid_folder_in_jungle = 0

    def _p_resolveConflict( self, oldState, savedState, newState ):
        """
            Try to resolve conflict between container's objects
        """
        state = ResolveConflict('Heading', oldState, savedState, newState, '_objects', \
                                 update_local_roles=1, \
                                 mode=1 \
                                 )
        state['modification_date'] = newState['modification_date']
        return state

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not SimpleAppItem._initstate( self, mode ):
            return 0

        logger.info("_initstate, mode %s" % mode)

        for id, x in self.objectItems():
            klass = None
            meta_type = getattr(x, 'meta_type', None)
            if meta_type and default_classes.has_key(meta_type):
                klass = default_classes[meta_type]
            if klass is not None:
                self._upgrade( id, klass, container=self )

        # set owner the same as the current editor
        if getattr( self, '_owner', None ) is None:
            editors = self.users_with_local_role( Roles.Editor )
            if editors:
                self._v_change_owner = editors[0]

        # fix permissions on old folders
        try:
            perm = Permission( CMFCorePermissions.View, (), self )
            roles = perm.getRoles()
            if type(roles) is ListType and Roles.Member not in roles:
                perm.setRoles( ( Roles.Manager, Roles.Owner, Roles.Author, Roles.Editor, Roles.Reader, Roles.Writer ) )
        except:
            pass

        if getattr( self, '_viewingOrder', None ) is None:
            self._viewingOrder = []

        if getattr( self, '_viewingDocumentOrder', None ) is None:
            self._viewingDocumentOrder = []

        try: delattr( self, '_directives' )
        except: pass

        try: delattr( self, 'display_mode' )
        except: pass

        if getattr( self, '_allowed_categories', None ) is None:
            self._allowed_categories = []
        elif self._allowed_categories != [] and type(self._allowed_categories[0]) is not StringType:
            self._allowed_categories = [ cat.getId() for cat in self._allowed_categories ]

        if getattr( self, '_category_inheritance', None ) is None:
            self._category_inheritance = 1
        
        if getattr( self, 'forbid_folder_in_jungle', None  ) is None:
            self.forbid_folder_in_jungle = 0

        return 1

    security.declareProtected( CMFCorePermissions.ManageProperties, 'setNomenclativeNumber' )
    def setNomenclativeNumber( self, number ):
        self._nomenclative_number = number

    security.declareProtected( CMFCorePermissions.View, 'getNomenclativeNumber' )
    def getNomenclativeNumber( self ):
        return getattr(self, '_nomenclative_number', '')

    security.declareProtected( CMFCorePermissions.ManageProperties, 'setPostfix' )
    def setPostfix( self, postfix ):
        self._postfix = postfix

    security.declareProtected( CMFCorePermissions.View, 'getPostfix' )
    def getPostfix( self ):
        return getattr(self, '_postfix', '')

    def SearchableText( self ):
        return "%s %s" % (self.title, self.description)

    def Creator( self ):
        """
            XXX Overriden to apply new owner rules
        """
        owner = getattr(self, '_v_change_owner', None)
        if owner is not None:
            delattr( self, '_v_change_owner' )
            try: self.changeOwnership( owner )
            except: pass
        return SimpleAppItem.Creator( self )

    security.declareProtected( CMFCorePermissions.View, 'editor' )
    def editor( self ):
        """
            Get folder editor
        """
        userids = []
        ob = self
        while ob and not ob.implements('isPortalRoot'):
           userids = ob.users_with_local_role( Roles.Editor )
           if userids:
              break
           ob = ob.aq_parent
        return userids

    security.declareProtected( CMFCorePermissions.View, 'getFolderFilter' )
    def getFolderFilter( self, REQUEST=None ):
        """
            Return and cache current content filter
        """
        if REQUEST is None:
            REQUEST = self.REQUEST or get_request()

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None
    
        filter = membership.getFilter( REQUEST )
        cfilter = filter['filter']
        nfilter = filter['name']

        cfilter = self.decodeFolderFilter( cfilter )
        if nfilter or cfilter:
            cfilter['name'] = nfilter

        return cfilter

    security.declareProtected( CMFCorePermissions.View, 'listObjects' )
    def listObjects( self, REQUEST=None, **kw ):
        """
            Returns visible objects in the folder, via objectValues
        """
        if REQUEST is None:
            REQUEST = self.REQUEST or get_request()

        if REQUEST is not None and not kw.has_key('sort_limit'):
            batch_start = int(REQUEST.get('batch_start', 1))
            batch_size = int(REQUEST.get('batch_size', 10))
            limit = int(REQUEST.get('batch_length', 0)) or batch_size
            offset = batch_start - 1
        else:
            limit = offset = 0

        values = [ x for x in self.objectValues() if x is not None and \
            _checkPermission( CMFCorePermissions.View, x ) ]

        if values:
            sort_on = get_param('sort_on', REQUEST, kw, 'created')
            sort_order = get_param('sort_order', REQUEST, kw, '')
            if sort_on == 'Creator':
                membership = getToolByName( self, 'portal_membership', None )
                values.sort( lambda x, y, f=membership.getMemberName: cmp( f(x.Creator()), f(y.Creator()) ) )
            elif sort_on:
                values.sort( lambda x, y, sort_on=sort_on: cmp(apply(getattr(x, sort_on)), apply(getattr(y, sort_on))) )
            if sort_order == 'reverse':
                values.reverse()

        if offset or limit:
            rs = []
            n = 0
            for x in values:
                n += 1
                if offset and not n > offset:
                    continue
                if limit and len(rs) == limit:
                    break
                rs.append( x )
            res = rs
            del rs

        return ( len(values), [ ObjectBrains( x ) for x in res ], )

    security.declareProtected( CMFCorePermissions.View, 'searchObjects' )
    def searchObjects( self, REQUEST=None, path_idx=None, **kw ):
        """
            Return visible objects in the folder, via portal_catalog
        """
        if REQUEST is None:
            REQUEST = self.REQUEST or get_request()

        catalog = getToolByName( self, 'portal_catalog', None )
        membership = getToolByName( self, 'portal_membership', None )
        if catalog is None or membership is None:
            return ()

        cfilter = self.getFolderFilter( REQUEST )
        query = kw.copy()
        outgoing = membership.getCurrentFolderView() == 'outgoing' and 1 or 0
        res = []
        s = ''

        if path_idx is None:
            if self.aq_parent.implements('isPortalRoot'):
                pass
            elif not cfilter.get('Root', None) or outgoing:
                path_idx = 'path'
                s = '/%'
            else:
                path_idx = 'parent_path'
        if path_idx:
            query[ path_idx ] = "%s%s" % ( self.physical_path(), s )

        query['Creator'] = cfilter.get('Creator', '')

        # TODO: move this to type information
        # should be a list of all nonfolderish types from the types_tool
        allowed_default = map( lambda x:x.getId(), self.allowedContentTypes( restrict=0 ) )
        types = list( cfilter.get( 'Type', allowed_default ) )
        if not types:
            return results

        query['portal_type'] = types
        query['sort_on'] = get_param('sort_on', REQUEST, kw, None)
        query['sort_order'] = get_param('sort_order', REQUEST, kw, None)
        if query['sort_on'] == 'Creator':
            query['sort_limit'] = None

        total_objects, res = catalog.searchResults( type='all', archive=None, with_limit=1, \
            REQUEST=REQUEST, **query )

        return ( total_objects, catalog.sortResults( res, **query ) )

    security.declareProtected( CMFCorePermissions.View, 'hasMainPage' )
    def hasMainPage( self ):
        """
           Check whether this folder is in the main page mode
        """
        return not not self.main_page

    security.declareProtected( CMFCorePermissions.ManageProperties, 'setMainPage' )
    def setMainPage( self, object ):
        """
           Set mark on the topic, that some of it's documents
           must be used as index page, when publishing to external site.

           mode values:
              0 - documents list
              1 - main page
        """
        uid = object is not None and object.getUid() or ''
        if uid == self.main_page:
            return
        self.main_page = uid
        self.updateRemoteCopy( recursive=0 )

    security.declareProtected( CMFCorePermissions.View, 'getMainPage' )
    def getMainPage( self ):
        """
            Return main document for topic
        """
        uid = self.main_page
        if not uid:
            return None

        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return None

        query = { 'path' : self.physical_path(), 'nd_uid' : uid }

        results = catalog.searchResults( **query )
        if not results:
            return None

        return results[0].getObject()

    security.declareProtected( CMFCorePermissions.AddPortalFolders, 'manage_addHeading' )
    def manage_addHeading( self, id, title='', set_owner=1, REQUEST=None ):
        """
            Add a new Heading object with id *id*
        """
        self._setObject( id, Heading( id, title ), set_owner=set_owner )
        if REQUEST is not None:
            return self.folder_contents( self, REQUEST, portal_status_message="Topic added" )

    def unrestricted_addHeading( self, id, title='', description='', set_owner=1 ):
        """
            Add a new Heading object with id *id*
        """
        uname = _getAuthenticatedUser(self).getUserName()
        if not uname:
            return None

        self.setLocalRoles( uname, [ Roles.Writer ] )
        self._setObject( id, Heading( id, title ), set_owner=set_owner )
        self.notifyModified()
        self.setLocalRoles( uname, [ Roles.Author ] )

        try: folder = self._getOb( id, None )
        except: folder = None

        if folder is not None:
            folder.setDescription( description )
            folder.reindexObject()

        return folder

    def manage_fixupOwnershipAfterAdd( self ):
        """
            Setup local editor role
        """
        if aq_parent( self ).implements('isPortalRoot'):
            self.changeOwnership( None, recursive=0, explicit=1 )
            return

        PortalFolder.manage_fixupOwnershipAfterAdd( self )

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return
        member = self.getOwner()
        if member is not None:
            member = membership.getMemberById( member.getUserName() )

        if member is None:
            self.changeOwnership( None, recursive=0, explicit=1 )
            return

        uname = member.getUserName()
        self.setLocalRoles( uname, [ Roles.Editor ] )
        self.manage_permission( CMFCorePermissions.View, \
                ( Roles.Manager, Roles.Owner, Roles.Author, Roles.Editor, Roles.Reader, Roles.Writer ), 0 )

    security.declareProtected( CMFCorePermissions.ManageProperties, 'manage_changeProperties' )
    def manage_changeProperties( self, REQUEST=None, **kw ):
        """
            Change existing object properties
        """
        res = SimpleAppItem.manage_changeProperties( self, REQUEST, **kw )
        self.reindexObject()
        return res

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'manage_permissions' )
    def manage_permissions( self, no_reindex=None, REQUEST=None, **kw ):
        """
            Change permissions of the given object
        """
        membership = getToolByName( self, 'portal_membership', None )
        url_tool = getToolByName( self, 'portal_url', None )
        if membership is None or url_tool is None:
            return

        groups = membership.listGroups()
        roles_map = {}

        valid_roles = url_tool.getPortalObject().valid_roles()
        valid_roles = [ role for role in self.managed_roles if role in valid_roles ]

        # read the desirable configuration from REQUEST
        for group in groups:
            roles = REQUEST.get( group.getId() ) or []
            roles = [ role for role in roles if role in valid_roles ]
            if roles:
                roles_map[ group.getId() ] = roles

        # reset local roles settings
        self.manage_delLocalGroupRoles( [ group.getId() for group in groups ] )

        # assign local roles to the groups
        for group in roles_map.keys():
            self.manage_setLocalGroupRoles( group, roles_map[group] )

        idxs = ['allowedRolesAndUsers']

        if not no_reindex:
            self.reindexObject( idxs=idxs, recursive=1 )
        else:
            catalog = getToolByName( self, 'portal_catalog', None )
            if catalog is not None:
                catalog.reindexObject( self, idxs=idxs )

        if REQUEST is not None:
            self.redirect( action='manage_access_form', REQUEST=REQUEST )

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'manage_access_options' )
    def manage_access_options( self, REQUEST=None ):
        """
            XXX
        """
        forbid_folder_in_jungle = REQUEST.get( 'forbid_folder_in_jungle' ) or None

        if forbid_folder_in_jungle is not None:
            self.forbid_folder_in_jungle = forbid_folder_in_jungle == '1' and 1 or 0

        if REQUEST is not None:
            self.redirect( action='manage_access_form', REQUEST=REQUEST )

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'setLocalRoles' )
    def setLocalRoles( self, userid, roles, REQUEST=None ):
        """
            Wrapper for the built-in manage_setLocalRoles
        """
        changed = 0

        if type(roles) is StringType:
	    new_roles = [ roles ]
        elif type(roles) is TupleType:
            new_roles = list( roles )
        else:
            new_roles = roles

        old_roles  = list( self.get_local_roles_for_userid( userid ) )
        user_roles = self.getLocalRoles( userid )
        man_roles  = self.managed_roles

        # find all roles inherited from the upper folders
        inherited = {}
        for rlist in user_roles[1:]:
            for role in rlist:
                inherited[ role ] = 1

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return

        if not membership.isAnonymousUser():
            cur_user = membership.getAuthenticatedMember().getUserName()
            if cur_user == userid \
                    and Roles.Owner not in old_roles \
                    and not inherited.has_key( Roles.Editor ) \
                    and not _checkPermission( CMFCorePermissions.ManagePortal, self ):
                if REQUEST is None:
                    return
                REQUEST.RESPONSE.redirect( \
                    self.absolute_url( redirect=1, action='manage_access_form',
                                       message='You are not allowed to change your own access rights.' ),
                                       status=303 )
                return

        # allow editor role to be reassigned
        try: del inherited[ Roles.Editor ]
        except KeyError: pass

        # don't reassign inherited roles
        new_roles = filter( lambda r, x=inherited: not x.has_key(r), new_roles )

        # see whether *userid* is the main editor
        editors = self.users_with_local_role( Roles.Editor )
        is_editor = len(editors) == 1 and editors[0] == userid

        # *editors* are all the explicit editors excluding *userid*
        try: editors.remove( userid )
        except ValueError: pass

        if Roles.Editor in new_roles:
            # set *changed* only if *userid* is not the main editor already
            changed = not is_editor
            # the main editor is also the owner of the folder
            self.changeOwnership( userid, recursive=0, explicit=1 )

            # if *changed* then *editors* (may) include previous editor
            if changed and editors:
                rdict = getattr( self, '__ac_local_roles__', None )

                # delete all the previous editors
                for editor in editors:
                    editor_roles = rdict and rdict.get( editor ) or []
                    editor_roles.remove( Roles.Editor )

                    # if *editor* has no other roles in the folder,
                    # grant her the reader role at least
                    if not editor_roles:
                        editor_roles.append( Roles.Reader )

                    self.manage_setLocalRoles( editor, editor_roles )

        elif Roles.Editor in old_roles:
            # editor role is being revoked from *userid*
            changed = 1
            # change owner to the next editor in the list, or no owner
            editor = editors and editors[0] or None
            self.changeOwnership( editor, recursive=0 )

        if changed and REQUEST is not None:
            # request the nav tree menu refresh when the editor was changed
            refreshClientFrame( Config.NavTreeMenu )

        # preserve system roles (e.g. owner in home folders)
        for role in old_roles:
            if not ( role in man_roles or role in new_roles ):
                new_roles.append( role )

        new_roles.sort()
        old_roles.sort()

        if new_roles != old_roles:
            if new_roles:
                self.manage_setLocalRoles( userid, new_roles )
            else:
                self.manage_delLocalRoles( (userid,) )
            changed = 1

        if changed:
            # update portal_catalog indexes
            self.reindexObject( idxs=['Creator','allowedRolesAndUsers'], recursive=1 )

        if REQUEST is not None:
            # user may have removed her own roles
            if _checkPermission( CMFCorePermissions.ChangePermissions, self ):
                action = 'manage_access_form'
            else:
                action = 'folder'

            return REQUEST.RESPONSE.redirect(
                    self.absolute_url( redirect=1, action=action,
                                       message='Access rights have been granted.' ),
                    status=303 )

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'delLocalRoles' )
    def delLocalRoles( self, userids, REQUEST=None ):
        """
            Wrapper for the built-in manage_delLocalRoles
        """
        if type(userids) is StringType:
            userids = ( userids, )

        editors = self.users_with_local_role( Roles.Editor )
        is_editor = len(editors) and editors[0] in userids

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return

        cur_user = membership.getAuthenticatedMember().getUserName()
        if cur_user in userids and not _checkPermission( CMFCorePermissions.ManagePortal, self ):
            user_roles = self.getLocalRoles( cur_user )
            # find all roles inherited from the upper folders
            inherited = {}
            for rlist in user_roles[1:]:
                for role in rlist:
                    inherited[ role ] = 1

            if Roles.Editor not in inherited.keys():
                if REQUEST is not None:
                    REQUEST.RESPONSE.redirect(
                        self.absolute_url( redirect=1, action='manage_access_form',
                                       message='You are not allowed to remove your own access rights.' ),
                        status=303 )
                return

        for userid in userids:
            try: editors.remove( userid )
            except ValueError: pass

        if is_editor:
            editor = editors and editors[0] or None
            self.changeOwnership( editor, recursive=0 )

            # request the nav tree menu refresh when editor was changed
            refreshClientFrame( Config.NavTreeMenu )

        man_roles = self.managed_roles

        for userid in userids:
            roles = list( self.get_local_roles_for_userid( userid ) )
            for role in man_roles:
                try: roles.remove( role )
                except ValueError: pass

            if roles:
                self.manage_setLocalRoles( userid, roles )
            else:
                self.manage_delLocalRoles( (userid,) )

        # update portal_catalog indexes
        self.reindexObject( idxs=['allowedRolesAndUsers','Creator'], recursive=1 )

        if REQUEST is not None:
            # user may have removed her own roles
            if _checkPermission( CMFCorePermissions.ChangePermissions, self ):
                action = 'manage_access_form'
            else:
                action = 'folder'

            return REQUEST.RESPONSE.redirect(
                    self.absolute_url( redirect=1, action=action,
                                       message='Access rights have been removed.' ),
                    status=303 )

    def getSortedLocalRoles( self ):
        """
            Return sorted local roles list over this object
        """
        res = self.getLocalRoles( no_tuple=1 )
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return res
        res.sort( lambda x, y, f=membership.getMemberName: cmp( f(x[0]), f(y[0])) )
        return res

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'getLocalRoles' )
    def getLocalRoles( self, userid=None, check_only=0, no_tuple=None ):
        """
            Return all local roles assigned over this object
        """
        info = []
        mroles = self.managed_roles
        object = self

        # walk through the whole CMF Site and gather all
        # acquired roles that are applied to the object
        n = 0
        while not object.implements('isPortalRoot') and n < default_max_level:
            rdict = getattr( object, '__ac_local_roles__', None )
            n += 1

            if rdict is None:
                pass
            elif userid is not None:
                roles = rdict.get( userid )
                roles = roles and filter( lambda r, m=mroles: r in m, roles )
                if roles:
                    info.append( roles )
            else:
                users = rdict.keys()
                users.sort()
                # user is a dict key, value
                for user in users:
                    # be aware about managed_roles only
                    roles = rdict[ user ]
                    roles = filter( lambda r, m=mroles: r in m, roles )
                    if roles:
                        if object is not self:
                            # mark inherited roles
                            roles.insert( 0, '__inherited' )
                        info.append( ( user, roles ) )

            if userid and not info:
                info.append( () )

            object = aq_parent( object )

        if check_only:
            return 1 in map(lambda p: p and 1, info)

        if not no_tuple:
            return tuple(info)
        else:
            return info

    #security.declareProtected(CMFCorePermissions.View, 'user_roles')
    security.declarePublic('user_roles')
    def user_roles( self ):
        """
            Get the users' role list within current context
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None

        roles = membership.getAuthenticatedMember().getRolesInContext(self)
        roles = filter( lambda x, self=self: x in self.managed_roles, roles )

        return roles

    security.declarePublic('allowedContentTypes')
    def allowedContentTypes( self, groups=0, restrict=1 ):
        """
            List type info objects for types which can be added in this folder
        """
        # this is a modified version from CMF 1.3-release
        res = []
        portal_types = getToolByName( self, 'portal_types', None )
        if portal_types is None:
            return None

        myType = portal_types.getTypeInfo(self)

        if myType is not None:
            for contentType in portal_types.listTypeInfo( restrict and self or None ):
                if myType.allowType( contentType.getId() ):
                   res.append( contentType )
        else:
           res = portal_types.listTypeInfo()

        if restrict:
            res = filter( lambda ob, self=self: ob.isConstructionAllowed( self ), res )
            if aq_parent(self).implements('isPortalRoot'):
                # TODO: must use some property
                res = filter( lambda ob: ob.getId() in default_root_allowed_types, res )

        if groups:
            seen = {}
            res = filter( lambda ob, seen=seen: not ( ob.type_group and seen.setdefault( ob.type_group, 1 )), \
                res )
            groups = portal_types.listTypeGroups()
            groups = filter( lambda ob, seen=seen: seen.has_key( ob.getId() ), groups )
            res += groups

        # Sorting by MessageCatalog
        # msg = getToolByName( self, 'msg' )
        # res.sort(lambda x, y, msg=msg: cmp(lower(msg(x.title)), lower(msg(y.title))) )

        return res

    def _verifyObjectPaste( self, object, validate_src=1 ):
        """
            Verify whether an object can be pasted here
        """
        portal_types = getToolByName( self, 'portal_types', None )
        if portal_types is None:
            return None

        tinfo = portal_types.getTypeInfo( self )
        oinfo = portal_types.getTypeInfo( object )

        if not( tinfo and oinfo and tinfo.allowType( oinfo.getId() ) ):
            raise CopyError # TODO: add message

        return PortalFolder._verifyObjectPaste( self, object, validate_src )

    security.declareProtected( CMFCorePermissions.View, 'deleteObjects' )
    def deleteObjects( self, ids ):
        """
            Check 'delete objects' permission on every remove operation
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None

        allowed = []

        for id in ids:
            ob = self._getOb( id, None )
            if ob is None or not membership.checkPermission( ZopePermissions.delete_objects, ob ):
                continue
            if ob.implements('isLockable'):
                try: ob.failIfLocked()
                except ResourceLockedError: continue

            ob._v_instance_destroyed = 1
            logger.info("deleteObjects Object was deleted: '%s' by %s" % ( ob.physical_path(), \
                _getAuthenticatedUser(self).getUserName() ))
            allowed.append( id )

        ob = None
        count = len(allowed)
        if count:
            ContainerBase.deleteObjects( self, allowed )

        return count

    security.declareProtected( CMFCorePermissions.ManageProperties, 'reindexObject' )
    def reindexObject( self, idxs=[], recursive=None ):
        """
            Reindex folder and optionally all the objects inside
        """
        try: CMFCatalogAware.reindexObject.im_func( self, idxs )
        except TypeError: CMFCatalogAware.reindexObject.im_func( self ) # for CMF 1.3 beta

        if not recursive:
            return

        portal_log( self, 'Heading', 'reindexObject', 'recursive!', ( idxs, self.absolute_url() ) )

        for ob in self.objectValues():
            if isinstance( ob, Heading ):
                ob.reindexObject( idxs, recursive )
            elif hasattr( aq_base(ob), 'reindexObject' ):
                try: ob.reindexObject( idxs )
                except TypeError: ob.reindexObject()

    def getBadLinks( self ):
        """
            Returns list of documents and bad links, included in given documents in format
            [[document, links_count, [bad_link1, ...]], ...]
        """
        expr = '<[\s]*a[^<^>]+href[\s]*=[\s]*"([^"]+)"[^<^>]*>[^<]*<[\s]*/a[\s]*>'
        url_expr = re.compile(expr, re.IGNORECASE)
        res = []

        for element in self.objectValues():
            if element.meta_type in ( 'HTMLDocument', 'HTMLCard', ):
                badLinks = []
                link = url_expr.search( element.EditableBody() )

                while link:
                    url = link.groups()[0]
                    try:
                        urlopen(url)
                    except:
                        err=exc_info()
                        if not hasattr(err[1], 'code') or err[1].code!=401:
                            badLinks.append(link.groups()[0])
                    link = url_expr.search(element.EditableBody(), link.end())

                if len(badLinks)>0:
                    res.append([element, len(badLinks), badLinks])

            elif isinstance( element, Heading ):
                res = res + element.getBadLinks()

        return res

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'setArchiveProperty' )
    def setArchiveProperty( self, archiveProperty ):
        self._archiveProperty = archiveProperty

    security.declareProtected( CMFCorePermissions.View, 'getArchiveProperty' )
    def getArchiveProperty( self ):
        return self._archiveProperty

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'setMaxNumberOfPages' )
    def setMaxNumberOfPages( self, maxNumberOfPages ):
        self._maxNumberOfPages = maxNumberOfPages

    security.declareProtected( CMFCorePermissions.View, 'getMaxNumberOfPages' )
    def getMaxNumberOfPages( self ):
        return self._maxNumberOfPages

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'listPublications' )
    def listPublications( self, exact = None, meta_types = [] ):
        path_index = exact and 'parent_path' or 'path'
        search_args = { path_index: self.physical_path()
                      , 'state': 'published'
                      , 'meta_type': meta_types
                      , 'sort_on' : 'Date'
                      , 'sort-order' : 'reverse'
                      }

        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return None

        results = apply(catalog.searchResults, (), search_args )

        ordered_documents_list = []
        documents_ids = []
        ordered_indexes = []

        for i in results:
            documents_ids.append(i.id)
        for i in self.getViewingDocumentOrder():
            try:
                ind = documents_ids.index(i)
                ordered_indexes.append( ind )
            except ValueError:
                pass
        for ind in range(0, len(results)):
            if not ind in ordered_indexes:
                ordered_documents_list.append( results[ind] )
        for ind in ordered_indexes:
            ordered_documents_list.append( results[ind] )

        return ordered_documents_list

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'getPublishedFolders' )
    def getPublishedFolders( self ):
        my_path = self.getPhysicalPath()
        my_len = len(my_path)
        subfolders = {}

        # filter out folders with no published documents inside
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return None

        published = catalog.searchResults( path=joinpath( my_path ), state='published' )

        for item in published:
            path = item.getPath().split( pathdelim )
            id = (len(path) > my_len + 1) and path[ my_len ] or None
            if id and not subfolders.has_key( id ):
                subfolders[ id ] = self[ id ]

        # Do not return object instances, we need only hash
        # with some object information
        subfolders_list = map(lambda x: {'absolute_url': x.external_url(),
                                         'meta_type'   : x.meta_type,
                                         'title'       : x.title,
                                         'title_or_id' : x.title_or_id(),
                                         'Description' : x.Description(),
                                         'hasMainPage' : x.hasMainPage(),
                                         'id'          : x.getId()
                                        },
                          subfolders.values() )

        ordered_subfolders_list = []
        subfolders_ids = []
        ordered_indexes = []

        for i in subfolders_list:
            subfolders_ids.append(i['id'])
        for i in self.getViewingOrder():
            try:
                ind = subfolders_ids.index(i)
                ordered_indexes.append( ind )
            except ValueError:
                pass
        for ind in range(0, len(subfolders_list)):
            if not ind in ordered_indexes:
                ordered_subfolders_list.append( subfolders_list[ind] )
        for ind in ordered_indexes:
            ordered_subfolders_list.append( subfolders_list[ind] )

        return ordered_subfolders_list

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'shiftDocument' )
    def shiftDocument( self, id, order ):
        documents_list = self.listPublications( exact=1 )
        self._viewingDocumentOrder = map(lambda x: x.id, documents_list)
        doc_pos = self._viewingDocumentOrder.index(id)
        temp_id = self._viewingDocumentOrder[doc_pos]
        order=int(order)

        if order==1:
            if doc_pos != len(self._viewingDocumentOrder)-1 and doc_pos != self.getMaxNumberOfPages()-1:
                self._viewingDocumentOrder[doc_pos] = self._viewingDocumentOrder[ doc_pos+1]
                self._viewingDocumentOrder[doc_pos+1] = temp_id
        elif order==2:
            last_pos = (self.getMaxNumberOfPages() or len(self._viewingDocumentOrder))-1
            if last_pos > len(self._viewingDocumentOrder)-1:
                last_pos = len(self._viewingDocumentOrder)-1
            self._viewingDocumentOrder = self._viewingDocumentOrder[:doc_pos] + \
                                         self._viewingDocumentOrder[ (doc_pos+1):(last_pos+1) ] + \
                                       [ self._viewingDocumentOrder[doc_pos], ] + \
                                         self._viewingDocumentOrder[ (last_pos+1): ]
        elif order==-1:
            if doc_pos:
                self._viewingDocumentOrder[doc_pos] = self._viewingDocumentOrder[doc_pos-1]
                self._viewingDocumentOrder[doc_pos-1] = temp_id
        elif order==-2:
            self._viewingDocumentOrder = [ self._viewingDocumentOrder[doc_pos], ] + \
                                           self._viewingDocumentOrder[:doc_pos] + \
                                           self._viewingDocumentOrder[(doc_pos+1):]

        self._p_changed = 1

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'shiftHeading' )
    def shiftHeading( self, id, order ):
        subfolders_list = self.getPublishedFolders()
        self._viewingOrder = map(lambda x: x['id'], subfolders_list)

        doc_pos = self._viewingOrder.index(id)
        temp_id = self._viewingOrder[doc_pos]
        order = int(order)

        if order==1:
            if doc_pos != len(self._viewingOrder)-1:
                self._viewingOrder[doc_pos] = self._viewingOrder[doc_pos+1]
                self._viewingOrder[doc_pos+1] = temp_id
        elif order==2:
            self._viewingOrder = self._viewingOrder[:doc_pos] + self._viewingOrder[ (doc_pos+1): ] \
                                         + [self._viewingOrder[doc_pos], ]
        elif order==-1:
            if doc_pos:
                self._viewingOrder[doc_pos] = self._viewingOrder[doc_pos-1]
                self._viewingOrder[doc_pos-1] = temp_id
        elif order==-2:
            self._viewingOrder = [self._viewingOrder[doc_pos], ] + self._viewingOrder[:doc_pos] \
                                         + self._viewingOrder[(doc_pos+1):]

        self._p_changed = 1

    security.declareProtected( CMFCorePermissions.View, 'getViewingDocumentOrder' )
    def getViewingDocumentOrder( self ):
        try:
            return self._viewingDocumentOrder
        except:
            self._viewingDocumentOrder = []
            self._p_changed = 1
            return self._viewingDocumentOrder

    security.declareProtected( CMFCorePermissions.View, 'getViewingOrder' )
    def getViewingOrder( self ):
        try:
            return self._viewingOrder
        except:
            self._viewingOrder = []
            self._p_changed = 1
            return self._viewingOrder

    def getContentsSize( self ):
        """
           Returns number of objects in folder
        """
        return len(self.objectIds())

    def _remote_transfer( self, context=None, container=None, server=None, path=None, id=None, \
                          parents=None, recursive=None ):
        """
        """
        pass

    def _remote_export( self, context=None, file=None, skip_ids=None ):
        """
        """
        pass

    def _remote_import( self, file, save_ids=None ):
        """
        """
        pass

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'setAllowedCategories' )
    def setAllowedCategories( self, allowed_categories ):
        """
            Sets allowed categories for heading.

            Arguments:

                allowed_categories - category definition objects.
        """
        self._allowed_categories = [cat.getId() for cat in allowed_categories]

    security.declarePublic( 'listAllowedCategories' )
    def listAllowedCategories( self, mode, cat_id=None ):
        """
            List category definition objects for allowed categories in this folder.

            Case mode of:
                'folders' - returns categories for ids from _allowed_categories,
                'inheritance' - returns concatenation of self and parent allowed categories,
                meta_type - returns intersection of categories available for meta_type and allowed categories.

            Arguments:

                mode -- mode of the assembly of the allowed category list.
                        Can be 'folders', 'inheritance', meta_type.

                cat_id -- id of category.

            Result:

                List of category definition objects.

        """
        if mode == 'parent_cats':
            if not self.aq_parent.implements('isPortalRoot'):
                return self.aq_parent.listAllowedCategories('inheritance')
            else:
                return self.listAllowedCategories('inheritance')

        elif mode == 'folders':
            return [ self.portal_metadata.getCategoryById(cat) for cat in self._allowed_categories ]

        elif mode == 'inheritance':
            full_allowed_categories = self._allowed_categories[:]
            if self._category_inheritance:
                parent = self.aq_parent
                while parent:
                    if parent.implements('isPortalRoot'):
                        full_allowed_categories.extend( \
                            [ cat.getId() for cat in self.portal_metadata.getCategories() if cat is not None ] \
                        )
                        break
                    full_allowed_categories.extend( \
                        [ cat.getId() for cat in parent.listAllowedCategories('folders') if cat is not None ] \
                    )
                    if not getattr( parent, '_category_inheritance', None ):
                        break
                    parent = parent.aq_parent

            for x in full_allowed_categories[:]:
                while full_allowed_categories.count(x) > 1:
                    full_allowed_categories.remove(x)

            return [ self.portal_metadata.getCategoryById(cat) for cat in full_allowed_categories ]

        # XXX Fix this!
        full_allowed_categories = filter(lambda x, y=[ \
            aq_base(x) for x in self.portal_metadata.listCategories(mode) ]: \
            x in y, [ aq_base(x) for x in self.listAllowedCategories('inheritance') ])

        if cat_id is not None and self.portal_metadata.getCategoryById(cat_id) not in full_allowed_categories:
            return full_allowed_categories + [ self.portal_metadata.getCategoryById(cat_id) ]

        return full_allowed_categories

    security.declareProtected( CMFCorePermissions.ChangePermissions, 'setCategoryInheritance' )
    def setCategoryInheritance( self, category_inheritance ):
        """
            Sets the folder category inheritance.

            Arguments:

                category_inheritance - value for category_inheritance
        """
        if category_inheritance:
            self._category_inheritance = 1
        else:
            self._category_inheritance = 0

    security.declareProtected( CMFCorePermissions.View, 'getCategoryInheritance' )
    def getCategoryInheritance( self ):
        """
            Returns folder category inheritance.

            Result:

                Boolean. Value of category inheritance.
        """
        return self._category_inheritance

InitializeClass( Heading )

default_classes = { 'Heading' : Heading, 'HTMLDocument' : HTMLDocument, 'HTMLCard': HTMLCard, 'Shortcut' : Shortcut }


def install( target ):
    # Register the Heading class
    Installer = ManageCMFContent()
    Installer.deploy_class( target=target, type_name='Heading', fti=factory_type_information )
