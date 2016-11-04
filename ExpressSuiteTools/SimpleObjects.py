"""
Contains the following abstract base classes, that the corresponding
instances must inherit from:

    'Persistent' -- persistent objects

    'ItemBase' -- transient publishable objects

    'InstanceBase' -- persistent publishable objects

    'ContentBase' -- content objects

    'ContainerBase' -- container objects

    'ToolBase' -- portal tools

$Id: SimpleObjects.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 13/03/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys
from re import sub
from time import time
from types import IntType, DictType, StringType
from copy import deepcopy
from new import instance as _new_instance
from random import randrange

from AccessControl import ClassSecurityInfo
from AccessControl import Permissions as ZopePermissions
from AccessControl.Owned import UnownableOwner, ownerInfo
from AccessControl.SecurityManagement import getSecurityManager
from AccessControl.PermissionRole import rolesForPermissionOn
from AccessControl.User import nobody

from Acquisition import Implicit, Explicit, Acquired, aq_inner, aq_parent, aq_base, aq_get
from App.Management import Tabs
from App.Undo import UndoSupport
from DateTime import DateTime
from Globals import REPLACEABLE, NOT_REPLACEABLE
from ZPublisher.HTTPRequest import record

from OFS.CopySupport import CopySource, CopyError, eNotSupported, sanity_check
from OFS.Moniker import Moniker as _Moniker
from OFS.ObjectManager import ObjectManager, checkValidId, BadRequestException
from OFS.PropertyManager import PropertyManager
from OFS.SimpleItem import Item
from OFS.Traversable import Traversable
from OFS.Uninstalled import BrokenClass

from Globals import Persistent as _Persistent
from ZODB.POSException import ConflictError

try:
    # Zope 2.6.x
    from Interface.Implements import objectImplements, instancesOfObjectImplements
except ImportError:
    # Zope 2.5.x
    from Interface.Util import objectImplements, instancesOfObjectImplements

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.CMFCatalogAware import CMFCatalogAware
from Products.CMFCore.DynamicType import DynamicType
from Products.CMFCore.Expression import Expression
from Products.CMFCore.PortalContent import PortalContent
from Products.CMFCore.utils import getToolByName, UniqueObject, _getAuthenticatedUser, _checkPermission, \
     _getViewFor
from Products.CMFDefault.DublinCore import DefaultDublinCoreImpl
from Products.PageTemplates.Expressions import getEngine

import Config
from Config import Roles
from Features import createFeature
from Exceptions import formatErrorValue, formatException, InvalidIdError, DuplicateIdError, ReservedIdError, \
     getObjectRepr, getObjectPath

from Utils import InitializeClass, isInstance, addQueryString, getPublishedInfo, UpdateRolePermissions, \
     applyRecursive, getClassByMetaType, getContainedObjects, joinpath, splitpath, \
     normpath

from CustomDefinitions import CustomSystemObjects, portalConfiguration
from CustomObjects import ObjectHasCustomCategory

from logging import getLogger
logger = getLogger( 'SimpleObjects' )


class Persistent( _Persistent ):
    """
        Abstract base class for persistent objects.

        Objects inheriting this class have built-in support for instance
        version tracking and automatic update of properties
    """
    _class_version = 1.0

    __implements__ = createFeature('isPersistent')

    security = ClassSecurityInfo()

    # attributes for version tag support
    _class_tag = None
    _version_tag = None
    __changed = None

    def __init__( self ):
        """
            Initializes new persistent object.

            Sets initial version of the instance and invokes  '_initstate()'.
            Constructors in derived classes must be desinged to call this
            method in order for the object to be properly initialized
        """
        self._version_tag = None
        aq_base( self )._initstate( 0 )

    def __setstate__( self, state ):
        # this method is called to unpickle object
        # logger.info( 'Persistent.__setstate__ object %s started' % getObjectRepr(self) )

        try:
            _Persistent.__setstate__( self, state )
        except AttributeError:
            return

        # check whether an autoupdate feature is enabled
        if not ( Config.AutoUpdateObjects or \
                 getattr( self.__class__, '_force_autoupdate', None ) ):
            return

        if self._p_jar is None:
            logger.warning( 'Persistent.__setstate__ object %s has no connection' % getObjectRepr(self) )
            return

        # check for remote ZEO objects
        if hasattr( self._p_jar._storage, '_connection' ) and not Config.AutoUpdateRemote:
            return

        try:
            if aq_base( self )._initstate( 1 ):
                # reset is needed to register self in transaction
                self._p_changed = 0
                self._p_changed = self.__changed = 1
        except ConflictError:
            raise
        except:
            logger.error( 'Persistent.__setstate__ initstate error:', exc_info=True )

    def _initstate( self, mode ):
        """
            Callback method for object initialization.

            The purpose of this method is to initialize crucial attributes
            and bring the instance into some consistent state. The stored
            object can become inconsistent after new version of the class
            is installed, which requires additional attributes to exist that
            old instances may not have.

            This method is called several times during object's lifetime
            - during construction, after loading from the persistent storage
            if the class version tag has changed, and when the object is
            converted to another class.  The on-load call can be disabled
            globally by changing value of 'Config.AutoUpdateObjects'
            variable to false.

            This basic implementation checks for new properties in the
            '_properties' map of the class and adds missing attributes to the
            instance, using value of either '"default"' map entry or 'None'.
            Derived classes should define their own implementations in order
            to initialize additional attributes.

            Arguments:

                'mode' -- integer code, defined by conditions under which
                        the method was called: 0 - construction, 1 - load
                        from storage, 2 - convertation to another class

            Result:

                Boolean value, true if the object has changed.

            Note:

                The 'self' reference is an unwrapped object.
        """
        if mode < 2 and getattr( self, '_version_tag', None ) == self._class_tag:
            return 0

        #if mode:
        #    logger.info( 'Persistent._initstate object %s\nmode: %s (%s:%s)' % ( getObjectRepr(self), mode, \
        #        getattr( self, '_version_tag', None ), self._class_tag ) )
        self._version_tag = self._class_tag

        prop_map = getattr( self.__class__, '_properties', None )
        if prop_map:

            prop_self = self.__dict__.get( '_properties' )
            if prop_self is not None:
                prop_found = {}

                for prop in prop_self:
                    id = prop.get( 'id' )
                    if id is not None:
                        prop_found[ id ] = 1

            for prop in prop_map:
                id = prop.get( 'id' )
                if id is None:
                    continue

                if not hasattr( self, id ):
                    value = prop.get( 'default' )
                    if value is not None or not hasattr( self.__class__, id ):
                        # make a copy of value so that lists and dicts can be used
                        setattr( self, id, deepcopy(value) )

                if not ( prop_self is None or prop_found.get( id ) ):
                    prop_self = prop_self + ( prop, )

            if prop_self is not None:
                self._properties = prop_self

        return 1

    def _upgrade( self, id, klass, container=None, args=() ):
        """
            Converts a specified subobject to another class.

            Sometimes class of the existing persistent object needs to be
            changed, for example when the class is moved to another module.
            This procedure can be accomplished by calling this method on its
            container, specifying identifier of the subobject to be converted
            and the target class.  If the subobject is not a direct attribute
            of the container, but is located in a simple subcontainer such as
            list or dictionary, this subcontainer can be passed along.

            The target class must be derived from the old, unless the old
            class is broken.  Class convertation can be globally disabled by
            changing value of 'Config.AutoUpgradeObjects' variable to false.

            Arguments:

                'id' -- identifier under which the subobject is bound

                'klass' -- reference to the target class object

                'container' -- optional subcontainer of indirect subobjects,
                            'id' being the key into it

            Result:

                Converted subobject.
        """
        #logger.info( 'Persistent._upgrade object %s' % getObjectRepr(self) )

        if not Config.AutoUpgradeObjects:
            return None

        base = aq_base( self )

        if container is not None:
            try:
                old = container[ id ]
            except ( TypeError, KeyError, IndexError, AttributeError ):
                base = aq_base( container )
                container = None

        if container is None:
            old = getattr( base, id, None )

        # do nothing if the object is already an instance of the *klass*
        if old is None or isinstance( old, klass ):
            return old

        # check whether the object can be upgraded
        try: issub = issubclass( klass, old.__class__ ) or isinstance( old, BrokenClass )
        except: issub = 0 # old is not a class instance

        if not issub:
            # better not raise exception from __setstate__
            # raise TypeError, '%s must be a subclass of %s' % ( klass.__name__,
            # old.__class__.__module__ + '.' + old.__class__.__name__ )
            return old

        logger.info( 'Persistent._upgrade %s to %s' % ( getObjectRepr(old), klass.__name__ ) )

        # persistent object is actually loaded from the storage on _p_mtime access
        getattr( old, '_p_mtime', None )

        # create empty instance of the new *klass*
        if hasattr( klass, '__basicnew__' ):
            new = klass.__basicnew__()
        else:
            new = _new_instance( klass )

        # copy object data
        new.__dict__.update( old.__dict__ )

        # replace *old* object in the container with the *new*
        if container is None:
            setattr( base, id, new )
            if getattr( base, 'isAnObjectManager', None ):
                # ObjectManager stores object's meta_type, fix it
                for info in base._objects:
                    if info.get('id') == id:
                        info['meta_type'] = getattr( new, 'meta_type', None )
                        break
        else:
            container[ id ] = new

        if hasattr( old, '_p_oid' ) and hasattr( new, '_p_oid' ):
            # copy persistence attributes
            for attr in ['_p_jar','_p_oid','_p_serial']:
                setattr( new, attr, getattr( old, attr ) )

            # forget about casual changes of the *old*
            old.__changed  = 0
            old._p_changed = 0

            cache = new._p_jar._cache
            # try to free cache slot (for Zope >= 2.6)
            try: del cache[ new._p_oid ]
            except KeyError: pass

            # update object cache in this connection
            cache[ new._p_oid ] = new

        # unlink reference to the *old* object
        del old

        # bring the *new* object into valid state
        if isinstance( new, Persistent ):
            new._initstate( 2 )

        # set special "__changed" flag to be on the safe side
        if hasattr( new, '_p_oid' ):
            new._p_changed = new.__changed = 1

        # notify container of changed subobject
        if hasattr( base, '_p_oid' ):
            base._p_changed = 1

        return new

    def _extract( self, src, dst, *args ):
        # TODO it has nothing to do here - move to Utils, merge with get_param
        # gets property from the request
        values = []

        for name in src.keys():
            if not dst.has_key( name ):
                dst[ name ] = src[ name ]

        for name in args:
            if dst.has_key( name ):
                values.append( dst[ name ] )
                del dst[ name ]
            else:
                values.append( None )

        return len(values) > 1 and values or values[0]

    security.declarePublic( 'implements' )
    def implements( self, feature=None ):
        """
            Checks whether the object implements given interface or feature.

            The class is considered to support an interface if that interface
            is enlisted by its '__implements__' attribute.  This list of
            supported interfaces and features may also include those from
            parent classes.  Additionally, integer attributes of the class
            are checked, such as 'isPrincipiaFolderish'.

            Arguments:

                'feature' -- optional interface or feature of interest,
                        can be specified by name or as class object itself

            Result:

                If 'feature' is requested, boolean value indicating whether
                it is supported; otherwise list of names of all supported
                interfaces and features.
        """
        # TODO build map of supported interfaces during class initialization
        base = aq_base( self )

        if feature is None:
            # build a list of names
            ifaces_map = {}
            for iface in objectImplements( base ):
                ifaces_map[ iface.__name__ ] = ''
            # removes duplicate entries from the list to avoid ZCatalog
            # unindexing error
            return ifaces_map.keys()

        if type(feature) is StringType and feature[0] == '_':
            return 0

        for iface in objectImplements( base ):
            if iface is feature or iface.__name__ == feature:
                return 1

        attr = getattr( base.__class__, feature, None )
        if type(attr) is IntType and attr:
            return 1

        return 0

InitializeClass( Persistent )


class ItemBase( Implicit, Traversable, PropertyManager, CopySource, Tabs ):
    """
        Abstract base class for transient publishable objects.

        Objects inheriting this class have support for instance
        version tracking and auto-update
    """
    __allow_access_to_unprotected_subobjects__ = 1

    __implements__ = createFeature('isItem')

    security = ClassSecurityInfo()

    manage_options = PropertyManager.manage_options

    security.declarePublic( 'implements' )
    implements = Persistent.implements

    # always acquired from context
    REQUEST = Acquired

    __instance_created = None
    __instance_cloned = None
    __instance_destroyed = None

    def __init__( self, id=None, title=None ):
        """
            Arguments:

                'id' -- id of new object

                'title' -- title of new object.
        """
        self.__instance_created = 1
        if id is not None:
            try: self._setId( id )
            except AttributeError: self.id = id
        if title is not None:
            self.setTitle( title )

    security.declarePublic( 'getId' )
    #getId = Item.getId
    def getId( self ):
        # Returns the identifier of the object
        id = self.id
        if callable( id ): return id()
        return id

    security.declarePublic( 'Title' )
    def Title( self ):
        """
            Returns the object title (Dublin Core element - resource name)
        """
        return self.title

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setTitle' )
    def setTitle( self, title ):
        """
            Sets the object title (Dublin Core element - resource name).

            Arguments:

                'title' -- Title of the object.
        """
        try:
            if title:
                title = sub(r'((\S)_(\S))+(?i)', r'\2 \3', title)
        except:
            pass
        self.title = title

    def TitleOrId( self ):
        """
            Returns object's title or id if it's not
        """
        return self.Title() or self.getId()

    def setObjectLanguage( self, language ):
        """
            Sets the object language (Dublin Core element - resource language).

            Arguments:

                'language' -- language of the object text.
        """
        self.language = language

    def hasProperty( self, id ):
        """
            Checks whether the object has a property 'id'.

            Arguments:

                'id' -- property name

            Result:

                Boolean value.
        """
        for prop in self._propertyMap():
            if id == prop['id']:
                return 1
        return 0

    def getProperty( self, id, default=MissingValue ):
        """
            Returns value of the property 'id' of this object.

            If no such property is found, returns 'default' argument or None
            in case it is not specified.

            Arguments:

                'id' -- property name

                'default' -- value to be returned if property does not exist

            Result:

                Value of the property.
        """
        for prop in self._propertyMap():
            if id == prop['id']:
                try:
                    return getattr( aq_base(self), id )
                except AttributeError:
                    if default is MissingValue:
                        default = prop.get('default')
                    break
        else:
            if default is MissingValue:
                default = None
        return default

    def propdict( self ):
        # helper method for PropertyManager implementation
        result = {}
        for prop in self._propertyMap():
            result[ prop['id'] ] = prop
        return result

    security.declareProtected( CMFCorePermissions.ManageProperties, 'listEditableProperties' )
    def listEditableProperties( self ):
        """
            Returns a list of properties which  be directly
            edited from the user interface.

            Result:

                A list of dictionary items, each beeing a copy
        """
        # TODO: allow reordering of items
        results = []
        for prop in self._propertyMap():
            if prop.has_key('title') and prop.has_key('mode') and 'w' in prop['mode']:
                item = prop.copy()
                item['value'] = self.getProperty( item['id'] )
                results.append( item )
        return results

    security.declarePublic( 'physical_path' )
    def physical_path( self ):
        """
            Returns path to this object as a string
        """
        return joinpath( self.getPhysicalPath() )

    security.declarePublic( 'parent' )
    def parent( self ):
        """
            Returns the container of this object
        """
        return aq_parent( aq_inner( self ) )

    security.declarePublic( 'parent_path' )
    def parent_path( self ):
        """
            Retuns path to the containter as a string
        """
        return joinpath( aq_parent( aq_inner( self ) ).getPhysicalPath() )

    security.declarePublic( 'absolute_url' )
    def absolute_url( self, relative=0, action=None, frame=None, message=None, params=None, fragment=None, \
                      redirect=None, canonical=None, no_version=None, REQUEST=None ):
        """
            Returns absolute URL of the object
        """
        if REQUEST is None:
            REQUEST = aq_get( self, 'REQUEST', None )
            if REQUEST is None and redirect:
                redirect = 0 # no sense to request redirect without client

        if params is None:
            params = {}

        if not canonical and ( relative or REQUEST is not None ):
            base_url = Traversable.absolute_url.im_func( self, relative )
            if REQUEST and REQUEST.get('ExternalPublish'):
                # XXX workaround for the situation when Traversable.getPhysicalPath finds storage in acquisition
                base_url = sub(r'(/go)/storage($|/)', r'\1\2', base_url)
        else:
            srv = aq_get( self, 'server_url', None, 1 )
            base_url = Traversable.absolute_url.im_func( self, 1 )
            base_url = joinpath( srv, base_url )

        if not no_version and REQUEST is not None:
            principal, subpath = getPublishedInfo( self, REQUEST )[5:7]
            if subpath:
                principal = aq_base( principal )

                if aq_base( self ) is principal:
                    base_url = joinpath( base_url, subpath )

                elif aq_base( self.parent() ) is principal:
                    # TODO should reimplement absolute url to support
                    # arbitrary subpaths on all levels
                    base_url, mypath = splitpath( base_url )
                    base_url = joinpath( base_url, subpath, mypath )

        if frame is not None:
            url = action and joinpath( base_url, action ) or base_url
            params = { 'link' : addQueryString( url, params, fragment ) }
            action = frame

        url = action and joinpath( base_url, action ) or base_url

        if message is not None:
            if type(message) is StringType:
                msg_parts = message.split('$')
            else:
                msg_parts = None
            if msg_parts and len(msg_parts) > 0:
                params['portal_status_message'] = msg_parts[0].strip()
                params['portal_status_info'] = len(msg_parts) > 1 and msg_parts[1].strip() or None
                params['portal_status_style'] = len(msg_parts) > 2 and msg_parts[2].strip() or None
            else:
                params['portal_status_message'] = message
                params['portal_status_info'] = None
                params['portal_status_style'] = None

        if redirect:
            for param in [ 'noWYSIWYG' ]:
                params[ param ] = REQUEST.get( param )

            if REQUEST.get( '_UpdateWorkspace' ):
                params = { 'frame' : 'workspace',
                           'link'  : addQueryString( url, params, fragment ) }
                url = joinpath( base_url, 'reload_frame' )

            params['_UpdateSections'] = REQUEST.get( '_UpdateSections' )

        if params:
            url = addQueryString( url, params, fragment )

        return url

    security.declarePublic( 'relative_url' )
    def relative_url( self, action=None, frame=None, message=None, params=None, fragment=None, REQUEST=None ):
        """
            Returns URL relative to the request URL.
        """
        if REQUEST is None:
            REQUEST = aq_get( self, 'REQUEST', None )

        if params is None: params = {}

        if REQUEST is None:
            base_url = joinpath( '', Traversable.absolute_url.im_func( self, 1 ) )
        else:
            base = aq_base( self )
            base_url = REQUEST.get( (id(base), 'relative_url') )

            if base_url is None:
                published, object, is_method, path_id, has_slash, principal, subpath, is_subitem = getPublishedInfo( self, REQUEST )

                object = aq_base( object )
                principal = aq_base( principal )
                # TODO: check REQUEST.base

                if base is object or ( is_subitem and base is principal ):
                    if is_method:
                        base_url = has_slash and '..' or ''
                    else:
                        base_url = not has_slash and path_id or '' #

                elif aq_base( self.parent() ) is principal:
                    my_id = self.getId()
                    if is_method:
                        base_url = has_slash and joinpath( '..', my_id ) or my_id
                    else:
                        base_url = has_slash and my_id or joinpath( path_id, my_id )

                else:
                    if self.implements('isVersion') and self.getPrincipalVersionId()==self.id:
                        base_url = joinpath( '', REQUEST._script, Traversable.absolute_url.im_func( aq_parent(self), 1 ) )
                    else:
                        base_url = joinpath( '', REQUEST._script, Traversable.absolute_url.im_func( self, 1 ) )
                    if subpath:
                        if base is principal:
                            base_url = joinpath( base_url, subpath )

                        elif aq_base( self.parent() ) is principal:
                            base_url, mypath = splitpath( base_url )
                            base_url = joinpath( base_url, subpath, mypath )

                # cache result
                REQUEST.set( (id(base), 'relative_url'), base_url )

        if frame is not None:
            url = not frame and splitpath( base_url )[1] or ''
            url = ( url and joinpath( url, action ) or action ) or '.'
            params = { 'link' : addQueryString( url, params, fragment ) }
            action = frame

        if action is None:
            url = base_url or '.'
        else:
            url = base_url and joinpath( base_url, action ) or action

        if message is not None:
            params['portal_status_message'] = message

        if params:
            url = addQueryString( url, params, fragment )

        return url

    security.declarePublic( 'redirect' )
    def redirect( self, status=None, REQUEST=None, *args, **kw ):
        """
            Redirects browser to another view of this object.
        """
        if REQUEST is None:
            REQUEST = aq_get( self, 'REQUEST' ) # can raise
        if not status:
            status = (REQUEST.REQUEST_METHOD == 'POST') and 303 or 302

        kw['REQUEST'] = REQUEST
        kw['redirect'] = 1

        url = self.absolute_url( *args, **kw )
        REQUEST.RESPONSE.redirect( url, status=status )

        return url

    def raise_standardErrorMessage( self, client=None, REQUEST={},
        error_type=None, error_value=None, tb=None, *args, **kw ):

        #if error_tb is None:
        #    error_tb = formatException( error_type, error_value, tb )

        # try to authenticate user
        #if REQUEST and REQUEST._auth \
        #           and error_type in [ 'Debug Error', 'NotFound', 'Forbidden' ] \
        #           and getSecurityManager().getUser() is nobody:
        #    try: REQUEST.clone().traverse( self.physical_path() )
        #    except: pass

        error_value = formatErrorValue( error_type, error_value )

        Item.raise_standardErrorMessage.im_func( self, client, REQUEST, \
                error_type, error_value, tb, *args, **kw )

    def cb_isCopyable( self ):
        """ Checks whether the object can be copied via clipboard
        """
        return CopySource.cb_isCopyable( self ) and \
               _checkPermission( CMFCorePermissions.View, self )

    def cb_isMoveable( self ):
        """ Checks whether the object can be moved via clipboard
        """
        return CopySource.cb_isMoveable( self ) and \
               _checkPermission( ZopePermissions.delete_objects, self )

    def _getCopy( self, container ):
        #
        # Called by CopyContainer to perform object clone operation.
        #
        new = CopySource._getCopy( self, container )
        new.__instance_cloned = self

        return new

    def manage_afterAdd( self, item, container ):
        #
        # Called by ObjectManager after the object is added to the container.
        # We use it to launch our creation/clone and add hooks.
        #
        if self.__instance_created:
            try:
                applyRecursive( ItemBase._instance_onCreate, 0, self )
            finally:
                del self.__instance_created

        elif self.__instance_cloned is not None:
            source = self.__instance_cloned
            try:
                applyRecursive( ItemBase._instance_onClone, 0, self, source, item )
            finally:
                del self.__instance_cloned

        applyRecursive( ItemBase._containment_onAdd, 0, self, item, container )

    def manage_afterClone( self, item ):
        #
        # Called by CopyContainer on the copy after the object is copied (copy/paste)
        # and added to the container. Exists here only for completeness.
        #
        if isInstance( item, ItemBase ) and item.__instance_cloned is not None:
            subpath = self.getPhysicalPath()[ len( item.getPhysicalPath() ): ]
            source = item.__instance_cloned.unrestrictedTraverse( subpath )
            applyRecursive( ItemBase._instance_onClone, 0, self, source, item )

        try:
            if hasattr(item, 'creation_date') and self.implements('isDocument'):
                item.creation_date = DateTime()
                #logger.info( 'manage_afterClone reindex %s' % `self` )
                item.reindexObject( idxs=['created',] )
        except:
            pass

    def manage_beforeDelete( self, item, container ):
        #
        # Called by ObjectManager before the object is removed from its container.
        # We use it to launch our delete and destroy hooks.
        #
        applyRecursive( ItemBase._containment_onDelete, 1, self, item, container )

        if self.__instance_destroyed:
            try:
                applyRecursive( ItemBase._instance_onDestroy, 1, self )
            finally:
                del self.__instance_destroyed

        elif isInstance( item, ItemBase ) and item.__instance_destroyed:
            applyRecursive( ItemBase._instance_onDestroy, 1, self )

    def _instance_onCreate( self ):
        """
            Instance creation event hook.

            This method is invoked upon the instance creation and normally
            is called only once in the object's lifetime just after
            the instance initialization.
        """
        pass

    def _instance_onClone( self, source, item ):
        """
            Instance clone event hook.

            This method is invoked upon the instance creation in case it was
            added by means of copy/paste operation.

            Arguments:

                'source' -- copy source object

                'item' -- cloned object
        """
        pass

    def _instance_onDestroy( self ):
        """
            Instance destroy event hook.

            This method is invoked in case the instance is going to be
            totally removed from the storage.
        """
        pass

    def _containment_onAdd( self, item, container ):
        """
            Containment add event hook.

            This method is invoked after the object is added to the
            container.

            Arguments:

                'item' -- added object

                'container' -- item container object

            Note: there is a difference between '_instance_onCreate'
            and '_containment_onAdd' hooks. The first is called only
            once after the object creation time while the last method
            is invoked on every cut/paste operation that moves object
            to the new container.
        """
        pass

    def _containment_onDelete( self, item, container ):
        """
            Containment delete event hook.

            This method is invoked before deleting the object from it's
            container.

            Arguments:

                'item' -- added object

                'container' -- item container object

            Note: see '_containment_onAdd' for further explanations.
        """
        pass

InitializeClass( ItemBase )


class InstanceBase( Persistent, ItemBase ):
    """
        Abstract base class for persistent publishable objects.
    """
    _class_version = 1.0

    __implements__ = Persistent.__implements__, \
                     ItemBase.__implements__

    def __init__( self, id=None, title=None ):
        Persistent.__init__( self )
        ItemBase.__init__( self, id, title )

InitializeClass( InstanceBase )


class ContentBase( InstanceBase, DefaultDublinCoreImpl, PortalContent ):
    """
        Abstract base class for content objects.
    """
    _class_version = 1.0

    security = ClassSecurityInfo()

    __implements__ = InstanceBase.__implements__, \
                     DefaultDublinCoreImpl.__implements__, \
                     PortalContent.__implements__

    manage_options = InstanceBase.manage_options + \
                     PortalContent.manage_options

    _properties = InstanceBase._properties + (
            #DefaultDublinCoreImpl._properties +
            {'id':'nd_uid', 'type':'string', 'mode':'w'},
        )

    # object owner will have this role
    _owner_role = Roles.Owner

    # name of the default object view method
    _default_view = None

    # default attribute values
    nd_uid = None

    # default actions list for actions tool
    _actions = ()

    def __init__( self, id=None, title=None, **kwargs ):
        """ Initialize class instance
        """
        InstanceBase.__init__( self, id, title )
        DefaultDublinCoreImpl.__init__( self, **kwargs )

    def __call__( self, REQUEST=None ):
        """
            Invokes the default view
        """
        try:
            view = _getViewFor( self )

        except 'Not Found':
            name = self._default_view
            if not name:
                raise

            view = getattr( self, name )
            if not getSecurityManager().validate( self, self, name, view ):
                raise Unauthorized( name, self )

        if getattr( aq_base(view), 'isDocTemp', None ):
            return apply( view, (self, REQUEST or self.REQUEST) )
        else:
            return view( REQUEST )

    security.declarePublic( 'locate_url' )
    def locate_url( self, expand=1, params=None, fragment=None, REQUEST=None ):
        """
            Returns URL to locate object via portal_links
        """
        if params is None:
            params = {}

        uid = self.getUid()
        portal_links = getToolByName( self, 'portal_links', None )

        if not uid or portal_links is None:
            url = self.absolute_url( params=params, fragment=fragment, REQUEST=REQUEST )
            url = '%s%s' % ( url, expand and '&expand=1' or '' )
            return url

        url = Traversable.absolute_url.im_func( portal_links, 0 )
        url = '%s/locate?uid=%s%s' % ( url, uid, expand and '&expand=1' or '' )

        if params:
            url = addQueryString( url, params, fragment )

        return url

    security.declarePublic( 'getUid' )
    def getUid( self ):
        """
            Returns object's UID
        """
        return self.nd_uid

    def _generate_uid( self ):
        """
            Generates unique object identificator (UID).

            We use portal system specification (index) in order to make out system where the object was generated.
            Look at PortalConfiguration class to explain this feature (UID should be unique between instances).

            Index by default is 'X'.
        """
        prptool = getToolByName( self, 'portal_properties', None )
        instance = prptool.getProperty('instance')
        default_index = 'X'

        try: index = portalConfiguration.getAttribute( instance, 'index' ) or default_index
        except: index = default_index

        uid = '%012u%s%05u%05u' % ( long( time()*100 ), index, id(self)%100000, randrange(100000) )
        return uid

    security.declarePrivate( 'addUid' )
    def addUid( self, container=None, force=None ):
        """ 
            Adds UID as 'nd_uid' property to the target object.
            Doesn't generate new uid if it already exists.
        """
        if not force and self.getProperty( 'nd_uid' ) is not None:
            if container is None or container.getProperty( 'nd_uid' ) is not None:
                return
        uid = self._generate_uid()
        self._setPropValue( 'nd_uid', uid )

    security.declarePrivate( 'listActions' )
    def listActions( self, info=None ):
        """ Add item actions to actions list
        """
        return self._actions

    security.declareProtected( ZopePermissions.take_ownership, 'changeOwnership' )
    def changeOwnership( self, user, recursive=None, explicit=None ):
        """
            Change owner of the object.
            If 'recursive' is 0 keep sub-objects ownership information.
        """
        new = None

        if type(user) is StringType:
            member = getToolByName( self, 'portal_membership', None ).getMemberById( user )
            user = member is not None and member.getUser() or None

        if user is None:
            if explicit:
                self._owner = None
            else:
                try: del self._owner
                except AttributeError: pass
        elif recursive is None or recursive:
            # TODO support explicit
            Item.changeOwnership( self, user, recursive )
        else:
            new = ownerInfo( user )
            old = aq_get( self, '_owner', None, 1 )
            if old is not UnownableOwner and new is not None and ( new != old or explicit ):
                self._owner = new

        try: owner = self.getOwner()
        except:
            logger.error("changeOwnership self: %s" % `self`)
            owner = None
        owner = owner is not None and owner.getUserName() or None
        owner_role = self._owner_role
        oidxs = ['Creator']

        #logger.info( 'changeOwnership user: %s, recursive: %s, owner: %s\nself: %s' % ( \
        #    user, recursive, owner, `self` ) )

        if owner and owner_role:
            owners = self.users_with_local_role( owner_role )

            if owner not in owners:
                roles = [ owner_role ]
                roles.extend( self.get_local_roles_for_userid( owner ) )
                self.manage_setLocalRoles( owner, roles )
                oidxs.append('allowedRolesAndUsers')

            elif owner and len(owners) > 1:
                owners = [ o for o in owners if o != owner ]
                if owners:
                    oidxs.append('allowedRolesAndUsers')

            for name in owners:
                roles = self.get_local_roles_for_userid( name )
                roles = [ r for r in roles if r != owner_role ]
                if roles:
                    self.manage_setLocalRoles( name, list(roles) )
                else:
                    self.manage_delLocalRoles( (name,) )

            UpdateRolePermissions( self )

        #if self.getUid():
        #    logger.info( 'changeOwnership reindex: %s' % `self` )
        #    self.reindexObject( idxs=oidxs )

    security.declareProtected( CMFCorePermissions.View, 'getContentsSize' )
    def getContentsSize( self ):
        """
            Returns size of the object
        """
        if hasattr( aq_base( self ), 'get_size' ):
            return self.get_size()
        return 0

    security.declareProtected( ZopePermissions.delete_objects, 'deleteObject' )
    def deleteObject( self, REQUEST=None ):
        """
            Delete me!
        """
        return self.confirm_delete(aq_parent(self), REQUEST, ids=[self.getId(),])

    def externalEdit( self, REQUEST ):
        """
            Opens this object in the External Editor.
            Should be directly called by the Web browser
        """
        REQUEST['target'] = self.getId()
        return self.parent().externalEdit_.index_html( REQUEST, REQUEST.RESPONSE )

    def _getCopy( self, container ):
        new = InstanceBase._getCopy( self, container )
        new.creation_date = DateTime()

        # reset global unique object id
        try: new._updateProperty( 'nd_uid', None )
        except: pass

        return new

    def _instance_onCreate( self ):
        # generate UID
        self.addUid()

    def _instance_onClone( self, source, item ):
        # generate another UID
        self.addUid( force=1 )

        if self is not item:
            return

        # if attach dont add prefix 'copy'
        from File import FileAttachment
        from ImageAttachment import ImageAttachment
        if isinstance( self, FileAttachment ) or isinstance( self, ImageAttachment ):
            return

        # prepend 'Copy' prefix to the object's title
        msg = getToolByName( item, 'msg' )

        if self.implements('hasLanguage'):
            lang = self.Language()
        else:
            lang = msg.get_default_language()

        # prefix = msg.gettext( 'copy', lang=lang )
        # if self.getId().startswith('copy'):
        #     prefix += self.getId()[ 4:self.getId().find('_') ]

        # self.setTitle( prefix + ' ' + self.Title() )
        self.setTitle( self.Title() )

    def _instance_onDestroy( self ):
        # remove links bound to this object
        lntool = getToolByName( self, 'portal_links', None )
        if lntool is not None:
            lntool.removeBoundLinks( self )

    def _containment_onAdd( self, item, container ):
        PortalContent.manage_afterAdd( self, item, container )

    def _containment_onDelete( self, item, container ):
        PortalContent.manage_beforeDelete( self, item, container )

    def _remote_onTransfer( self, remote ):
        # transfer local object to the remote server
        dltool = getToolByName( self, 'portal_links', None )
        dlremote = getToolByName( remote, 'portal_links', None )

        if dltool is None or dlremote is None:
            return

        file = dltool._exportLinks( self )
        if file:
            dlremote._importLinks( file )

    security.declarePublic('archive')
    def archive( self ):
        """ 
            This is 'archive' index metadata. Used by catalog
        """
        IsArchive = 0
        archive_states = ['archive','OnArchive']

        if self.meta_type == 'HTMLDocument':
            workflow = getToolByName(self, 'portal_workflow', None)
            IsArchive = workflow is not None and workflow.getInfoFor( self, 'state', '' ) in \
                        archive_states and 1 or 0
        elif self.meta_type == 'Task Item':
            base = self.getBase()
            if base and ( base.implements('isDocument') or base.implements('isVersionable') ):
                workflow = getToolByName(self, 'portal_workflow', None)
                IsArchive = workflow is not None and workflow.getInfoFor( base, 'state', '' ) in \
                            archive_states and 1 or 0

        return IsArchive

    security.declarePublic('hasResolution')
    def hasResolution( self ):
        """
            This is 'hasResolution' index metadata. Used by catalog
        """
        if self.meta_type not in ['HTMLDocument']:
            return 0

        if not ObjectHasCustomCategory( self ):
            return 0

        tasks = self.followup.getBoundTasks()
        if not tasks:
            return 0

        IsResolution = 0
        for task in tasks:
            if task.getTaskResolution() is not None:
                IsResolution = 1
                break

        return IsResolution

    security.declarePublic('IsSystemObject')
    def IsSystemObject( self, no_authenticate=None ):
        """
            Check either the object is being a system
        """
        if not no_authenticate:
            portal_membership = getToolByName( self, 'portal_membership' )
            user = portal_membership.getAuthenticatedMember()
            IsManager = user.IsManager()
            IsAdmin = user.IsAdmin()

            if IsAdmin: return 0

        is_system_object = 0
        url = self.absolute_url()
        system_objects = CustomSystemObjects()

        for key in system_objects:
            if url.find( key ) > -1:
                is_system_object = 1
                break

        return is_system_object

    def IsLocked( self ):
        """
            Checks if object is locked for view
        """
        roles = rolesForPermissionOn( CMFCorePermissions.View, self )
        return not Roles.Reader in roles and 1 or 0
        #return not _checkPermission( CMFCorePermissions.View, self ) and 1 or 0

    def IsLockAllowed( self ):
        """
            Checks if view object locking is allowed 
        """
        owners = self.users_with_local_role( self._owner_role or Roles.Owner )
        uname = _getAuthenticatedUser(self).getUserName()
        return uname in owners and 1 or 0

InitializeClass( ContentBase )


class ContainerBase( InstanceBase, ObjectManager ):
    """
        Abstract base class for container objects.
    """
    _class_version = 1.0

    isPrincipiaFolderish = 0

    security = ClassSecurityInfo()

    manage_options = (
            { 'label'  : 'Contents',
              'action' : 'manage_contents', #'manage_main'
              'help'   : ('OFSP', 'ObjectManager_Contents.stx') },
         ) + InstanceBase.manage_options

    security.declareProtected( ZopePermissions.view_management_screens, 'manage_contents' )
    manage_contents = ObjectManager.manage_main

    security.declarePublic( 'checkId' )
    def checkId( self, id, allow_dup=0 ):
        """
            Checks that *id* doesn't exists in container
        """
        try:
            self._checkId( id, allow_dup )
        except InvalidIdError, exc:
            return exc
        return None

    def _checkId( self, id, allow_dup=0 ):
        """
            This method prevents people other than the portal manager
            from overriding skinned names
        """
        try:
            checkValidId( self, id, allow_dup )
        except BadRequestException, msg:
            message = str(msg)
            if not message:
                pass
            elif message.find('in use') >= 0:
                raise DuplicateIdError, "This identifier is already in use."
            elif message.find('reserved') >= 0:
                raise ReservedIdError, "This identifier is reserved."
            raise InvalidIdError, "This identifier is not valid."

        if allow_dup or id == 'index_html':
            return

        ob = self
        while ob is not None and not getattr( ob, '_isPortalRoot', 0 ):
            ob = aq_parent( aq_inner(ob) )
        if ob is None or not hasattr( aq_base( ob ), id ):
            return

        item = getattr( ob, id )
        # allow storages in site containers
        if isinstance( item, ContentBase ):
            return
        # if the portal root has no object by this name, allow an override
        flags = getattr( item, '__replaceable__', NOT_REPLACEABLE )
        if flags & REPLACEABLE:
            return
        # portal manager may override anything
        if _checkPermission( CMFCorePermissions.ManagePortal, self ):
            return

        raise ReservedIdError, "This identifier is reserved."

    def objectIds( self, spec=None, implements=None ):
        # Returns a list of subobject ids of the current object.
        # If 'spec' is specified, returns objects whose meta_type
        # matches 'spec'.
        if spec is None and implements is None:
            return [ ob['id'] for ob in self._objects ]

        if type(spec) == StringType:
            spec = [spec]
        if type(implements) == StringType:
            implements = [implements]

        set = []
        checked = {}

        for ob in self._objects:
            mtype = ob['meta_type']
            if spec and mtype not in spec:
                continue

            if implements:
                if not checked.has_key( mtype ):
                    checked[ mtype ] = 0
                    klass = getClassByMetaType( mtype, None )
                    if klass is None:
                        continue

                    for feature in implements:
                        for iface in instancesOfObjectImplements( klass ):
                            if iface.__name__ == feature:
                                break
                        else:
                            attr = getattr( klass, feature, None )
                            if not ( type(attr) is IntType and attr ):
                                break # failed
                    else:
                        checked[ mtype ] = 1

                if not checked[ mtype ]:
                    continue

            set.append( ob['id'] )

        return set

    def objectValues( self, spec=None, implements=None ):
        # Returns a list of actual subobjects of the current object.
        # If 'spec' is specified, returns only objects whose meta_type
        # match 'spec'.
        return [ self._getOb(id) for id in self.objectIds( spec, implements ) ]

    def objectItems( self, spec=None, implements=None ):
        # Returns a list of (id, subobject) tuples of the current object.
        # If 'spec' is specified, returns only objects whose meta_type match
        # 'spec'
        return [ (id, self._getOb(id)) for id in self.objectIds( spec, implements ) ]

    security.declareProtected( ZopePermissions.delete_objects, 'deleteObjects' )
    def deleteObjects( self, ids ):
        self.manage_delObjects( ids )
        return ids

    def moveObject( self, ob, REQUEST=None ):
        """
            Move object inside the given container
        """
        if not sanity_check( self, ob ):
            raise CopyError, 'This object cannot be pasted into itself'

        try: 
            ob._notifyOfCopyTo( self, op=1 )
        except:
            raise CopyError, sys.exc_info()[1]

        id = ob.getId()
        parent = aq_parent(aq_inner(ob))
        parent._objects = tuple(filter(lambda i,n=id: i['id']!=n, parent._objects))
        parent._delOb(id)
        p_from = parent.physical_path()

        new_id = self._get_id(id)
        meta_type = getattr(ob, 'meta_type', None)

        self._objects = self._objects + ( { 'id' : new_id, 'meta_type' : meta_type }, )
        if new_id != id:
            ob._setId(new_id) # setattr(ob, 'id', new_id)
        self._setOb(new_id, ob)

        obj = self._getOb(new_id)

        catalog = getToolByName(self, 'portal_catalog', None)
        followup = getToolByName(self, 'portal_followup', None)

        # XXX move all contained objects inside the catalog(s)
        objects = getContainedObjects( obj, path=1, recursive=1 )
        p_to = self.physical_path()

        for o, uid in objects:
            path = uid.replace( p_to, p_from ).replace( new_id, id )
            if getattr(o, 'meta_type', None) == 'Task Item' and followup is not None:
                followup._catalog.moveObject( o, uid, path, idxs=() )
            if catalog is not None:
                w = catalog.wrapOb(o)
                catalog._catalog.moveObject( w, uid, path )

        return obj

    def _containment_onAdd( self, item, container ):
        ObjectManager.manage_afterAdd( self, item, container )

    def _instance_onClone( self, source, item ):
        ObjectManager.manage_afterClone( self, item )

    def _containment_onDelete( self, item, container ):
        ObjectManager.manage_beforeDelete( self, item, container )

    def _CMFCatalogAware__recurse( self, name, *args ):
        # avoid double (un)indexing of subobjects
        # if self inherits both ContainerBase and ContentBase
        pass

InitializeClass( ContainerBase )


class ToolBase( UniqueObject, InstanceBase, ActionProviderBase, UndoSupport ):
    """
        Abstract base class for portal tools.
    """
    _class_version = 1.0

    security = ClassSecurityInfo()

    manage_options = ActionProviderBase.manage_options + \
                     InstanceBase.manage_options + \
                     UndoSupport.manage_options

    _actions = ActionProviderBase._actions # list(...), why?

    def redirect( self, status=None, REQUEST=None, action=None, *args, **kw ):
        if action is not None:
            actions = getToolByName( self, 'portal_actions', None )
            if actions is not None:
                actinfo = actions.getAction( action )
                if actinfo:
                    return REQUEST.RESPONSE.redirect( actinfo['url'] ) # XXX

        return InstanceBase.redirect( self, status, REQUEST, action=action, *args, **kw )

InitializeClass( ActionProviderBase ) # CMF 1.3.1 bug
InitializeClass( ToolBase )


from Acquisition import ImplicitAcquisitionWrapper
class ProxyValue( Implicit ):

    def __of__( self, parent ):
        return getattr( parent._v_proxied_object, self.__name__ )

class ProxyItemMixin( Implicit ):

    _v_proxied_object = None

    def _proxy_connect( self ):
        raise NotImplementedError

    def __of__( self, parent ):
        wrapped = Implicit.__of__( aq_base(self), parent )
        try: wrapped._proxy_connect()
        except: pass
        return wrapped

    def __getattr__( self, name ):
        if self._v_proxied_object is None:
            raise AttributeError, name
        p=ProxyValue()
        p.__name__=name
        value = getattr( aq_base(self._v_proxied_object), name )
        if name.startswith('_'):
            raise Unauthorized( name, value )
        return ImplicitAcquisitionWrapper( p, self )


class ExpressionWrapper( Persistent ):

    _class_version = 1.0

    expr = None
    factory = Expression
    use_dict = None

    def __init__( self, text=None, factory=None, use_dict=None ):
        """ Initialize class instance
        """
        Persistent.__init__( self )

        if factory:
            self.factory = factory
        if text:
            self.expr = self.factory( text )
        if use_dict is not None:
            self.use_dict = int(use_dict)

    def _initstate( self, mode ):
        """ Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if getattr( self, 'usefirst', None ) is not None:
            delattr( self, 'usefirst' )
            self.use_dict = 1

        return 1

    def __call__( self, *args, **kw ):
        """ Execute expression
        """
        if self.use_dict and len(args) >= self.use_dict:
            adict = args[ self.use_dict - 1 ]
            if type(adict) is DictType:
                kw.update( adict )
            elif hasattr( adict, '__dict__' ):
                kw.update( adict.__dict__ )

        for i in range( len(args) ):
            kw[ 'arg' + str(i+1) ] = args[i]

        return self.expr( getEngine().getContext( kw ) )

    def setExpression( self, text ):
        """ Change expression text
        """
        self.expr = self.factory( text )

