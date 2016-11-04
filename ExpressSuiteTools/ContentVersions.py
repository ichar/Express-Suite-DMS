"""
Collection of classes used to provide versions in document
$Id: ContentVersions.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 30/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
import string
import urllib
from random import randrange
from types import StringType, TupleType, ListType, InstanceType
from UserDict import UserDict

from ExtensionClass import Base
from AccessControl import ClassSecurityInfo
from AccessControl import Permissions as ZopePermissions
from AccessControl.Owned import Owned, ownerInfo
from AccessControl.Role import RoleManager
from AccessControl import getSecurityManager, SpecialUsers
from Acquisition import aq_base, aq_get, aq_inner, aq_parent, Acquired, Explicit, Implicit
from DateTime import DateTime
from OFS.ObjectManager import ObjectManager
from webdav.Resource import Resource

from Products.CMFCore.CMFCatalogAware import CMFCatalogAware
from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import _checkPermission, getToolByName
from Products.CMFDefault.Document import Document
from Products.Localizer import get_request

import Features
from Config import Roles, Permissions
from ConflictResolution import ResolveConflict
from SimpleAppItem import SimpleAppItem
from SimpleObjects import Persistent
from DocumentLinkTool import Link

from Utils import InitializeClass, installPermission, cookId, makeTuple

from logging import getLogger
logger = getLogger( 'ContentVersions' )

try:
    from webdav.WriteLockInterface import WriteLockInterface
    NoWL = 0
except ImportError:
    NoWL = 1

try:
    from Products.ExternalEditor.ExternalEditor import ExternalEditorPermission
    NoExternalEditor = 0
except ImportError:
    NoExternalEditor = 1


class ContentVersion( Persistent, Implicit, Owned, CMFCatalogAware, RoleManager, Resource, ObjectManager ):
    """ 
        Simple version class.

        ContentVersion takes some properties from parent document and store it as its own.
        So one document can have multiple independent versions.
    """
    _class_version = 1.01

    meta_type = 'Content Version'
    portal_type = 'Content Version'

    meta_types = ({'name':'Image Attachment',
                   'permission':CMFCorePermissions.View,
                   'action':''},
                 )
    __implements__ = ( Features.isDocument,
                       Features.isVersion,
                       ObjectManager.__implements__, # added
                     )
    if not NoWL:
        __implements__ = __implements__ + ( WriteLockInterface, )

    __allow_access_to_unprotected_subobjects__ = 1
    __propsets__ = ()

    _stx_level = Acquired

    text = ''
    cooked_text = ''
    _owner = None

    associated_with_attach = None
    content_type = Acquired
    absolute_url = Acquired

    __ac_roles__ = ( Roles.VersionOwner, )

    security = ClassSecurityInfo()

    def __init__( self, id, title='', description='' ):
        """
            Initialize class instance
        """
        Persistent.__init__(self)

        self.id = id
        self.title = title
        self.description = description
        self.modification_date = self.creation_date = DateTime()
        self.workflow_history = {}
        self.attachments = []

    # CHECK THE OBJECT STATES AND ADVISABLE IGNORE CONFLICT !!!
    # =========================================================
    def _p_resolveConflict( self, o, s, n ):
        return ResolveConflict('ContentVersion', o, s, n, 'modification_date', mode=-1, trace=0, default=1)

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if not hasattr( self, 'registry_data' ):
            self.registry_data = {}

        ac_local_roles = self.__ac_local_roles__ or {}
        for userid, roles in ac_local_roles.items():
            if type(roles) is TupleType:
                ac_local_roles[userid] = list(roles)
        self.__ac_local_roles__ = ac_local_roles

        if not hasattr( self, 'workflow_history' ):
            self.workflow_history = {}

        elif type(self.workflow_history) != type({}):
            try:
                items = self.workflow_history.items()
            except:
                items = []
            container = {}
            for key, value in items:
                container[ key ] = value
            self.workflow_history = container
            self._p_changed = 1

            logger.info('initstate workflow_history, keys: %s' % len(self.workflow_history.keys()))

        if not hasattr( self, '_copies_holders' ):
            self._copies_holders = []

        return 1

    security.declareProtected(CMFCorePermissions.View, '__call__')
    def __call__( self, *args, **kw ):
        """
            Default view
        """
        self._setVersionInRequest( self.id, self.REQUEST )
        return aq_parent(self)(*args, **kw)

    def __getitem__( self, key ):
        # if this is attache, return it
        if key in self.objectIds():
            return  self._getOb( key )
        # recursion
        #return aq_parent(self)[ key ]

    # hack for CMFCatalogAware
    def _CMFCatalogAware__recurse( self, name, *args ):
        values = [ i[1] for i in self.objectItems() ]
        opaque_values = self.opaqueValues()
        for subobjects in values, opaque_values:
            for ob in subobjects:
                s = getattr(ob, '_p_changed', 0)
                if hasattr(aq_base(ob), name):
                    getattr(ob, name)(*args)
                if s is None: ob._p_deactivate()

    # hack for ObjectManager
    def _subobject_permissions( self ):
        return ()

    # notify document
    def _notifyAttachChanged( self, id ):
        aq_parent(self)._notifyAttachChanged( id )

    # notify document
    def _notifyOnDocumentChange( self ):
        aq_parent(self)._notifyOnDocumentChange()

    def implements( self, feature=None ):
        result = Persistent.implements( self, feature )
        if result or feature is None:
            return result
        base = aq_parent(aq_inner( self ))
        if base is None:
            return base
        return base.implements( feature )

    def getPhysicalPath( self ):
        """
            Inserts version in context of version container object.

            Returns obtained path (an immutable sequence of strings)
            that can be used to access this object again
            later, for example in a copy/paste operation.

            Result:

                Tuple.
        """
        path = ( self.getId(), )
        p = aq_parent(aq_inner(self).__of__(aq_parent(self).version))
        if p is not None:
            path = p.getPhysicalPath() + path

        return path

    security.declarePublic('registry_ids')
    def registry_ids( self ):
        """
            Used by catalog
        """
        if getattr(self, 'registry_data', None):
            return self.registry_data.keys()
        return getattr(self.getVersionable(), 'registry_data', {}).keys()

    security.declarePublic('state')
    def state( self ):
        """
            Used by catalog
        """
        return self.getStatus()

    def _setVersionInRequest( self, ver_id=None, REQUEST=None ):
        """
            Places in the request pointer to the version.

            This is almost the same as making the version current.
            If ver_id is None, the current version will be chosen.
            Returns id of the version previously placed version (or None if there was no
            such version).

            Arguments:

                'ver_id' -- Identifier of the version. None means to use this version.

                'REQUEST' -- REQUEST object.

            Result:

                String or None
        """
        doc_uid = aq_parent(self).getUid()
        if REQUEST is None:
            REQUEST = aq_get( self.__of__(aq_parent(self)), 'REQUEST', None ) or get_request()
        prev_ver = REQUEST.get( (doc_uid, 'version') )
        REQUEST.set( (doc_uid, 'version'), ver_id or self.id )
        return prev_ver

    security.declareProtected(CMFCorePermissions.View, 'makeCurrent')
    def makeCurrent( self, REQUEST=None ):
        """
            Public interface for _setVersionInRequest (and uses only this version).

            Arguments:

                'REQUEST' -- REQUEST object.

            Result:

                String or None
        """
        return self._setVersionInRequest( None, REQUEST) or self.getPrincipalVersionId()

    def Type( self ):
        """
            Returns type of object for catalog
        """
        return "%s %s" %( aq_parent(self).Type(), 'Version')

    def title_or_id( self ):
        """
            Returns version title otherwise version id.

            Result:

                String.
        """
        return self.Title() or self.id

    # These methods are redefined to use desired version properties when
    # called _version_.method(). Otherwise will be called
    # HTMLDocument.method() -> getVersion().property, but getVersion()
    # and _version_ may be different

    Title = SimpleAppItem.Title.im_func
    Description = SimpleAppItem.Description.im_func
    Creator = SimpleAppItem.Creator.im_func
    CreationDate = SimpleAppItem.CreationDate.im_func
    ModificationDate = SimpleAppItem.ModificationDate.im_func
    modified = SimpleAppItem.modified.im_func

    def EditableBody( self ):
        """
            Returns the editable body of the version.
            See HTMLDocument.EditableBody for further details.
        """
        old = self._setVersionInRequest()
        text = aq_parent(self).EditableBody()
        self._setVersionInRequest(old)
        return text

    security.declareProtected( CMFCorePermissions.View, 'manage_FTPget' )
    def manage_FTPget( self ):
        """
            Gets the version body for FTP download (also used for the WebDAV SRC).
            See Document.manage_FTPget for further details.
        """
        old = self._setVersionInRequest()
        bodytext = aq_parent(self).manage_FTPget()
        self._setVersionInRequest(old)
        return bodytext

    def PUT( self, REQUEST, RESPONSE ):
        """
            Handles HTTP (and presumably FTP?) PUT requests.
            See HTMLDocument.PUT for further details.
        """
        doc_uid = aq_parent(self).getUid()
        oldver = REQUEST and REQUEST.get( (doc_uid, 'version') )
        REQUEST.set( (doc_uid, 'version'), self.id )
        result = aq_parent(self).PUT( REQUEST, RESPONSE )
        REQUEST.set( (doc_uid, 'version'), oldver )
        return result

    security.declarePublic('getId')
    def getId( self ):
        """
            Returns id of this version.

            Result:

                String.
        """
        return self.id

    security.declarePublic('getVersionNumber')
    def getVersionNumber( self ):
        """
            Returns id part from getId().

            Result:

                String.
        """
        id = self.getId()
        number = id.replace('version_','')
        return number

    security.declareProtected( CMFCorePermissions.View, 'getVersionTitle' )
    def getVersionTitle( self ):
        """
            Returns title of this version object.

            Result:

                String.
        """
        return self.title

    def getVersionable( self, unwrap=False ):
        """
            Acquires versionable content from the content version context.
        """
        context = aq_parent( self )
        return context

        #container = aq_parent(aq_inner( self ))
        #object = aq_parent(aq_inner( container ))
        #
        #if unwrap or context is container:
        #   return object
        #return object.__of__( context )

    # XXX move methods below to another class
    # (if we will inherit DTMLDocument from this class , we'll have to remove them)

    def removeAssociation( self, id ):
        """
            See HTMLDocument.removeAssociation for further details.
        """
        return aq_parent(self).removeAssociation( id )

    def associateWithAttach( self, *args, **kw ):
        """
            See HTMLDocument.associateWithAttach for further details.
        """
        return aq_parent(self).associateWithAttach(*args, **kw)

    def addFile( self, *args, **kw ):
        """
            Attaches a file to the document.
            See HTMLDocument.associateWithAttach for further details.
        """
        return aq_parent(self).addFile(*args, **kw)

    def removeFile( self, id ):
        """
            Removes all links pointing to the given file and deletes file.
            See HTMLDocument.removeFile for further details.
        """
        return aq_parent(self).removeFile(id)

    def manage_fixupOwnershipAfterAdd( self ):
        """
            Changes the ownership and permissions after the version is created
        """
        user = getSecurityManager().getUser()

        if SpecialUsers.emergency_user and aq_base(user) is SpecialUsers.emergency_user:
            __creatable_by_emergency_user__ = getattr( self,'__creatable_by_emergency_user__', None )
            if __creatable_by_emergency_user__ is None or not __creatable_by_emergency_user__():
                raise EmergencyUserCannotOwn, (
                    "Objects cannot be owned by the emergency user")

        self._owner = ownerInfo(user)

        # fix roles and permissions
        self.manage_setLocalRoles( user.getUserName(), [ Roles.VersionOwner ] )

        #may be need to set any more permissions to VersionOwner?
        self.manage_permission( CMFCorePermissions.View, \
                ( Roles.Manager, Roles.Owner, Roles.Editor, Roles.Reader, Roles.Writer, Roles.VersionOwner ), 0 )

        self.manage_permission( CMFCorePermissions.ModifyPortalContent, \
                ( Roles.Manager, Roles.VersionOwner ), 0 )

        self.manage_permission( Permissions.CreateObjectVersions, (), 0 )

    def getStatus( self ):
        """
            Gets status of current version.

            Result:

                Status of version (id).
        """
        wf_id = self.getVersionWorkflowId()
        workflow = getToolByName(self, 'portal_workflow', None)
        if not wf_id or workflow is None:
            return None

        if hasattr(aq_base(self), 'workflow_history'):
            workflow_history = aq_base(self).workflow_history
            if workflow_history and workflow_history.has_key(wf_id):
                return workflow_history.get(wf_id)[-1]['state']
            return workflow[wf_id].initial_state

        return None

    def getVersionWorkflowId( self ):
        """
            Returns object workflow id 
        """
        metadata = getToolByName( self, 'portal_metadata', None )

        try:
            wf_id = metadata.getCategoryById( self.Category() ).Workflow()
        except:
            logger.error("getStatus undefined workflow state of:\n%s" % self.physical_path())
            return None

        return wf_id

    # Prevent infinite loop while cataloging.
    def objectValues( self ):
        return ()

installPermission( ContentVersion, Permissions.CreateObjectVersions )
InitializeClass( ContentVersion )


class VersionsContainer( Persistent, ObjectManager ):
    """
        Version container class
    """
    _class_version = 1.0

    security = ClassSecurityInfo()

    #define it here to prevent 'maximum recursion depth exceeded' error
    def changeOwnership( self, *args, **kw ):
        """
            Really does nothing
        """
        pass

    def __init__( self, id ):
        """
            Creates instance.
            Creates in it default version with id='version_0.1',
            sets editable and principal version properties
        """
        Persistent.__init__(self)
        self.id = id

        # create default version
        ver = ContentVersion( id='version_0.1', title='', description='' )
        self._setObject( 'version_0.1', ver )

        self._principal_version = 'version_0.1'
        self._v_use_version = None

    def getPhysicalPath( self ):
        """
            Inserts version container in context of parent object.

            Returns obtained path (an immutable sequence of strings)
            that can be used to access this object again
            later, for example in a copy/paste operation.

            Result:

                Tuple.
        """
        path = (self.id, )
        p = aq_parent(aq_inner(self))
        if p is not None:
            path = p.getPhysicalPath() + path

        return path

    security.declareProtected( CMFCorePermissions.View, 'getCurrentVersionId' )
    def getCurrentVersionId( self ):
        """
            Returns current version id we work with or None
        """
        doc = aq_parent(self)
        REQUEST = aq_get( self.__of__(doc), 'REQUEST', None ) or get_request()
        num = REQUEST and REQUEST.get( (doc.getUid(), 'version') ) or self.getPrincipalVersionId()

        ver_ids=self.objectIds()

        if num and num in ver_ids:
            return num
        return None

    security.declareProtected(CMFCorePermissions.View, 'getVersion')
    def getVersion(self, num=None):
        """
            Return current or principal Version object.

            Arguments:

                'num' -- Id of the version to be retrieved. If None, principal
                    version will be returned.

            Result:

                ContentVersion.
        """
        num = num or self.getCurrentVersionId() or self._principal_version
        try:
            return aq_base( self._getOb(num) ).__of__(aq_parent(aq_inner(self)))
        except:
            return aq_base( self._getOb(self._principal_version) ).__of__(aq_parent(aq_inner(self)))

    __getitem__ = getVersion

    security.declareProtected(CMFCorePermissions.View, 'getEditableVersion')
    def getEditableVersion(self):
        """
            Returns the version which is marked as 'editable'.

            Result:

                ContentVersion.
        """
        #return aq_base( self._getOb(self._editable_version) ).__of__(aq_parent(self))
        # depricated
        return aq_base( self._getOb(self.getCurrentVersionId()) ).__of__(aq_parent(self))

    def __bobo_traverse__( self, REQUEST, name ):
        """
            This method will make this container traversable.

            Returns version with id=name (if exists), or property with id=name.
            If version is accessed, sets a flag in the request object indicating
            currently selected version.  Also sets auxiliary request variables
            for 'absolute_url' and 'relative_url' methods to work correctly
            with versions.

            Arguments:

                'REQUEST' -- REQUEST object.

                'name' -- Next part of URL.

            Result:

                ContentVersion or something else (depends on 'name' argument).
        """
        REQUEST = REQUEST or aq_get( self, 'REQUEST', None )

        result = self[name]
        if name != result.id:
            return getattr(self, name)
            #return getattr(aq_parent(self), name)

        doc = aq_parent( self )

        if name in self.objectIds() and type(REQUEST)!=type({}): # for copy/paste operation
            REQUEST.set( (id(aq_base(result)), 'principal'), doc )
            REQUEST.set( (id(aq_base(doc)), 'subpath'), self.id + '/' + name )
            result._setVersionInRequest( REQUEST=REQUEST )

        return result

    security.declareProtected(Permissions.CreateObjectVersions, 'createVersion')
    def createVersion( self, old_id, new_id, title='', description='' ):
        """
            Creates new version with given properties based on the version with id=old_id.

            Returns id of the created version.

            Arguments:

                'old_id' -- Id of the version which is considered the base for new one.

                'new_id' -- Identifier for new version.

                'title' -- New version's title.

                'description' -- New version's description.

            Result:

                String.
        """
        object = ContentVersion( id=new_id, title=title, description=description )
        old = self.getVersion( old_id )

        object.text = old.text
        #object.cooked_text = old.cooked_text

        # copy propertysheets from the old version object
        psets = ()
        for old_ps in old.__propsets__:
            old_ps._p_mtime
            new_ps = old_ps.__class__.__basicnew__()
            new_ps.__dict__.update( old_ps.__dict__ )
            psets = psets + ( new_ps, )
        object.__propsets__ = psets

        #object.attachments = old.attachments
        object.associated_with_attach = old.associated_with_attach
        #old.associated_with_attach = None

        self._setObject(new_id, object)

        return new_id

    def _listVersions( self ):
        """
            Returns version objects in context of the document.

            Result:

                A list of ContentVersion objects.
        """
        doc = aq_parent( aq_inner( self ) )
        return [ aq_base(v).__of__(doc) for v in self.objectValues() ]

InitializeClass(VersionsContainer)


class VersionableContent( Base ):
    """
        VersionableContent class provides functions for supporting versions
        in data classes (such as HTMLDocument). To provide versions, child
        class must be subclassed from VersionableContent (and if it is
        multiple inheritance, VersionableContent have to be first in classes
        list)
    """
    _class_version = 1.0

    __implements__ = Features.isVersionable

    security = ClassSecurityInfo()

    _versionable_methods = ()
    _versionable_methods_common = ()
    _versionable_attrs = ()
    _versionable_perms = ()

    def __init__( self, container='version' ):
        self.__ac_local_roles__ = VersionableRoles()
        self._setObject( container, VersionsContainer( container ) )

    def __getattr__( self, name ):
        """
            Returns attribue 'name' of current version.

            Returns attribue 'name' of current version if 'name'
            is among self._versionable_attrs or self._versionable_perms.
            Raises AttributeError exception otherwise.

            Arguments:

                'name' -- attribute name

            Result:

                Attribute value.
        """
        if name in self._versionable_attrs or name in self._versionable_perms: # and name!='_owner':
            #FIXME!!! check permissions
            version = self.version.getVersion()
            if hasattr(aq_base(version), name):
                return getattr(version,name)

        raise AttributeError, name

    def __setattr__( self, name, value ):
        """
            Sets name=value in current version or content object itself.

            If 'name' is among self._versionable_attrs then sets name=value
            in current version otherwise sets it to document itself.

            Arguments:

                'name' -- attribute name to set

                'value' -- attribute value to set
        """
        ###print 'version setattr: %s=%s' % (name, str(value))

        try: x = makeTuple(self._versionable_attrs, self._versionable_perms)
        except: x = []

        if name in x: # and name!='_owner':
            #print 'is current version'
            ob = self.getVersion()
            if ob is not None:
                setattr(ob, name, value)
        else:
            #print 'is self'
            if Persistent._p_setattr(self, name, value):
                return
            self.__dict__[name] = value
            if not name.startswith('tmp_'): # name[:3] not in ['_p_','_v_'] and
                self._p_changed = 1

        ###print 'OK'

    def __delattr__( self, name ):
        """
            Removes attribute 'name' from current version.

            If 'name' is among self._versionable_attrs or
            self._versionable_perms, only TRIES to remove attribute.
            Otherwise directly remover attribute 'name' in content object.

            Arguments:

                'name' -- attribute to remove
        """
        ###print 'version delattr: %s' % name

        if not self.__dict__.has_key(name):
            return

        try: x = makeTuple(self._versionable_attrs, self._versionable_perms)
        except: x = []

        if name in x:
            #print 'is current version'
            try: del self.__dict__[name]
            except: pass
        else:
            #print 'is self'
            if Persistent._p_delattr(self, name):
                return
            del self.__dict__[name]
            if not name.startswith('tmp_'): # name[:3] not in ['_p_','_v_'] and
                self._p_changed = 1

        ###print 'OK'

    def __getitem__( self, key ):
        return self.getVersion()[key]

    security.declareProtected( CMFCorePermissions.View, 'getVersionable' )
    def getVersionable( self ):
        """
            Returns document object
        """
        return self

    security.declareProtected(CMFCorePermissions.View, 'getVersion')
    def getVersion( self, num=None ):
        """
            Returns version with id 'num' or default version of document.

            Arguments:

                'num' -- Id of the version to retrieve. If None, returns
                    principal version.

            Result:

                ContentVersion.
        """
        return self.version.getVersion(num)

    def checkVersionPermission( self, permission, version_id=None, version=None ):
        """
            TO DO
        """
        #return _checkPermission( perm, aq_base( self.getVersion(num) ).__of__( aq_parent(self) ) )
        if version_id is None:
            version_id = version.id
        return _checkPermission( permission, aq_base( self.getVersion(version_id) ).__of__( aq_parent(self) ) )

    security.declareProtected(CMFCorePermissions.View, 'getFirstEditableVersion')
    def getFirstEditableVersion( self ):
        """
            Returns first editable by current user version of document
        """
        editable_versions = []
        for version in self.version._listVersions():
            if self.checkVersionPermission( CMFCorePermissions.ModifyPortalContent, version=version ) or version.getStatus()=='group':
                editable_versions.append( version )

        # make sort conditions
        if editable_versions:
            return editable_versions[-1]
        return None

    security.declareProtected(CMFCorePermissions.View, 'getEditableVersion')
    def getEditableVersion( self ):
        """
            Returns editable version.

            Result:

                ContentVersion.
        """
        return self.version.getEditableVersion()

    security.declareProtected(CMFCorePermissions.View, 'getEditableVersionId')
    def getEditableVersionId( self ):
        """
            Returns id of the editable version.

            Result:

                String.
        """
        return (self.getEditableVersion() and self.getEditableVersion().id or None)

    security.declareProtected(CMFCorePermissions.View, 'getPrincipalVersionId')
    def getPrincipalVersionId( self ):
        """
            Returns id of the principal version.

            Result:

                String.
        """
        return self.version._principal_version

    security.declareProtected(CMFCorePermissions.View, 'getCurrentVersionId')
    def getCurrentVersionId( self ):
        """
            Returns id of currently used version.

            If can not find (object uid, 'version') key in REQUEST, returns None.

            Result:

                String or None.
        """
        return self.version.getCurrentVersionId()

    security.declareProtected(CMFCorePermissions.View, 'isCurrentVersionPrincipal')
    def isCurrentVersionPrincipal( self ):
        """
            Returns true if current version is principal.

            Result:

                Boolean.
        """
        return self.getPrincipalVersionId() == self.getCurrentVersionId() or \
            self.getCurrentVersionId()==None

    security.declareProtected(CMFCorePermissions.View, 'isCurrentVersionEditable')
    def isCurrentVersionEditable( self ):
        """
            Returns true if current version is editable.

            Result:

                Boolean.
        """
        return ( self.getCurrentVersionId() or self.getPrincipalVersionId() ) == self.getEditableVersionId()

    security.declareProtected(CMFCorePermissions.View, 'getMaxMajorAndMinorNumbers')
    def getMaxMajorAndMinorNumbers( self ):
        """
            Returns tuple with the major and minor parts of id of the version
            with maximal id.

            Note: used to show how will new created version id looks like.

            Result:

                Tuple.
        """
        vers_ids = self.version.objectIds()
        #calculate max major version and is's max minor version
        versions_mm = []
        for test_id in vers_ids:
            mm = re.findall(r'version_(\d+)[_\.](\d+)', test_id)
            versions_mm.append( (int(mm[0][0]), int(mm[0][1])) )
        versions_mm.sort()
        return versions_mm[-1]

    security.declareProtected(Permissions.CreateObjectVersions, 'createVersion')
    def createVersion( self, ver_id, ver_weight='minor', title='', description='', REQUEST=None ):
        """
            Creates new version. Returns id of created version.

            Arguments:

                'ver_id' -- Id of the version on the basis of which to create new one.
                'ver_weight' -- Weight of created version. Should be 'minor'
                    (default) or 'major'. Affects on id of new version.
                'title' -- Title of version.
                'description' -- Description of version.
                'REQUEST' -- REQUEST object.

            Result:

                String.
        """
        major, minor = self.getMaxMajorAndMinorNumbers()
        if ver_weight=='major':
            major += 1
            minor = 0
        else:
            minor += 1
        id = 'version_'+ str(major)+'.'+str(minor)

        new_id = self.version.createVersion(old_id=ver_id,
                    new_id=id,
                    title=title,
                    description=description)

        # copy attachments to new version
        new = self.getVersion(new_id)
        old = self.getVersion(ver_id)

        new.manage_pasteObjects( old.manage_copyObjects( old.objectIds() ) )

        # Copy document links from the source version
        links_tool = getToolByName( self, 'portal_links', None )
        link_brains = links_tool.searchLinks(source_uid=self.getUid(), source_ver_id=ver_id)
        if link_brains:
             for brain in link_brains:
                  old_link = brain.getObject()
                  klass = Link
                  new_link = klass.__basicnew__()
                  new_link.__dict__.update( old_link.__dict__ )

                  link_id = cookId(links_tool, prefix='link')
                  new_link.id = link_id
                  new_link.extra['source_ver_id'] = id
                  links_tool._setObject(link_id, new_link)
                  links_tool.indexObject( new_link )

        if REQUEST is not None:
            return REQUEST.RESPONSE.redirect( self.absolute_url()+'/version/'+ new_id +'/document_edit_form')
        else:
            return new_id

    security.declarePublic('checkVersionViewPerm')
    def checkVersionViewPerm( self, version=None ):
        """
            Checks 'View' permission for current user on the version 'version'.

            Arguments:

                'version' -- Version to check permission. May be string
                    with version id or version object itself.

            Result:

                Boolean.
        """
        if version is not None and isinstance(version, StringType):
            ver = self.getVersion( version )
        elif version is not None and isinstance(version, ContentVersion):
            ver = version
        else:
            ver = self.getVersion()
        return _checkPermission(CMFCorePermissions.View, ver)

    security.declarePublic('checkVersionModifyPerm')
    def checkVersionModifyPerm( self, version=None ):
        """
            Checks 'Modify portal content' permission for current user on the version 'version'.

            Arguments:

                'version' -- Version to check permission. May be string
                    with version id or version object itself.

            Result:

                Boolean.
        """
        if version is not None and isinstance(version, StringType):
            ver = self.getVersion( version )
        elif version is not None and isinstance(version, ContentVersion):
            ver = version
        else:
            ver = self.getVersion()
        return _checkPermission(CMFCorePermissions.ModifyPortalContent, ver)

    def reindexContainer( self ):
        """
            Recursive reindex object container
        """
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is not None:
            catalog.reindexObject( self, idxs=[], recursive=1 )

        catalog = getToolByName( self, 'portal_followup', None )
        if catalog is not None:
            catalog.reindexObject( self, idxs=[], recursive=1 )

    def reindexObject( self, idxs=[], recursive=None ):
        """
            Reindexes the object.

            Arguments:

                'idxs' -- list of indexes to reindex.
        """
        # This is needed to prevent cataloging of inactive version
        try: Document.reindexObject.im_func( self.getVersion(), idxs )
        except TypeError: Document.reindexObject.im_func( self.getVersion() )

        if self.isCurrentVersionPrincipal():
            try:
                Document.reindexObject( self, idxs )
            except TypeError:
                logger.error('reindexObject reindex error: %s' % `self`)
                Document.reindexObject( self )

        if idxs==[]:
            # Update the modification date
            self.notifyModified()

    security.declareProtected(CMFCorePermissions.View, 'listVersions')
    def listVersions( self ):
        """
            Returns list of existing versions mappings.

            Each item in resulted list has next keys:
                'id' -- id of the version
                'Title' -- version title
                'Number' -- version number (see getVersionNumber() for more datails)
                'Description' -- version description
                'Creator' -- creator of the version
                'CreationDate' -- creation date
                'ModificationDate' -- last modification date
                'Editable' -- is the version editable or no
                'Principal' -- is the version principal or no.

            Result:

                List of mappings.
        """
        result = []
        principal_id = self.getPrincipalVersionId()
        for version in self.version._listVersions():
            if not _checkPermission(CMFCorePermissions.View, version):
                continue
            res = { 'id'               : version.id,
                    'Title'            : version.Title(),
                    'Number'           : version.getVersionNumber(),
                    'Description'      : version.Description(),
                    'Creator'          : version.Creator(),
                    'CreationDate'     : version.CreationDate(),
                    'ModificationDate' : version.ModificationDate(),
                    'State'            : version.getStatus(),
                    'Principal'        : self.getPrincipalVersionId() == version.id,
                    'Current'          : self.getCurrentVersionId() == version.id,
                  }
            action = self.meta_type == 'HTMLCard' and 'card_view' or 'document_view'
            if version.id == principal_id:
                res['URL'] = self.absolute_url( action=action, no_version=1 )
            else:
                res['URL'] = version.absolute_url( action=action )
            result.append(res)
        return result

    security.declareProtected(Permissions.MakeVersionPrincipal, 'activateCurrentVersion')
    def activateCurrentVersion( self ):
        """
            Makes current version principal.
        """
        if self.getCurrentVersionId():
            self.version._principal_version = self.getCurrentVersionId()

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'denyVersionEdit')
    def denyVersionEdit( self ):
        """
            Takes away modifying permissions on ediatble version.

            Used by workflow.
        """
        self.getEditableVersion().manage_permission( CMFCorePermissions.ModifyPortalContent, (Roles.Manager, ), 0 )

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'allowVersionEdit')
    def allowVersionEdit( self ):
        """
            Gives back modifying permissions on ediatble version.

            Used by workflow.
        """
        self.getEditableVersion().manage_permission( CMFCorePermissions.ModifyPortalContent, (Roles.Manager, Roles.VersionOwner), 0 )

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'patchVersionAccessOnPublish')
    def patchVersionAccessOnPublish( self ):
        """
            Lets visitor to see only active version.

            Used by workflow.

            Note:

                Removes permission 'View' in the object (document). This
                permission will be extracted from version via __getattr__.
                This hack is needed to provide accees ONLY to the principal
                version on the external site.
        """
        return

        delattr(self, '_View_Permission')

        self.getEditableVersion().manage_permission( CMFCorePermissions.ModifyPortalContent, (Roles.Manager, ), 0 )
        principal = self.version._principal_version
        for ver in self.version._listVersions():
            if ver.id == principal:
                #let visitor to view version
                ver.manage_permission( CMFCorePermissions.View,
                    (Roles.Manager, Roles.Owner, Roles.Editor, Roles.Reader, Roles.Writer, Roles.VersionOwner, Roles.Visitor ), 0 )
            else:
                #other versions visitor can't see
                ver.manage_permission( CMFCorePermissions.View,
                    (Roles.Manager, Roles.Owner, Roles.Editor, Roles.Reader, Roles.Writer, Roles.VersionOwner), 0 )

    def externalEditLink_( self, object, borrow_lock=0 ):
        """
            Inserts the external editor link to an object if appropriate.

            Returns html text for that link.

            Note:

                See Products.ExternalEditor.ExternalEditor.EditLink() for more details.

            Result:

                String
        """
        if NoExternalEditor:
            return ''

        base = aq_base(object)
        user = getSecurityManager().getUser()
        editable = (hasattr(base, 'manage_FTPget')
                    or hasattr(base, 'EditableBody')
                    or hasattr(base, 'document_src')
                    or hasattr(base, 'read'))

        if editable and user.has_permission(ExternalEditorPermission, object):
            if object.implements('isVersion'):
                #object is version
                obj_url = self.version.absolute_url()
            else:
                #object is attachment
                #use this way to prevent adding subpath (version/version_id) of currently using version
                obj_url = aq_parent(self).absolute_url() + '/' + urllib.quote(self.getId())
            url = "%s/externalEdit_/%s" % (
                obj_url, urllib.quote(object.getId()))
            if borrow_lock:
                url += '?borrow_lock=1'
            
            msg = getToolByName(self, 'msg')
            edit_title = msg('Edit using external editor')
            
            return ('<a href="%s" title="%s"><img src="%s/misc_/ExternalEditor/edit_icon" align="middle" hspace="2" border="0" /></a>' % (url, edit_title, object.REQUEST.BASEPATH1))
        else:
            return ''

InitializeClass(VersionableContent)


class VersionableMethod( Explicit ):
    """
        Provides document method's call on version rather than on document itself
    """

    # simulate Script object for getPublishedInfo
    func_code = None

    def __init__( self, func, common=0 ):
        if hasattr( func, 'im_func' ):
            func = func.im_func
        self._func = func
        self._common = common

    def __call__( self, *args, **kw ):
        document = aq_parent(aq_inner( self ))
        context = aq_parent( self )

        while context is not None:
            if aq_parent(aq_inner( context )) is document:
                break
            context = aq_parent( context )
        else:
            context = document

        if isinstance( context, VersionsContainer ):
            context = aq_parent(aq_inner( context ))

        if context is document and not self._common:
            context = document.getVersion()

        return self._func( context, *args, **kw )


class VersionableAttribute( Base ):
    """
        VersionableAttribute class.

        This is attribute in document, which must be taken from version
        (even when attribute with the same name is presented in document).
        See ComputedAttribute for more details
    """
    def __init__( self, attr, default=MissingValue ):
        self._attr = attr
        self._default = default

    def __of__( self, parent ):
        try:
            result = parent.__getattr__( self._attr )
        except AttributeError:
            if self._default is MissingValue:
                raise
            return self._default
        return result


class VersionableRoles( UserDict, Explicit ):

    def __getitem__( self, key ):
        roles = self.data.get( key )
        roles = roles and list(roles) or []

        parent = aq_parent( self )
        if parent is not None:
            roles.extend( parent.getVersion().__ac_local_roles__.get( key ) or [] )

        #if not roles:
        #    raise KeyError, key
        return roles

    def get( self, key, default=None ):
        try: return self[ key ]
        except KeyError: return default

    def __setitem__( self, key, roles ):
        if Roles.VersionOwner in roles:
            if type(roles) is TupleType:
                roles = list(roles)
            roles.remove( Roles.VersionOwner )
        self.data[ key ] = roles

    def __len__( self ):
        return 1

    def __call__( self ):
        return self


def InitializeVersionableClass( klass ):
    """
        Initializes versionable methods, attributes and permissions
        in 'VersionableContent' derivative classes.

        Arguments:

            'klass' -- target class object.
    """
    names = getattr( klass, '_versionable_methods', () )
    for name in names:
        value = getattr( klass, name )
        if not ( type(value) is InstanceType and isinstance( value, VersionableMethod ) ):
            setattr( klass, name, VersionableMethod( value ) )

    names = getattr( klass, '_versionable_methods_common', () )
    for name in names:
        value = getattr( klass, name )
        if not ( type(value) is InstanceType and isinstance( value, VersionableMethod ) ):
            setattr( klass, name, VersionableMethod( value, 1 ) )

    names = getattr( klass, '_versionable_attrs', () )
    for name in names:
        if not hasattr( klass, name ):
            setattr( klass, name, VersionableAttribute( name ) )
        else:
            value = getattr( klass, name )
            if not ( type(value) is InstanceType and isinstance( value, VersionableAttribute ) ):
                setattr( klass, name, VersionableAttribute( name, value ) )

    names = getattr( klass, '_versionable_perms', () )
    perms = ()
    for name in names:
        if not name.startswith('_'):
            name = '_%s_Permission' % name.replace( ' ', '_' )
        perms += ( name, )
    klass._versionable_perms = perms