InitializeClass( ExpressionWrapper )

class Moniker( _Moniker ):

    def __init__( self, ob=None, data=None ):
        # Construct Moniker instance from either object or data generated by dump().
        if ob is not None:
            self.idpath = ob.getPhysicalPath()

        elif data:
            self.idpath = data

    def getPath( self ):
        # Return traversable path to the named object.
        return self.idpath


class SimpleRecord:

    def __init__( self, data=None, *args, **kwargs ):
        if args and data:
            for name in args:
                self.__dict__[ name ] = data[ name ]

        elif type(data) is DictType:
            self.__dict__.update( data )

        elif isInstance( data, record ):
            self.__dict__.update( data.__dict__ )

        if kwargs:
            self.__dict__.update( kwargs )

    def __getitem__( self, key ):
        return self.__dict__[ key ]

    def __setitem__( self, key, value ):
        self.__dict__[ key ] = value

    def __contains__( self, key ):
        return self.__dict__.has_key( key )

    def keys( self ):
        return self.__dict__.keys()

    def values( self ):
        return self.__dict__.values()

    def items( self ):
        return self.__dict__.items()

    def get( self, key, default=None ):
        return self.__dict__.get( key, default )

    def setdefault( self, key, value ):
        return self.__dict__.setdefault( key, value )

    def updatedefault( self, data ):
        for key, value in data.items():
            self.__dict__.setdefault( key, value )

    def setactive( self, key, value ):
        if not value and self.__dict__.has_key( key ):
            return self.__dict__[ key ]
        self.__dict__[ key ] = value
        return value

    def copy( self ):
        return self.__class__( self.__dict__ )

    has_key = __contains__
